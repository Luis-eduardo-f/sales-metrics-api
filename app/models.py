"""SQLAlchemy ORM models for the sales dataset.

Schema (simplified ER diagram)::

    Customer 1---* Order 1---* OrderItem *---1 Product

- A Customer places many Orders.
- An Order has many OrderItems (one per product line).
- OrderItem.unit_price is captured at the time of purchase (it is intentionally NOT looked up
  from Product.unit_price at query time), mirroring how real order systems snapshot pricing so
  that historical revenue doesn't change if a product's price changes later.
"""

import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class OrderStatus(str, enum.Enum):
    """Lifecycle status of an order."""

    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

    # Statuses that count towards revenue metrics. Cancelled orders never generated real
    # revenue, so they are excluded from every /metrics/* aggregation.
    @classmethod
    def revenue_statuses(cls) -> tuple["OrderStatus", ...]:
        return (cls.PENDING, cls.COMPLETED)


class Customer(Base):
    """A person who can place orders."""

    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    country: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    signup_date: Mapped[date] = mapped_column(Date, nullable=False)

    orders: Mapped[list["Order"]] = relationship(back_populates="customer")


class Product(Base):
    """An item that can be sold."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    order_items: Mapped[list["OrderItem"]] = relationship(back_populates="product")


class Order(Base):
    """A purchase made by a customer, composed of one or more OrderItems."""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False, index=True)
    order_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    status: Mapped[OrderStatus] = mapped_column(
        SAEnum(OrderStatus, name="order_status", native_enum=False, length=20),
        nullable=False,
        default=OrderStatus.COMPLETED,
    )

    customer: Mapped["Customer"] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    """A single product line within an Order."""

    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(nullable=False)
    # Price per unit at the moment of purchase (see module docstring).
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    order: Mapped["Order"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship(back_populates="order_items")
