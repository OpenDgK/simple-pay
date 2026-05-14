from __future__ import annotations

import json
import mimetypes
import os
import re
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from .alipay import ALIPAY_FAILED_STATUSES, ALIPAY_PAID_STATUSES, AlipayClient, verify_alipay_signature
from .config import settings
from .daxpay import FAILED_STATUSES, PAID_STATUSES, DaxPayClient, verify_signed_payload
from .db import get_db, init_db, wait_for_database
from .email_service import send_account_delivery_email, send_manual_payment_review_email
from .ezboti import EzbotiClient
from .models import AppSetting, InventoryItem, Order, PaymentEvent, Product
from .pay188 import (
    PAY188_FAILED_STATUSES,
    PAY188_PAID_STATUSES,
    Pay188Client,
    normalize_callback_payload,
    safe_callback_payload,
    verify_pay188_callback,
)
from .schemas import (
    AdminLoginRequest,
    DeliveryUpdateRequest,
    InventoryBulkCreateRequest,
    InventoryCreateRequest,
    InventoryUpdateRequest,
    ProductRequest,
    SiteContentUpdateRequest,
)
from .security import (
    constant_time_equal,
    create_admin_token,
    random_code,
    random_token,
    require_admin,
    sha256_hex,
)
from .xunhupay import (
    XUNHUPAY_FAILED_STATUSES,
    XUNHUPAY_PAID_STATUSES,
    XunhuPayClient,
    verify_xunhupay_signature,
)

app = FastAPI(title=settings.app_name)

DEFAULT_CONTENT: dict[str, str] = {
    "heroBadge": "自动发货 · 邮箱收货",
    "feature1": "支付完成后自动发货",
    "feature2": "账号密码发送到邮箱",
    "feature3": "无库存时自动售罄",
    "flowTitle": "三步自动开通",
    "flowIntro": "选择套餐、填写邮箱并完成支付，系统会自动发货到邮箱。",
    "step1Title": "选择套餐",
    "step1Body": "Plus 或 Team 有库存时可购买，售罄会自动禁用。",
    "step2Title": "填写邮箱",
    "step2Body": "用于接收账号密码，请确认邮箱可正常收信。",
    "step3Title": "支付完成自动发货",
    "step3Body": "支付完成后，系统会自动把货物发送到您的邮箱。",
}

DEFAULT_PRODUCTS: list[dict[str, Any]] = [
    {
        "name": "PLUS一月",
        "description": "",
        "amount_cents": settings.product_price_cents,
        "currency": settings.product_currency,
        "sort_order": 10,
    },
    {
        "name": "Team一月",
        "description": "",
        "amount_cents": settings.product_price_cents,
        "currency": settings.product_currency,
        "sort_order": 20,
    },
]

