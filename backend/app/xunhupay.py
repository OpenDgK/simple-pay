from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

from .config import settings


XUNHUPAY_PAID_STATUSES = {"OD"}
XUNHUPAY_FAILED_STATUSES = {"CD", "RD", "UD"}


def _stringify(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    return str(value)


def _canonical_body(params: dict[str, Any], secret: str) -> str:
    pairs: list[tuple[str, str]] = []
    for key, value in params.items():
        if key == "hash" or value is None:
            continue
        text = _stringify(value).strip()
        if text == "":
            continue
        pairs.append((key, text))
    body = "&".join(f"{key}={value}" for key, value in sorted(pairs, key=lambda item: item[0]))
    return f"{body}{secret}"


def sign_params(params: dict[str, Any], secret: str) -> str:
    return hashlib.md5(_canonical_body(params, secret).encode("utf-8")).hexdigest().lower()


def verify_xunhupay_signature(payload: dict[str, Any], secret: str) -> bool:
    received = str(payload.get("hash") or "")
    if not received or not secret:
        return False
    expected = sign_params(payload, secret)
    return hmac.compare_digest(expected.lower(), received.lower())


@dataclass
class XunhuPayCreateResult:
    xunhupay_order_no: str | None
    pay_body: str | None
    status: str
    raw: dict[str, Any]


class XunhuPayClient:
    def __init__(self) -> None:
        self.gateway_url = settings.xunhupay_gateway_url
        self.app_id = settings.xunhupay_app_id
        self.app_secret = settings.xunhupay_app_secret

    async def create_payment(
        self,
        *,
        order_no: str,
        title: str,
        amount: Decimal,
    ) -> XunhuPayCreateResult:
        required = {
            "XUNHUPAY_GATEWAY_URL": self.gateway_url,
            "XUNHUPAY_APP_ID": self.app_id,
            "XUNHUPAY_APP_SECRET": self.app_secret,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError(f"missing XunhuPay config: {', '.join(missing)}")

        payload: dict[str, Any] = {
            "version": settings.xunhupay_version,
            "appid": self.app_id,
            "trade_order_id": order_no,
            "total_fee": f"{amount:.2f}",
            "title": title[:120],
            "time": int(time.time()),
            "notify_url": settings.effective_xunhupay_notify_url,
            "return_url": settings.effective_xunhupay_return_url,
            "callback_url": settings.effective_xunhupay_return_url,
            "nonce_str": secrets.token_hex(16),
            "plugins": settings.xunhupay_plugins,
            "attach": order_no,
        }
        payload["hash"] = sign_params(payload, self.app_secret)

        async with httpx.AsyncClient(timeout=settings.xunhupay_request_timeout_seconds) as client:
            response = await client.post(self.gateway_url, json=payload)
            response.raise_for_status()
            data = response.json()

        if data.get("hash") and not verify_xunhupay_signature(data, self.app_secret):
            raise RuntimeError("XunhuPay response signature verification failed")
        if str(data.get("errcode")) != "0":
            raise RuntimeError(f"XunhuPay create payment failed: {data.get('errmsg') or data}")

        pay_body = data.get("url") or data.get("url_qrcode")
        return XunhuPayCreateResult(
            xunhupay_order_no=data.get("openid") or data.get("open_order_id"),
            pay_body=str(pay_body) if pay_body else None,
            status="progress",
            raw=data,
        )
