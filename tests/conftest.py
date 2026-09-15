"""Shared pytest fixtures.

Environment variables MUST be set before anything under `app` is imported, since
`app.config.Settings` reads them at import time. This gives every test an isolated,
in-memory SQLite database (never touching a real `sales_metrics.db` file) and a known
API key, entirely independent of any local `.env` file.
"""

import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["API_KEY"] = "test-api-key"
os.environ["CACHE_TTL_SECONDS"] = "60"

from datetime import date, datetime  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.cache import cache_clear  # noqa: E402
from app.database import SessionLocal, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Customer, Order, OrderItem, OrderStatus, Product  # noqa: E402

TEST_API_KEY = "test-api-key"


def _override_get_db():
    """Dependency override so every request in the test suite uses the isolated test DB
    session factory explicitly, rather than relying implicitly on module import order."""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _seed_fixture_data() -> None:
    """Insert a small, hand-computed dataset so tests can assert on exact numbers.

    Layout (all monetary figures chosen to make manual verification easy):

    Customers: Alice, Bob, Carla, Diego, Elena, Fatima (ids 1-6, in that order).
    Products: Widget A ($10), Widget B ($20), Widget C ($50) (ids 1-3).

    Orders (non-cancelled orders count towards revenue; PENDING counts, CANCELLED doesn't):
      #1 Alice   2024-01-05 10:00  COMPLETED  -> 2x Widget A ($20) + 1x Widget B ($20) = $40
      #2 Bob     2024-01-05 15:00  COMPLETED  -> 1x Widget A ($10)                     = $10
      #3 Alice   2024-01-20 09:30  COMPLETED  -> 1x Widget C ($50)                     = $50
      #4 Carla   2024-02-10 12:00  COMPLETED  -> 3x Widget B ($60)                     = $60
      #5 Diego   2024-02-15 08:00  CANCELLED  -> 5x Widget A ($50, excluded from revenue)
      #6 Elena   2024-02-20 18:45  PENDING    -> 2x Widget C ($100)                    = $100

    Expected revenue: day(2024-01-05)=$50, day(2024-01-20)=$50, day(2024-02-10)=$60,
    day(2024-02-20)=$100; month(2024-01)=$100 (3 orders), month(2024-02)=$160 (2 orders);
    total = $260. Top products by revenue: Widget C ($150), Widget B ($80), Widget A ($30).
    """

    db = SessionLocal()
    try:
        alice = Customer(name="Alice Silva", email="alice@example.com", country="Brazil", signup_date=date(2023, 1, 10))
        bob = Customer(name="Bob Santos", email="bob@example.com", country="Brazil", signup_date=date(2023, 2, 15))
        carla = Customer(name="Carla Souza", email="carla@example.com", country="Portugal", signup_date=date(2023, 3, 20))
        diego = Customer(name="Diego Fernandes", email="diego@example.com", country="Argentina", signup_date=date(2023, 4, 5))
        elena = Customer(name="Elena Petrova", email="elena@example.com", country="Russia", signup_date=date(2023, 5, 25))
        fatima = Customer(name="Fatima Costa", email="fatima@example.com", country="Brazil", signup_date=date(2023, 6, 1))
        db.add_all([alice, bob, carla, diego, elena, fatima])
        db.commit()
        for c in (alice, bob, carla, diego, elena, fatima):
            db.refresh(c)

        widget_a = Product(name="Widget A", category="Electronics", unit_price=10.00)
        widget_b = Product(name="Widget B", category="Books", unit_price=20.00)
        widget_c = Product(name="Widget C", category="Home & Kitchen", unit_price=50.00)
        db.add_all([widget_a, widget_b, widget_c])
        db.commit()
        for p in (widget_a, widget_b, widget_c):
            db.refresh(p)

        order1 = Order(customer_id=alice.id, order_date=datetime(2024, 1, 5, 10, 0, 0), status=OrderStatus.COMPLETED)
        order2 = Order(customer_id=bob.id, order_date=datetime(2024, 1, 5, 15, 0, 0), status=OrderStatus.COMPLETED)
        order3 = Order(customer_id=alice.id, order_date=datetime(2024, 1, 20, 9, 30, 0), status=OrderStatus.COMPLETED)
        order4 = Order(customer_id=carla.id, order_date=datetime(2024, 2, 10, 12, 0, 0), status=OrderStatus.COMPLETED)
        order5 = Order(customer_id=diego.id, order_date=datetime(2024, 2, 15, 8, 0, 0), status=OrderStatus.CANCELLED)
        order6 = Order(customer_id=elena.id, order_date=datetime(2024, 2, 20, 18, 45, 0), status=OrderStatus.PENDING)
        db.add_all([order1, order2, order3, order4, order5, order6])
        db.commit()
        for o in (order1, order2, order3, order4, order5, order6):
            db.refresh(o)

        items = [
            OrderItem(order_id=order1.id, product_id=widget_a.id, quantity=2, unit_price=10.00),
            OrderItem(order_id=order1.id, product_id=widget_b.id, quantity=1, unit_price=20.00),
            OrderItem(order_id=order2.id, product_id=widget_a.id, quantity=1, unit_price=10.00),
            OrderItem(order_id=order3.id, product_id=widget_c.id, quantity=1, unit_price=50.00),
            OrderItem(order_id=order4.id, product_id=widget_b.id, quantity=3, unit_price=20.00),
            OrderItem(order_id=order5.id, product_id=widget_a.id, quantity=5, unit_price=10.00),
            OrderItem(order_id=order6.id, product_id=widget_c.id, quantity=2, unit_price=50.00),
        ]
        db.add_all(items)
        db.commit()
    finally:
        db.close()


@pytest.fixture(scope="session")
def client():
    """A TestClient backed by a single in-memory SQLite database, seeded once per test
    session with the fixture dataset documented in `_seed_fixture_data`."""

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        _seed_fixture_data()
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _reset_cache():
    """Ensure the in-process revenue cache never leaks state between tests."""

    cache_clear()
    yield
    cache_clear()


@pytest.fixture
def auth_headers() -> dict:
    return {"X-API-Key": TEST_API_KEY}