if settings.cors_allow_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[item.strip() for item in settings.cors_allow_origins.split(",") if item.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.on_event("startup")
def _startup() -> None:
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    wait_for_database()
    init_db()
    db = next(get_db())
    try:
        _seed_default_data(db)
    finally:
        db.close()


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if settings.trusted_proxy_headers and forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "127.0.0.1"


def _amount_text(cents: int) -> str:
    return f"{Decimal(cents) / Decimal(100):.2f}"


def _amount_yuan(cents: int) -> Decimal:
    return (Decimal(cents) / Decimal(100)).quantize(Decimal("0.01"))


def _seed_default_data(db: Session) -> None:
    if not db.scalar(select(Product.id).limit(1)):
        for product in DEFAULT_PRODUCTS:
            db.add(
                Product(
                    name=product["name"],
                    description=product["description"] or None,
                    amount_cents=product["amount_cents"],
                    currency=product["currency"],
                    active=1,
                    sort_order=product["sort_order"],
                )
            )
    for key, value in DEFAULT_CONTENT.items():
        if not db.get(AppSetting, key):
            db.add(AppSetting(key=key, value=value))
    db.commit()


def _site_content(db: Session) -> dict[str, str]:
    content = dict(DEFAULT_CONTENT)
    rows = db.scalars(select(AppSetting)).all()
    content.update({row.key: row.value for row in rows})
    return content


def _release_expired_inventory(db: Session) -> None:
    cutoff = datetime.now() - timedelta(minutes=max(settings.inventory_reservation_minutes, 1))
    rows = db.scalars(
        select(InventoryItem)
        .where(InventoryItem.status == "reserved", InventoryItem.reserved_at < cutoff)
        .order_by(InventoryItem.id.asc())
    ).all()
    changed = False
    for item in rows:
        order = item.order
        if order and order.pay_status == "pending":
            order.pay_status = "expired"
            order.payment_error = "Inventory reservation expired before payment"
        if not order or order.pay_status in {"pending", "expired", "failed"}:
            item.status = "available"
            item.order_id = None
            item.reserved_at = None
            changed = True
    if changed:
        db.flush()


def _stock_counts(db: Session) -> dict[int, dict[str, int]]:
    rows = db.execute(
        select(InventoryItem.product_id, InventoryItem.status, func.count(InventoryItem.id))
        .group_by(InventoryItem.product_id, InventoryItem.status)
    ).all()
    counts: dict[int, dict[str, int]] = {}
    for product_id, status_text, count in rows:
        counts.setdefault(int(product_id), {"available": 0, "reserved": 0, "sold": 0, "disabled": 0})
        counts[int(product_id)][str(status_text)] = int(count)
    return counts


def _inventory_counts_for_product(db: Session, product_id: int) -> dict[str, int]:
    counts = _stock_counts(db).get(product_id, {})
    return {
        "available": int(counts.get("available", 0)),
        "reserved": int(counts.get("reserved", 0)),
        "sold": int(counts.get("sold", 0)),
        "disabled": int(counts.get("disabled", 0)),
    }


def _active_products(db: Session) -> list[Product]:
    return db.scalars(
        select(Product)
        .where(Product.active == 1)
        .order_by(Product.sort_order.asc(), Product.id.asc())
    ).all()


def _product_to_public(product: Product, counts: dict[str, int] | None = None) -> dict[str, Any]:
    counts = counts or {}
    stock_count = int(counts.get("available", 0))
    return {
        "id": product.id,
        "name": product.name,
        "description": product.description or "",
        "amount_cents": product.amount_cents,
        "priceText": _amount_text(product.amount_cents),
        "currency": product.currency,
        "stock_count": stock_count,
        "sold_out": stock_count <= 0,
    }


def _product_to_admin(product: Product, counts: dict[str, int] | None = None) -> dict[str, Any]:
    counts = counts or {}
    data = _product_to_public(product, counts)
    data.update(
        {
            "active": bool(product.active),
            "sort_order": product.sort_order,
            "stock_reserved": int(counts.get("reserved", 0)),
            "stock_sold": int(counts.get("sold", 0)),
            "stock_disabled": int(counts.get("disabled", 0)),
            "created_at": product.created_at.isoformat() if product.created_at else None,
            "updated_at": product.updated_at.isoformat() if product.updated_at else None,
        }
    )
    return data


def _selected_product(db: Session, product_id: int | None) -> Product:
    stmt = select(Product).where(Product.active == 1)
    if product_id is not None:
        product = db.scalar(stmt.where(Product.id == product_id))
        if not product:
            raise HTTPException(status_code=400, detail="Product is not available")
        return product
    product = db.scalar(stmt.order_by(Product.sort_order.asc(), Product.id.asc()).limit(1))
    if not product:
        raise HTTPException(status_code=400, detail="No active product is available")
    return product


def _reserve_inventory(db: Session, product: Product, order: Order) -> InventoryItem:
    item = db.scalar(
        select(InventoryItem)
        .where(InventoryItem.product_id == product.id, InventoryItem.status == "available")
        .order_by(InventoryItem.id.asc())
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if not item:
        raise HTTPException(status_code=409, detail="该商品已售罄")
    item.status = "reserved"
    item.order = order
    item.reserved_at = datetime.now()
    return item


def _delivery_text(product_name: str, account: str, password: str) -> str:
    return "\n".join(
        [
            f"商品：{product_name}",
            f"账号：{account}",
            f"密码：{password}",
        ]
    )


def _fulfill_paid_order(db: Session, order: Order) -> None:
    item = order.inventory_item
    if not item:
        product = db.scalar(
            select(Product)
            .where(
                Product.active == 1,
                Product.name == order.product_name,
                Product.amount_cents == order.amount_cents,
                Product.currency == order.currency,
            )
            .order_by(Product.sort_order.asc(), Product.id.asc())
            .limit(1)
        )
        if product:
            item = db.scalar(
                select(InventoryItem)
                .where(InventoryItem.product_id == product.id, InventoryItem.status == "available")
                .order_by(InventoryItem.id.asc())
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if item:
                item.order = order
                item.reserved_at = item.reserved_at or datetime.now()
        if not item:
            order.delivery_status = "pending"
            order.email_error = "没有找到可用库存，请手动处理"
            return

    item.status = "sold"
    item.sold_at = item.sold_at or datetime.now()
    order.delivery_status = "delivered"
    order.delivery_result = _delivery_text(order.product_name, item.account, item.password)

    if order.email_sent_at and not order.email_error:
        return
    try:
        send_account_delivery_email(
            to_email=order.contact,
            order_no=order.order_no,
            product_name=order.product_name,
            account=item.account,
            password=item.password,
        )
        order.email_sent_at = datetime.now()
        order.email_error = None
    except Exception as exc:
        order.email_error = str(exc)


def _release_inventory_for_order(order: Order) -> None:
    item = order.inventory_item
    if item and item.status == "reserved":
        item.status = "available"
        item.order_id = None
        item.reserved_at = None


def _inventory_to_admin(item: InventoryItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "product_id": item.product_id,
        "order_no": item.order.order_no if item.order else None,
        "account": item.account,
        "password": item.password,
        "note": item.note,
        "status": item.status,
        "reserved_at": item.reserved_at.isoformat() if item.reserved_at else None,
        "sold_at": item.sold_at.isoformat() if item.sold_at else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def _parse_inventory_lines(text: str) -> list[tuple[str, str]]:
    parsed: list[tuple[str, str]] = []
    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        for separator in ["----", "|", ",", "\t"]:
            if separator in line:
                account, password = line.split(separator, 1)
                break
        else:
            parts = line.split(maxsplit=1)
            if len(parts) != 2:
                raise HTTPException(status_code=400, detail=f"第 {line_no} 行格式错误，请使用：账号 密码")
            account, password = parts
        account = account.strip()
        password = password.strip()
        if not account or not password:
            raise HTTPException(status_code=400, detail=f"第 {line_no} 行缺少账号或密码")
        parsed.append((account[:255], password[:255]))
    if not parsed:
        raise HTTPException(status_code=400, detail="没有可导入的库存")
    return parsed


def _order_to_public(order: Order, *, include_contact: bool = True) -> dict[str, Any]:
    return {
        "order_no": order.order_no,
        "contact": order.contact if include_contact else None,
        "requirement": order.requirement if include_contact else None,
        "remark": order.remark if include_contact else None,
        "product_name": order.product_name,
        "amount_cents": order.amount_cents,
        "amount_text": _amount_text(order.amount_cents),
        "currency": order.currency,
        "pay_status": order.pay_status,
        "pay_channel": order.pay_channel,
        "delivery_status": order.delivery_status,
        "delivery_result": order.delivery_result,
        "has_upload": bool(order.stored_filename),
        "original_filename": order.original_filename,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
    }


def _order_to_admin(order: Order) -> dict[str, Any]:
    data = _order_to_public(order)
    data.update(
        {
            "id": order.id,
            "content_type": order.content_type,
            "file_size": order.file_size,
            "daxpay_order_no": order.daxpay_order_no,
            "pay_body": order.pay_body,
            "pay_channel": order.pay_channel,
            "payment_error": order.payment_error,
            "updated_at": order.updated_at.isoformat() if order.updated_at else None,
            "email_sent_at": order.email_sent_at.isoformat() if order.email_sent_at else None,
            "email_error": order.email_error,
            "inventory_item": _inventory_to_admin(order.inventory_item) if order.inventory_item else None,
            "file_download_url": (
                f"{settings.admin_api_prefix}/orders/{order.order_no}/file"
                if order.stored_filename
                else None
            ),
        }
    )
    return data


def _make_order_no() -> str:
    return f"SOP{datetime.now():%Y%m%d%H%M%S}{random_code(6)}"


def _safe_ext(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if not ext and filename:
        guessed = mimetypes.guess_extension(filename)
        ext = guessed or ""
    return ext


def _validate_upload_meta(file: UploadFile) -> str:
    ext = _safe_ext(file.filename or "")
    if ext not in settings.allowed_extensions:
        allowed = ", ".join(sorted(settings.allowed_extensions))
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {allowed}")
    content_type = file.content_type or "application/octet-stream"
    if not any(content_type == item or content_type.startswith(item) for item in settings.allowed_mime_prefixes):
        raise HTTPException(status_code=400, detail="Unsupported file MIME type")
    return ext


async def _save_upload(file: UploadFile, order_no: str) -> tuple[str, int]:
    ext = _validate_upload_meta(file)
    date_dir = settings.upload_dir / datetime.now().strftime("%Y%m%d")
    date_dir.mkdir(parents=True, exist_ok=True)
    stored = f"{order_no}_{uuid.uuid4().hex}{ext}"
    target = date_dir / stored
    total = 0
    with target.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > settings.max_upload_bytes:
                out.close()
                target.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Uploaded file is too large")
            out.write(chunk)
    return str(target.relative_to(settings.upload_dir)), total


def _find_order_by_lookup(db: Session, order_no: str, query_code: str) -> Order:
    order = db.scalar(select(Order).where(Order.order_no == order_no))
    if not order or not constant_time_equal(order.query_code_hash, sha256_hex(query_code.upper())):
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config")
def public_config(db: Session = Depends(get_db)) -> dict[str, Any]:
    _release_expired_inventory(db)
    db.commit()
    products = _active_products(db)
    first_product = products[0] if products else None
    stock_counts = _stock_counts(db)
    return {
        "appName": settings.app_name,
        "productName": first_product.name if first_product else settings.product_name,
        "productDescription": first_product.description if first_product else settings.product_description,
        "priceCents": first_product.amount_cents if first_product else settings.product_price_cents,
        "priceText": _amount_text(first_product.amount_cents if first_product else settings.product_price_cents),
        "currency": first_product.currency if first_product else settings.product_currency,
        "products": [_product_to_public(product, stock_counts.get(product.id)) for product in products],
        "content": _site_content(db),
        "paymentMode": settings.payment_mode,
        "maxUploadMb": settings.max_upload_mb,
        "allowedUploadExtensions": sorted(settings.allowed_extensions),
        "adminPanelPath": settings.admin_panel_path,
        "adminApiPrefix": settings.admin_api_prefix,
    }


@app.get("/api/payments/qr")
def payment_qr(data: str = Query(..., min_length=1, max_length=2048)) -> Response:
    import qrcode
    import qrcode.image.svg

    img = qrcode.make(data, image_factory=qrcode.image.svg.SvgPathImage, border=2)
    stream = BytesIO()
    img.save(stream)
    return Response(
        content=stream.getvalue(),
        media_type="image/svg+xml",
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/orders")
async def create_order(
    request: Request,
    contact: str = Form(..., min_length=1, max_length=255),
    product_id: int | None = Form(default=None),
    requirement: str = Form(default="", max_length=10000),
    remark: str | None = Form(default=None, max_length=5000),
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _release_expired_inventory(db)
    product = _selected_product(db, product_id)
    order_no = _make_order_no()
    query_code = random_code(10)
    query_token = random_token(32)
    requirement_text = requirement.strip() or product.description or product.name

    stored_filename: str | None = None
    file_size: int | None = None
    if file and file.filename:
        stored_filename, file_size = await _save_upload(file, order_no)

    order = Order(
        order_no=order_no,
        query_code_hash=sha256_hex(query_code),
        query_token_hash=sha256_hex(query_token),
        contact=contact.strip(),
        requirement=requirement_text,
        remark=remark.strip() if remark else None,
        product_name=product.name,
        amount_cents=product.amount_cents,
        currency=product.currency,
        original_filename=file.filename if file and file.filename else None,
        stored_filename=stored_filename,
        content_type=file.content_type if file and file.filename else None,
        file_size=file_size,
        pay_status="pending",
        delivery_status="pending",
    )
    db.add(order)
    db.flush()
    reserved_item = _reserve_inventory(db, product, order)

    try:
        if settings.payment_mode == "alipay":
            created = await AlipayClient().create_payment(
                order_no=order.order_no,
                title=product.name,
                description=order.requirement,
                amount=_amount_yuan(product.amount_cents),
            )
            order.daxpay_order_no = created.alipay_trade_no
            order.pay_body = created.pay_body
            order.pay_channel = "alipay"
        elif settings.payment_mode == "xunhupay":
            created = await XunhuPayClient().create_payment(
                order_no=order.order_no,
                title=product.name,
                amount=_amount_yuan(product.amount_cents),
            )
            order.daxpay_order_no = created.xunhupay_order_no
            order.pay_body = created.pay_body
            order.pay_channel = "xunhupay"
        elif settings.payment_mode == "pay188":
            created = await Pay188Client().create_payment(
                order_no=order.order_no,
                title=product.name,
                amount=_amount_yuan(product.amount_cents),
                return_url=f"{settings.public_base_url}/order/{query_token}",
            )
            order.daxpay_order_no = created.pay188_order_no
            order.pay_body = created.pay_body
            order.pay_channel = settings.pay188_payment_method
        elif settings.payment_mode == "ezboti":
            created = await EzbotiClient().customer_info(
                external_id=order.order_no,
                nickname=order.contact,
            )
            order.daxpay_order_no = created.customer_id
            order.pay_body = created.pay_url
            order.pay_channel = "ezboti"
        elif settings.payment_mode == "manual":
            order.pay_body = json.dumps(
                {
                    "qr_url": settings.manual_payment_qr_url,
                    "instructions": settings.manual_payment_instructions,
                },
                ensure_ascii=False,
            )
            order.pay_channel = "manual"
        else:
            created = await DaxPayClient().create_payment(
                order_no=order.order_no,
                title=product.name,
                description=order.requirement,
                amount=_amount_yuan(product.amount_cents),
                client_ip=_client_ip(request),
            )
            order.daxpay_order_no = created.daxpay_order_no
            order.pay_body = created.pay_body
            order.pay_channel = settings.daxpay_channel
        order.payment_error = None
    except Exception as exc:
        if reserved_item.status == "reserved":
            reserved_item.status = "available"
            reserved_item.order_id = None
            reserved_item.reserved_at = None
        order.payment_error = str(exc)
        db.commit()
        raise HTTPException(status_code=502, detail=f"Payment order creation failed: {exc}") from exc

    db.commit()
    db.refresh(order)

    return {
        **_order_to_public(order),
        "query_code": query_code,
        "query_token_url": f"{settings.public_base_url}/order/{query_token}",
        "pay_body": order.pay_body,
        "mock_payment": settings.payment_mode == "mock",
    }


@app.get("/api/orders/lookup")
def lookup_order(
    order_no: str = Query(..., min_length=4, max_length=64),
    query_code: str = Query(..., min_length=4, max_length=32),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    order = _find_order_by_lookup(db, order_no.strip(), query_code.strip())
    return _order_to_public(order)


@app.get("/api/orders/token/{token}")
def lookup_order_by_token(token: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not re.match(r"^[A-Za-z0-9_\-]{20,}$", token):
        raise HTTPException(status_code=404, detail="Order not found")
    order = db.scalar(select(Order).where(Order.query_token_hash == sha256_hex(token)))
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return _order_to_public(order)


@app.post("/api/payments/mock/{order_no}")
def mock_pay(order_no: str, query_code: str = Query(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    if settings.payment_mode != "mock":
        raise HTTPException(status_code=404, detail="Mock payment is disabled")
    order = _find_order_by_lookup(db, order_no, query_code)
    if order.pay_status == "expired":
        raise HTTPException(status_code=409, detail="订单库存占用已过期，请重新下单")
    order.pay_status = "paid"
    order.paid_at = datetime.now()
    _fulfill_paid_order(db, order)
    event = PaymentEvent(
        order=order,
        event_type="mock_paid",
        raw_payload=json.dumps({"order_no": order_no}, ensure_ascii=False),
        signature_valid=1,
    )
    db.add(event)
    db.commit()
    db.refresh(order)
    return _order_to_public(order)


@app.post("/api/payments/ezboti/sync/{order_no}")
async def ezboti_sync_payment(
    order_no: str,
    query_code: str = Query(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if settings.payment_mode != "ezboti":
        raise HTTPException(status_code=404, detail="Ezboti payment sync is disabled")
    order = _find_order_by_lookup(db, order_no, query_code)
    if order.pay_status == "expired":
        raise HTTPException(status_code=409, detail="订单库存占用已过期，请重新下单")
    if order.pay_status == "paid":
        return _order_to_public(order)

    info = await EzbotiClient().customer_info(external_id=order.order_no, nickname=order.contact)
    order.daxpay_order_no = info.customer_id or order.daxpay_order_no
    order.pay_body = info.pay_url or order.pay_body
    order.pay_channel = "ezboti"
    if info.is_paid:
        order.pay_status = "paid"
        order.paid_at = order.paid_at or datetime.now()
        _fulfill_paid_order(db, order)
        event_type = "ezboti_sync_paid"
    else:
        order.pay_status = "pending"
        event_type = "ezboti_sync_pending"
    db.add(
        PaymentEvent(
            order=order,
            event_type=event_type,
            raw_payload=json.dumps(info.raw, ensure_ascii=False),
            signature_valid=1,
        )
    )
    db.commit()
    db.refresh(order)
    return _order_to_public(order)


@app.post("/api/payments/manual/{order_no}")
def manual_payment_submit(
    order_no: str,
    query_code: str = Query(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if settings.payment_mode != "manual":
        raise HTTPException(status_code=404, detail="Manual payment is disabled")
    order = _find_order_by_lookup(db, order_no, query_code)
    if order.pay_status == "expired":
        raise HTTPException(status_code=409, detail="订单库存占用已过期，请重新下单")
    if order.pay_status == "paid":
        return _order_to_public(order)
    if order.pay_status in {"pending", "failed"}:
        order.pay_status = "reviewing"
        order.payment_error = None
        notify_error = None
        if settings.admin_notify_email:
            try:
                send_manual_payment_review_email(
                    to_email=settings.admin_notify_email,
                    order_no=order.order_no,
                    contact=order.contact,
                    product_name=order.product_name,
                    amount_text=_amount_text(order.amount_cents),
                    currency=order.currency,
                    admin_url=f"{settings.public_base_url}{settings.admin_panel_path}",
                )
            except Exception as exc:
                notify_error = str(exc)
        db.add(
            PaymentEvent(
                order=order,
                event_type="manual_payment_submitted",
                raw_payload=json.dumps({"order_no": order_no, "notify_error": notify_error}, ensure_ascii=False),
                signature_valid=1,
            )
        )
    db.commit()
    db.refresh(order)
    return _order_to_public(order)


@app.post("/api/orders/{order_no}/cancel")
async def cancel_order(
    order_no: str,
    query_code: str = Query(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    order = _find_order_by_lookup(db, order_no, query_code)
    if order.pay_status == "paid":
        return _order_to_public(order)
    if order.pay_status == "expired":
        _release_inventory_for_order(order)
        db.commit()
        db.refresh(order)
        return _order_to_public(order)

    if order.pay_channel == "ezboti" and settings.payment_mode == "ezboti":
        info = await EzbotiClient().customer_info(external_id=order.order_no, nickname=order.contact)
        order.daxpay_order_no = info.customer_id or order.daxpay_order_no
        order.pay_body = info.pay_url or order.pay_body
        if info.is_paid:
            order.pay_status = "paid"
            order.paid_at = order.paid_at or datetime.now()
            _fulfill_paid_order(db, order)
            db.add(
                PaymentEvent(
                    order=order,
                    event_type="ezboti_cancel_check_paid",
                    raw_payload=json.dumps(info.raw, ensure_ascii=False),
                    signature_valid=1,
                )
            )
            db.commit()
            db.refresh(order)
            return _order_to_public(order)

        db.add(
            PaymentEvent(
                order=order,
                event_type="ezboti_cancel_check_pending",
                raw_payload=json.dumps(info.raw, ensure_ascii=False),
                signature_valid=1,
            )
        )

    if order.pay_status == "pending":
        order.pay_status = "failed"
        order.payment_error = "用户关闭支付窗口，未检测到支付成功，库存已释放"
        _release_inventory_for_order(order)
        db.add(
            PaymentEvent(
                order=order,
                event_type="customer_cancelled",
                raw_payload=json.dumps({"order_no": order_no}, ensure_ascii=False),
                signature_valid=1,
            )
        )
    db.commit()
    db.refresh(order)
    return _order_to_public(order)


@app.post("/api/payments/daxpay/notify")
async def daxpay_notify(request: Request, db: Session = Depends(get_db)) -> PlainTextResponse:
    payload = await request.json()
    signature_valid = verify_signed_payload(payload, settings.daxpay_sign_secret)
    if not signature_valid:
        raise HTTPException(status_code=400, detail="Invalid DaxPay signature")

    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    biz_order_no = data.get("bizOrderNo") or data.get("attach")
    daxpay_order_no = data.get("orderNo")
    if not biz_order_no:
        raise HTTPException(status_code=400, detail="Missing bizOrderNo")

    order = db.scalar(select(Order).where(Order.order_no == str(biz_order_no)))
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    status_text = str(data.get("status") or "").lower()
    if status_text in PAID_STATUSES:
        order.pay_status = "paid"
        order.paid_at = order.paid_at or datetime.now()
        _fulfill_paid_order(db, order)
    elif status_text in FAILED_STATUSES:
        order.pay_status = "failed"
        _release_inventory_for_order(order)
    else:
        order.pay_status = "pending"
    order.daxpay_order_no = daxpay_order_no or order.daxpay_order_no
    order.pay_channel = data.get("channel") or order.pay_channel

    db.add(
        PaymentEvent(
            order=order,
            event_type="daxpay_notify",
            raw_payload=json.dumps(payload, ensure_ascii=False),
            signature_valid=1,
        )
    )
    db.commit()
    return PlainTextResponse("SUCCESS")


@app.post("/api/payments/alipay/notify")
async def alipay_notify(request: Request, db: Session = Depends(get_db)) -> PlainTextResponse:
    form = await request.form()
    payload = {key: str(value) for key, value in form.items()}
    signature_valid = verify_alipay_signature(payload, settings.alipay_public_key)
    if not signature_valid:
        return PlainTextResponse("failure", status_code=400)
    if payload.get("app_id") != settings.alipay_app_id:
        return PlainTextResponse("failure", status_code=400)

    order_no = payload.get("out_trade_no")
    if not order_no:
        return PlainTextResponse("failure", status_code=400)
    order = db.scalar(select(Order).where(Order.order_no == str(order_no)))
    if not order:
        return PlainTextResponse("failure", status_code=404)

    try:
        paid_amount = Decimal(str(payload.get("total_amount") or "0")).quantize(Decimal("0.01"))
    except Exception:
        return PlainTextResponse("failure", status_code=400)
    if paid_amount != _amount_yuan(order.amount_cents):
        db.add(
            PaymentEvent(
                order=order,
                event_type="alipay_notify_amount_mismatch",
                raw_payload=json.dumps(payload, ensure_ascii=False),
                signature_valid=1,
            )
        )
        db.commit()
        return PlainTextResponse("failure", status_code=400)

    trade_status = str(payload.get("trade_status") or "").upper()
    if trade_status in ALIPAY_PAID_STATUSES:
        order.pay_status = "paid"
        order.paid_at = order.paid_at or datetime.now()
        _fulfill_paid_order(db, order)
    elif trade_status in ALIPAY_FAILED_STATUSES:
        order.pay_status = "failed"
        _release_inventory_for_order(order)
    else:
        order.pay_status = "pending"
    order.daxpay_order_no = payload.get("trade_no") or order.daxpay_order_no
    order.pay_channel = "alipay"

    db.add(
        PaymentEvent(
            order=order,
            event_type="alipay_notify",
            raw_payload=json.dumps(payload, ensure_ascii=False),
            signature_valid=1,
        )
    )
    db.commit()
    return PlainTextResponse("success")


@app.post("/api/payments/xunhupay/notify")
async def xunhupay_notify(request: Request, db: Session = Depends(get_db)) -> PlainTextResponse:
    form = await request.form()
    payload = {key: str(value) for key, value in form.items()}
    if not verify_xunhupay_signature(payload, settings.xunhupay_app_secret):
        return PlainTextResponse("fail", status_code=400)
    if payload.get("appid") != settings.xunhupay_app_id:
        return PlainTextResponse("fail", status_code=400)

    order_no = payload.get("trade_order_id") or payload.get("attach")
    if not order_no:
        return PlainTextResponse("fail", status_code=400)
    order = db.scalar(select(Order).where(Order.order_no == str(order_no)))
    if not order:
        return PlainTextResponse("fail", status_code=404)

    try:
        paid_amount = Decimal(str(payload.get("total_fee") or "0")).quantize(Decimal("0.01"))
    except Exception:
        return PlainTextResponse("fail", status_code=400)
    if paid_amount != _amount_yuan(order.amount_cents):
        db.add(
            PaymentEvent(
                order=order,
                event_type="xunhupay_notify_amount_mismatch",
                raw_payload=json.dumps(payload, ensure_ascii=False),
                signature_valid=1,
            )
        )
        db.commit()
        return PlainTextResponse("fail", status_code=400)

    status_text = str(payload.get("status") or "").upper()
    if status_text in XUNHUPAY_PAID_STATUSES:
        order.pay_status = "paid"
        order.paid_at = order.paid_at or datetime.now()
        _fulfill_paid_order(db, order)
    elif status_text in XUNHUPAY_FAILED_STATUSES:
        order.pay_status = "failed"
        _release_inventory_for_order(order)
    else:
        order.pay_status = "pending"
    order.daxpay_order_no = payload.get("open_order_id") or order.daxpay_order_no
    order.pay_channel = "xunhupay"

    db.add(
        PaymentEvent(
            order=order,
            event_type="xunhupay_notify",
            raw_payload=json.dumps(payload, ensure_ascii=False),
            signature_valid=1,
        )
    )
    db.commit()
    return PlainTextResponse("success")


@app.post("/api/payments/pay188/notify")
async def pay188_notify(request: Request, db: Session = Depends(get_db)) -> PlainTextResponse:
    try:
        payload = await request.json()
    except Exception:
        form = await request.form()
        payload = {key: str(value) for key, value in form.items()}
    if not isinstance(payload, dict):
        return PlainTextResponse("fail", status_code=400)
    payload = {str(key): value for key, value in payload.items()}
    signature_valid = verify_pay188_callback(payload, settings.pay188_secret_key)
    payload = normalize_callback_payload(payload)
    if payload.get("merchantId") and str(payload.get("merchantId")) != settings.pay188_merchant_id:
        return PlainTextResponse("fail", status_code=400)

    order_no = (
        payload.get("merchantOrderId")
        or payload.get("out_trade_no")
        or payload.get("outTradeNo")
        or payload.get("trade_order_id")
        or payload.get("attach")
    )
    if not order_no:
        return PlainTextResponse("fail", status_code=400)
    order = db.scalar(select(Order).where(Order.order_no == str(order_no)))
    if not order:
        return PlainTextResponse("fail", status_code=404)
    if not signature_valid:
        db.add(
            PaymentEvent(
                order=order,
                event_type="pay188_notify_invalid_signature",
                raw_payload=safe_callback_payload(payload),
                signature_valid=0,
            )
        )
        db.commit()
        return PlainTextResponse("fail", status_code=400)

    amount_value = payload.get("amount") or payload.get("money") or payload.get("total_fee") or payload.get("paidAmount")
    if amount_value is not None and str(amount_value).strip() != "":
        try:
            paid_amount = Decimal(str(amount_value)).quantize(Decimal("0.01"))
        except Exception:
            return PlainTextResponse("fail", status_code=400)
        if paid_amount != _amount_yuan(order.amount_cents):
            db.add(
                PaymentEvent(
                    order=order,
                    event_type="pay188_notify_amount_mismatch",
                    raw_payload=safe_callback_payload(payload),
                    signature_valid=1,
                )
            )
            db.commit()
            return PlainTextResponse("fail", status_code=400)

    status_text = str(
        payload.get("status")
        or payload.get("trade_status")
        or payload.get("pay_status")
        or payload.get("state")
        or "success"
    ).lower()
    if status_text in PAY188_PAID_STATUSES:
        order.pay_status = "paid"
        order.paid_at = order.paid_at or datetime.now()
        _fulfill_paid_order(db, order)
    elif status_text in PAY188_FAILED_STATUSES:
        order.pay_status = "failed"
        _release_inventory_for_order(order)
    else:
        order.pay_status = "pending"
    order.daxpay_order_no = (
        payload.get("orderId")
        or payload.get("payOrderId")
        or payload.get("transactionId")
        or payload.get("trade_no")
        or order.daxpay_order_no
    )
    order.pay_channel = str(payload.get("paymentMethod") or payload.get("coinType") or order.pay_channel or "pay188")

    db.add(
        PaymentEvent(
            order=order,
            event_type="pay188_notify",
            raw_payload=safe_callback_payload(payload),
            signature_valid=1,
        )
    )
    db.commit()
    return PlainTextResponse("success")


@app.get(f"{settings.admin_api_prefix}/products", dependencies=[Depends(require_admin)])
def admin_products(db: Session = Depends(get_db)) -> dict[str, Any]:
    _release_expired_inventory(db)
    db.commit()
    stock_counts = _stock_counts(db)
    rows = db.scalars(select(Product).order_by(Product.sort_order.asc(), Product.id.asc())).all()
    return {"items": [_product_to_admin(product, stock_counts.get(product.id)) for product in rows]}


@app.post(f"{settings.admin_api_prefix}/products", dependencies=[Depends(require_admin)])
def create_product(payload: ProductRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    product = Product(
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
        amount_cents=payload.amount_cents,
        currency=payload.currency.upper(),
        active=1 if payload.active else 0,
        sort_order=payload.sort_order,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return _product_to_admin(product, _inventory_counts_for_product(db, product.id))


@app.patch(f"{settings.admin_api_prefix}/products/{{product_id}}", dependencies=[Depends(require_admin)])
def update_product(product_id: int, payload: ProductRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    product.name = payload.name.strip()
    product.description = payload.description.strip() if payload.description else None
    product.amount_cents = payload.amount_cents
    product.currency = payload.currency.upper()
    product.active = 1 if payload.active else 0
    product.sort_order = payload.sort_order
    db.commit()
    db.refresh(product)
    return _product_to_admin(product, _inventory_counts_for_product(db, product.id))


@app.get(f"{settings.admin_api_prefix}/inventory", dependencies=[Depends(require_admin)])
def admin_inventory(
    product_id: int | None = Query(default=None, ge=1),
    status_text: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _release_expired_inventory(db)
    db.commit()
    stmt = select(InventoryItem)
    if product_id:
        stmt = stmt.where(InventoryItem.product_id == product_id)
    if status_text:
        stmt = stmt.where(InventoryItem.status == status_text)
    rows = db.scalars(stmt.order_by(InventoryItem.id.desc()).limit(300)).all()
    return {"items": [_inventory_to_admin(item) for item in rows]}


@app.post(f"{settings.admin_api_prefix}/inventory", dependencies=[Depends(require_admin)])
def create_inventory_item(payload: InventoryCreateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    product = db.get(Product, payload.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    item = InventoryItem(
        product_id=product.id,
        account=payload.account.strip(),
        password=payload.password.strip(),
        note=payload.note.strip() if payload.note else None,
        status="available",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _inventory_to_admin(item)


@app.post(f"{settings.admin_api_prefix}/inventory/bulk", dependencies=[Depends(require_admin)])
def create_inventory_bulk(payload: InventoryBulkCreateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    product = db.get(Product, payload.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    rows = _parse_inventory_lines(payload.items_text)
    items = [
        InventoryItem(product_id=product.id, account=account, password=password, status="available")
        for account, password in rows
    ]
    db.add_all(items)
    db.commit()
    return {"created": len(items)}


@app.patch(f"{settings.admin_api_prefix}/inventory/{{item_id}}", dependencies=[Depends(require_admin)])
def update_inventory_item(item_id: int, payload: InventoryUpdateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    item = db.get(InventoryItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    if item.status in {"reserved", "sold"} and payload.status == "available":
        raise HTTPException(status_code=400, detail="Reserved or sold inventory cannot be reset here")
    item.account = payload.account.strip()
    item.password = payload.password.strip()
    item.note = payload.note.strip() if payload.note else None
    item.status = payload.status
    db.commit()
    db.refresh(item)
    return _inventory_to_admin(item)


@app.delete(f"{settings.admin_api_prefix}/inventory/{{item_id}}", dependencies=[Depends(require_admin)])
def delete_inventory_item(item_id: int, db: Session = Depends(get_db)) -> dict[str, str]:
    item = db.get(InventoryItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    if item.status in {"reserved", "sold"}:
        raise HTTPException(status_code=400, detail="Reserved or sold inventory cannot be deleted")
    db.delete(item)
    db.commit()
    return {"status": "deleted"}


@app.get(f"{settings.admin_api_prefix}/content", dependencies=[Depends(require_admin)])
def admin_content(db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"content": _site_content(db), "keys": list(DEFAULT_CONTENT.keys())}


@app.put(f"{settings.admin_api_prefix}/content", dependencies=[Depends(require_admin)])
def update_content(payload: SiteContentUpdateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    for key, default_value in DEFAULT_CONTENT.items():
        value = str(payload.content.get(key, default_value))[:2000]
        row = db.get(AppSetting, key)
        if row:
            row.value = value
        else:
            db.add(AppSetting(key=key, value=value))
    db.commit()
    return {"content": _site_content(db), "keys": list(DEFAULT_CONTENT.keys())}


@app.post(f"{settings.admin_api_prefix}/login")
def admin_login(payload: AdminLoginRequest) -> dict[str, str]:
    if not constant_time_equal(payload.username, settings.admin_username) or not constant_time_equal(
        payload.password,
        settings.admin_password,
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    return {"token": create_admin_token(settings.admin_username)}


@app.get(f"{settings.admin_api_prefix}/orders", dependencies=[Depends(require_admin)])
def admin_orders(
    q: str | None = None,
    pay_status: str | None = None,
    delivery_status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    stmt = select(Order)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Order.order_no.like(like), Order.contact.like(like), Order.requirement.like(like)))
    if pay_status:
        stmt = stmt.where(Order.pay_status == pay_status)
    if delivery_status:
        stmt = stmt.where(Order.delivery_status == delivery_status)
    rows = db.scalars(stmt.order_by(desc(Order.created_at)).offset(offset).limit(limit)).all()
    return {"items": [_order_to_admin(order) for order in rows], "limit": limit, "offset": offset}


@app.get(f"{settings.admin_api_prefix}/orders/{{order_no}}", dependencies=[Depends(require_admin)])
def admin_order_detail(order_no: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    order = db.scalar(select(Order).where(Order.order_no == order_no))
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return _order_to_admin(order)


@app.patch(f"{settings.admin_api_prefix}/orders/{{order_no}}/delivery", dependencies=[Depends(require_admin)])
def update_delivery(order_no: str, payload: DeliveryUpdateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    order = db.scalar(select(Order).where(Order.order_no == order_no))
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    auto_fulfilled = False
    if payload.pay_status:
        if payload.pay_status == "paid":
            order.pay_status = "paid"
            order.paid_at = order.paid_at or datetime.now()
            _fulfill_paid_order(db, order)
            auto_fulfilled = True
        elif payload.pay_status == "failed":
            order.pay_status = "failed"
            _release_inventory_for_order(order)
        else:
            order.pay_status = payload.pay_status

    if not auto_fulfilled or payload.delivery_result:
        order.delivery_status = payload.delivery_status
        order.delivery_result = payload.delivery_result
    db.commit()
    db.refresh(order)
    return _order_to_admin(order)


@app.get(f"{settings.admin_api_prefix}/orders/{{order_no}}/file", dependencies=[Depends(require_admin)])
def download_upload(order_no: str, db: Session = Depends(get_db)) -> FileResponse:
    order = db.scalar(select(Order).where(Order.order_no == order_no))
    if not order or not order.stored_filename:
        raise HTTPException(status_code=404, detail="File not found")
    file_path = (settings.upload_dir / order.stored_filename).resolve()
    root = settings.upload_dir.resolve()
    if os.path.commonpath([str(root), str(file_path)]) != str(root) or not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        file_path,
        filename=order.original_filename or file_path.name,
        media_type=order.content_type or "application/octet-stream",
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
