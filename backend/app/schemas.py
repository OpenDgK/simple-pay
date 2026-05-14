from __future__ import annotations

from pydantic import BaseModel, Field


class AdminLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class DeliveryUpdateRequest(BaseModel):
    pay_status: str | None = Field(default=None, pattern="^(pending|reviewing|paid|failed|expired)$")
    delivery_status: str = Field(pattern="^(pending|processing|delivered|cancelled)$")
    delivery_result: str | None = Field(default=None, max_length=10000)


class ProductRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=5000)
    amount_cents: int = Field(ge=1, le=100_000_000)
    currency: str = Field(default="CNY", pattern="^[A-Z]{3,16}$")
    active: bool = True
    sort_order: int = Field(default=100, ge=0, le=100_000)


class SiteContentUpdateRequest(BaseModel):
    content: dict[str, str] = Field(default_factory=dict)


class InventoryCreateRequest(BaseModel):
    product_id: int = Field(ge=1)
    account: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=255)
    note: str | None = Field(default=None, max_length=5000)


class InventoryBulkCreateRequest(BaseModel):
    product_id: int = Field(ge=1)
    items_text: str = Field(min_length=1, max_length=200000)


class InventoryUpdateRequest(BaseModel):
    account: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=255)
    note: str | None = Field(default=None, max_length=5000)
    status: str = Field(pattern="^(available|reserved|sold|disabled)$")
