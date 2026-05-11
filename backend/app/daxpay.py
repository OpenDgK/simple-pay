from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

import httpx

from .config import settings


PAID_STATUSES = {"pay_success", "success", "paid", "finish", "completed"}
FAILED_STATUSES = {"fail", "failed", "close", "closed", "cancel", "canceled", "cancelled"}


def _stringify(value: Any, *, sort_nested: bool = True) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        return format(value.normalize(), "f").rstrip("0").rstrip(".")
    if isinstance(value, float):
        text = ("%f" % value).rstrip("0").rstrip(".")
        return text or "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=sort_nested)
    return str(value)


def _canonical_pairs(params: dict[str, Any], *, sort_nested: bool = True) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for key, value in params.items():
        if key.lower() == "sign" or value is None:
            continue
        text = _stringify(value, sort_nested=sort_nested)
        text = text.replace('"', "").replace("\\", "")
        pairs.append((key, text))
    return sorted(pairs, key=lambda item: item[0].lower())


def sign_params(params: dict[str, Any], secret: str, sign_type: str | None = None, *, sort_nested: bool = True) -> str:
    sign_type = (sign_type or settings.daxpay_sign_type).upper()
    body = "&".join(f"{key}={value}" for key, value in _canonical_pairs(params, sort_nested=sort_nested))
    body = f"{body}&key={secret}".upper()
    if sign_type == "MD5":
        return hashlib.md5(body.encode("utf-8")).hexdigest()
    if sign_type in {"HMAC_SHA256", "HMACSHA256"}:
        return hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
    raise ValueError(f"Unsupported DaxPay sign type: {sign_type}")


def verify_signed_payload(payload: dict[str, Any], secret: str) -> bool:
    sign = str(payload.get("sign") or "")
    if not sign:
        return False
    expected = sign_params(payload, secret, sort_nested=False)
    return hmac.compare_digest(expected.lower(), sign.lower())


@dataclass
class DaxPayCreateResult:
    daxpay_order_no: str | None
    pay_body: str | None
    status: str
    raw: dict[str, Any]


class DaxPayClient:
    def __init__(self) -> None:
        self.api_url = settings.daxpay_api_url
        self.secret = settings.daxpay_sign_secret

    def _base_payload(self, client_ip: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "mchNo": settings.daxpay_mch_no,
            "appId": settings.daxpay_app_id,
            "clientIp": client_ip,
            "reqTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "nonceStr": secrets.token_hex(8),
        }
        return {key: value for key, value in payload.items() if value}

    async def create_payment(
        self,
        *,
        order_no: str,
        title: str,
        description: str,
        amount: Decimal,
        client_ip: str,
    ) -> DaxPayCreateResult:
        if settings.payment_mode == "mock":
            return DaxPayCreateResult(
                daxpay_order_no=f"MOCK_{order_no}",
                pay_body=f"{settings.public_base_url}/pay/mock?order_no={order_no}",
                status="progress",
                raw={"mock": True, "bizOrderNo": order_no},
            )

        required = {
            "DAXPAY_API_URL": self.api_url,
            "DAXPAY_APP_ID": settings.daxpay_app_id,
            "DAXPAY_MCH_NO": settings.daxpay_mch_no,
            "DAXPAY_SIGN_SECRET": self.secret,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError(f"missing DaxPay config: {', '.join(missing)}")

        payload = {
            **self._base_payload(client_ip),
            "bizOrderNo": order_no,
            "title": title,
            "description": description[:500],
            "allocation": False,
            "channel": settings.daxpay_channel,
            "method": settings.daxpay_method,
            "amount": f"{amount:.2f}",
            "attach": order_no,
            "returnUrl": settings.effective_daxpay_return_url,
            "notifyUrl": settings.effective_daxpay_notify_url,
        }
        payload["sign"] = sign_params(payload, self.secret)

        async with httpx.AsyncClient(timeout=settings.daxpay_request_timeout_seconds) as client:
            response = await client.post(f"{self.api_url}/unipay/pay", json=payload)
            response.raise_for_status()
            data = response.json()

        if data.get("sign") and not verify_signed_payload(data, self.secret):
            raise RuntimeError("DaxPay response signature verification failed")
        if data.get("code") != 0:
            raise RuntimeError(f"DaxPay create payment failed: {data.get('msg') or data}")

        biz_data = data.get("data") or {}
        return DaxPayCreateResult(
            daxpay_order_no=biz_data.get("orderNo"),
            pay_body=biz_data.get("payBody"),
            status=biz_data.get("status") or "progress",
            raw=data,
        )
