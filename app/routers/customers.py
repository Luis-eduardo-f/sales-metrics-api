"""Customer listing and per-customer order summary endpoints."""

import math

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.database import get_db
from app.models import Customer, Order, OrderItem, OrderStatus
from app.schemas import CustomerListResponse, CustomerOut, CustomerSummary

router = APIRouter(prefix="/customers", tags=["customers"], dependencies=[Depends(require_api_key)])


@router.get(
    "",
    response_model=CustomerListResponse,
    summary="List customers",
    description="Paginated, optionally filtered by country (case-insensitive exact match).",
)
def list_customers(
    page: int = Query(1, ge=1, description="1-indexed page number."),
    page_size: int = Query(20, ge=1, le=100, description="Number of customers per page."),
    country: str | None = Query(None, description="Filter to customers in this country (case-insensitive)."),
    db: Session = Depends(get_db),
) -> CustomerListResponse:
    filters = []
    if country:
        filters.append(Customer.country.ilike(country))

    total = db.execute(select(func.count()).select_from(Customer).where(*filters)).scalar_one()

    stmt = (
        select(Customer)
        .where(*filters)
        .order_by(Customer.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    customers = db.execute(stmt).scalars().all()

    total_pages = math.ceil(total / page_size) if total else 0

    return CustomerListResponse(
        items=[CustomerOut.model_validate(c) for c in customers],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


@router.get(
    "/{customer_id}/summary",
    response_model=CustomerSummary,
    summary="Customer order summary",
    description=(
        "Order count and first/last order date consider orders of any status. "
        "`total_spend` only counts non-cancelled orders, consistent with the /metrics endpoints."
    ),
    responses={404: {"description": "Customer not found"}},
)
def get_customer_summary(customer_id: int, db: Session = Depends(get_db)) -> CustomerSummary:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {customer_id} not found.",
        )

    order_count, first_order_date, last_order_date = db.execute(
        select(func.count(Order.id), func.min(Order.order_date), func.max(Order.order_date)).where(
            Order.customer_id == customer_id
        )
    ).one()

    total_spend = db.execute(
        select(func.coalesce(func.sum(OrderItem.quantity * OrderItem.unit_price), 0))
        .join(Order, OrderItem.order_id == Order.id)
        .where(
            Order.customer_id == customer_id,
            Order.status.in_(OrderStatus.revenue_statuses()),
        )
    ).scalar_one()

    return CustomerSummary(
        customer_id=customer.id,
        name=customer.name,
        email=customer.email,
        order_count=order_count,
        total_spend=round(float(total_spend), 2),
        first_order_date=first_order_date,
        last_order_date=last_order_date,
    )
