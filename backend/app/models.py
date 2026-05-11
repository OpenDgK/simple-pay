from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_no: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    query_code_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    query_token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)

    contact: Mapped[str] = mapped_column(String(255), nullable=False)
    requirement: Mapped[str] = mapped_column(Text, nullable=False)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)

    product_name: Mapped[str] = mapped_column(String(120), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(16), nullable=False, default="CNY")

    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stored_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)

    pay_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    delivery_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    delivery_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    email_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    email_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    daxpay_order_no: Mapped[str | None] = mapped_column(String(128), nullable=True)
    pay_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    pay_channel: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payment_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    events: Mapped[list["PaymentEvent"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
    )
    inventory_item: Mapped["InventoryItem | None"] = relationship(back_populates="order", uselist=False)


Index("ix_orders_pay_delivery_status", Order.pay_status, Order.delivery_status)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(16), nullable=False, default="CNY")
    active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


Index("ix_products_active_sort", Product.active, Product.sort_order)


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True, index=True)

    account: Mapped[str] = mapped_column(String(255), nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="available")

    reserved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sold_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    order: Mapped[Order | None] = relationship(back_populates="inventory_item")
    product: Mapped[Product] = relationship()


Index("ix_inventory_product_status", InventoryItem.product_id, InventoryItem.status)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class PaymentEvent(Base):
    __tablename__ = "payment_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_payload: Mapped[str] = mapped_column(Text, nullable=False)
    signature_valid: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    order: Mapped[Order] = relationship(back_populates="events")
