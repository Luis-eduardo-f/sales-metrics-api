"""Analytical endpoints: revenue over time and top products by revenue.

Both endpoints deliberately group/aggregate data in Python after a single portable SQL query,
rather than relying on dialect-specific SQL (e.g. SQLite's `strftime` vs. PostgreSQL's
`date_trunc`) to bucket by day/month. For the size of dataset this project targets (a synthetic
demo warehouse, not a multi-terabyte fact table) this keeps the code identical -- and equally
fast -- against both supported databases. A future iteration aimed at much larger data volumes
would push the grouping back into SQL (with a per-dialect implementation) once that trade-off
starts to matter.
"""

from collections import defaultdict
from datetime import date, datetime, time

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.cache import cache_get, cache_set, make_cache_key
from app.database import get_db
from app.models import Order, OrderItem, OrderStatus, Product
from app.schemas import (
    RevenueBucket,
    RevenueGroupBy,
    RevenueResponse,
    TopProduct,
    TopProductsResponse,
)

router = APIRouter(prefix="/metrics", tags=["metrics"], dependencies=[Depends(require_api_key)])


def _validate_date_range(start_date: date | None, end_date: date | None) -> None:
    if start_date is not None and end_date is not None and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_date must be on or before end_date.",
        )


def _date_bounds(start_date: date | None, end_date: date | None) -> tuple[datetime | None, datetime | None]:
    """Convert inclusive calendar-date bounds into inclusive datetime bounds."""

    start_dt = datetime.combine(start_date, time.min) if start_date else None
    end_dt = datetime.combine(end_date, time.max) if end_date else None
    return start_dt, end_dt


@router.get(
    "/revenue",
    response_model=RevenueResponse,
    summary="Aggregated revenue over time",
    description=(
        "Sums `quantity * unit_price` across all order items belonging to non-cancelled "
        "orders, grouped by day or month. Results are cached in-process for a short TTL "
        "(cache-aside pattern) since dashboards tend to re-request the same window "
        "repeatedly -- see the `cached` field and the README for details."
    ),
)
def get_revenue(
    group_by: RevenueGroupBy = Query(
        RevenueGroupBy.DAY, description="Time granularity to bucket revenue by."
    ),
    start_date: date | None = Query(None, description="Inclusive start of the date range (YYYY-MM-DD)."),
    end_date: date | None = Query(None, description="Inclusive end of the date range (YYYY-MM-DD)."),
    db: Session = Depends(get_db),
) -> RevenueResponse:
    _validate_date_range(start_date, end_date)

    cache_key = make_cache_key("revenue", group_by.value, start_date, end_date)
    cached_response = cache_get(cache_key)
    if cached_response is not None:
        return cached_response.model_copy(update={"cached": True})

    start_dt, end_dt = _date_bounds(start_date, end_date)

    stmt = (
        select(OrderItem.quantity, OrderItem.unit_price, Order.order_date, Order.id)
        .join(Order, OrderItem.order_id == Order.id)
        .where(Order.status.in_(OrderStatus.revenue_statuses()))
    )
    if start_dt is not None:
        stmt = stmt.where(Order.order_date >= start_dt)
    if end_dt is not None:
        stmt = stmt.where(Order.order_date <= end_dt)

    rows = db.execute(stmt).all()

    revenue_by_bucket: dict[str, float] = defaultdict(float)
    orders_by_bucket: dict[str, set[int]] = defaultdict(set)

    for quantity, unit_price, order_date, order_id in rows:
        if group_by == RevenueGroupBy.DAY:
            bucket_key = order_date.date().isoformat()
        else:
            bucket_key = order_date.strftime("%Y-%m")
        revenue_by_bucket[bucket_key] += float(quantity) * float(unit_price)
        orders_by_bucket[bucket_key].add(order_id)

    buckets = [
        RevenueBucket(
            period=period,
            revenue=round(revenue, 2),
            order_count=len(orders_by_bucket[period]),
        )
        for period, revenue in sorted(revenue_by_bucket.items())
    ]
    total_revenue = round(sum(revenue_by_bucket.values()), 2)

    response = RevenueResponse(
        group_by=group_by,
        start_date=start_date,
        end_date=end_date,
        total_revenue=total_revenue,
        buckets=buckets,
        cached=False,
    )
    cache_set(cache_key, response)
    return response


@router.get(
    "/top-products",
    response_model=TopProductsResponse,
    summary="Top products by revenue",
    description=(
        "Ranks products by total revenue (`quantity * unit_price`) across non-cancelled "
        "orders in the given date range, descending."
    ),
)
def get_top_products(
    limit: int = Query(10, ge=1, le=100, description="Maximum number of products to return."),
    start_date: date | None = Query(None, description="Inclusive start of the date range (YYYY-MM-DD)."),
    end_date: date | None = Query(None, description="Inclusive end of the date range (YYYY-MM-DD)."),
    db: Session = Depends(get_db),
) -> TopProductsResponse:
    _validate_date_range(start_date, end_date)
    start_dt, end_dt = _date_bounds(start_date, end_date)

    stmt = (
        select(
            Product.id,
            Product.name,
            Product.category,
            OrderItem.quantity,
            OrderItem.unit_price,
        )
        .join(OrderItem, OrderItem.product_id == Product.id)
        .join(Order, OrderItem.order_id == Order.id)
        .where(Order.status.in_(OrderStatus.revenue_statuses()))
    )
    if start_dt is not None:
        stmt = stmt.where(Order.order_date >= start_dt)
    if end_dt is not None:
        stmt = stmt.where(Order.order_date <= end_dt)

    rows = db.execute(stmt).all()

    aggregates: dict[int, dict] = {}
    for product_id, name, category, quantity, unit_price in rows:
        entry = aggregates.setdefault(
            product_id, {"name": name, "category": category, "revenue": 0.0, "units_sold": 0}
        )
        entry["revenue"] += float(quantity) * float(unit_price)
        entry["units_sold"] += quantity

    ranked = sorted(aggregates.items(), key=lambda kv: kv[1]["revenue"], reverse=True)[:limit]

    products = [
        TopProduct(
            product_id=product_id,
            name=data["name"],
            category=data["category"],
            revenue=round(data["revenue"], 2),
            units_sold=data["units_sold"],
        )
        for product_id, data in ranked
    ]

    return TopProductsResponse(start_date=start_date, end_date=end_date, limit=limit, products=products)
