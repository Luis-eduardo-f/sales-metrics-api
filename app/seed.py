"""Generate a synthetic, referentially-consistent sales dataset using Faker.

Run as a module so relative imports work correctly:

    python -m app.seed              # seed only if the database is empty
    python -m app.seed --reset      # drop and recreate all tables first, then seed
    python -m app.seed --customers 300 --products 60 --orders 1200

A fixed random seed makes the generated dataset reproducible across runs and machines --
useful both for local development ("does the API return the numbers I expect?") and as the
basis for the test fixtures in tests/conftest.py (which seed a small, hand-computed dataset
of their own rather than relying on this script's output).
"""

from __future__ import annotations

import argparse
import random
from datetime import datetime, timedelta

from faker import Faker
from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, engine, init_db
from app.models import Customer, Order, OrderItem, OrderStatus, Product

DEFAULT_SEED = 42
DEFAULT_NUM_CUSTOMERS = 150
DEFAULT_NUM_PRODUCTS = 40
DEFAULT_NUM_ORDERS = 600
MIN_ITEMS_PER_ORDER = 1
MAX_ITEMS_PER_ORDER = 4  # averages ~2.5 items/order -> ~1500 order items at 600 orders

PRODUCT_CATEGORIES = [
    "Electronics",
    "Books",
    "Clothing",
    "Home & Kitchen",
    "Sports & Outdoors",
    "Toys & Games",
    "Beauty",
    "Groceries",
    "Automotive",
    "Office Supplies",
]

# Weighted so most orders complete normally, a minority are still pending, and a small
# fraction are cancelled -- cancelled orders are excluded from revenue metrics (see
# OrderStatus.revenue_statuses in app/models.py), which keeps the seeded data a meaningful
# exercise of that filter.
ORDER_STATUS_WEIGHTS = {
    OrderStatus.COMPLETED: 0.70,
    OrderStatus.PENDING: 0.20,
    OrderStatus.CANCELLED: 0.10,
}


def _weighted_status(rng: random.Random) -> OrderStatus:
    statuses = list(ORDER_STATUS_WEIGHTS.keys())
    weights = list(ORDER_STATUS_WEIGHTS.values())
    return rng.choices(statuses, weights=weights, k=1)[0]


def seed_customers(db: Session, fake: Faker, count: int) -> list[Customer]:
    customers = []
    for _ in range(count):
        signup_date = fake.date_between(start_date="-3y", end_date="today")
        customer = Customer(
            name=fake.name(),
            email=fake.unique.email(),
            country=fake.country(),
            signup_date=signup_date,
        )
        db.add(customer)
        customers.append(customer)
    db.commit()
    for c in customers:
        db.refresh(c)
    return customers


def seed_products(db: Session, fake: Faker, count: int) -> list[Product]:
    products = []
    for _ in range(count):
        category = fake.random_element(PRODUCT_CATEGORIES)
        product = Product(
            name=fake.unique.catch_phrase(),
            category=category,
            unit_price=round(random.uniform(5.0, 499.0), 2),
        )
        db.add(product)
        products.append(product)
    db.commit()
    for p in products:
        db.refresh(p)
    return products


def seed_orders_and_items(
    db: Session,
    fake: Faker,
    rng: random.Random,
    customers: list[Customer],
    products: list[Product],
    order_count: int,
) -> None:
    orders = []
    for _ in range(order_count):
        customer = rng.choice(customers)
        # Orders always happen on or after the customer's signup date.
        signup_dt = datetime.combine(customer.signup_date, datetime.min.time())
        earliest = max(signup_dt, datetime.now() - timedelta(days=3 * 365))
        days_span = max((datetime.now() - earliest).days, 1)
        order_date = earliest + timedelta(
            days=rng.randint(0, days_span), seconds=rng.randint(0, 86399)
        )
        order = Order(
            customer_id=customer.id,
            order_date=order_date,
            status=_weighted_status(rng),
        )
        db.add(order)
        orders.append(order)
    db.commit()
    for o in orders:
        db.refresh(o)

    items = []
    for order in orders:
        num_items = rng.randint(MIN_ITEMS_PER_ORDER, MAX_ITEMS_PER_ORDER)
        chosen_products = rng.sample(products, k=min(num_items, len(products)))
        for product in chosen_products:
            # Small +/-10% variance vs. the product's current price, simulating that prices
            # drift over time -- this is exactly why OrderItem snapshots its own unit_price
            # instead of joining against Product.unit_price at read time (see app/models.py).
            price_at_purchase = round(float(product.unit_price) * rng.uniform(0.9, 1.1), 2)
            items.append(
                OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    quantity=rng.randint(1, 5),
                    unit_price=price_at_purchase,
                )
            )
    db.add_all(items)
    db.commit()


def run(
    *,
    reset: bool = False,
    seed: int = DEFAULT_SEED,
    num_customers: int = DEFAULT_NUM_CUSTOMERS,
    num_products: int = DEFAULT_NUM_PRODUCTS,
    num_orders: int = DEFAULT_NUM_ORDERS,
) -> None:
    if reset:
        Base.metadata.drop_all(bind=engine)
    init_db()

    db = SessionLocal()
    try:
        existing = db.query(Customer).first()
        if existing is not None and not reset:
            print("Database already contains data -- skipping seed. Use --reset to wipe and reseed.")
            return

        fake = Faker()
        Faker.seed(seed)
        rng = random.Random(seed)
        random.seed(seed)  # covers direct `random.uniform` calls in this module

        print(f"Seeding {num_customers} customers...")
        customers = seed_customers(db, fake, num_customers)

        print(f"Seeding {num_products} products...")
        products = seed_products(db, fake, num_products)

        print(f"Seeding {num_orders} orders with order items...")
        seed_orders_and_items(db, fake, rng, customers, products, num_orders)

        item_count = db.query(OrderItem).count()
        print(f"Done. {num_customers} customers, {num_products} products, "
              f"{num_orders} orders, {item_count} order items.")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="Drop and recreate all tables before seeding.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Random seed for reproducibility.")
    parser.add_argument("--customers", type=int, default=DEFAULT_NUM_CUSTOMERS, dest="num_customers")
    parser.add_argument("--products", type=int, default=DEFAULT_NUM_PRODUCTS, dest="num_products")
    parser.add_argument("--orders", type=int, default=DEFAULT_NUM_ORDERS, dest="num_orders")
    args = parser.parse_args()

    run(
        reset=args.reset,
        seed=args.seed,
        num_customers=args.num_customers,
        num_products=args.num_products,
        num_orders=args.num_orders,
    )


if __name__ == "__main__":
    main()
