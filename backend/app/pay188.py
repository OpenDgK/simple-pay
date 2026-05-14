from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

from .config import settings


PAY188_PAID_STATUSES = {"paid", "success", "succeeded", "completed", "trade_success", "finished", "1", "true"}
PAY188_FAILED_STATUSES = {"failed", "fail", "cancelled", "canceled", "closed", "expired", "0", "false"}


def _stringify(value: Any) -> str:
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _non_empty_pairs(params: dict[str, Any], *, exclude: set[str] | None = None) -> list[tuple[str, str]]:
    excluded = exclude or set()
    pairs: list[tuple[str, str]] = []
    for key, value in params.items():
        if key in excluded or value is None:
            continue
        text = _stringify(value).strip()
        if text == "":
            continue
        pairs.append((key, text))
    return sorted(pairs, key=lambda item: item[0])


def _sign_base(params: dict[str, Any], *, exclude: set[str] | None = None) -> str:
    return "&".join(f"{key}={value}" for key, value in _non_empty_pairs(params, exclude=exclude))


def sign_standard_params(params: dict[str, Any], secret: str) -> str:
    base = _sign_base(params, exclude={"sign", "sign_type", "subject"})
    return hashlib.md5(f"{base}&key={secret}".encode("utf-8")).hexdigest().lower()


def verify_pay188_callback(payload: dict[str, Any], secret: str) -> bool:
    if not secret:
        return False
    for candidate in _callback_candidates(payload):
        received = str(candidate.get("sign") or "")
        if not received:
            continue
        for exclude in ({"sign"}, {"sign", "sign_type"}):
            base = _sign_base(candidate, exclude=exclude)
            expected_values = [
                hashlib.md5(f"{base}&key={secret}".encode("utf-8")).hexdigest(),
                hashlib.md5(f"{base}{secret}".encode("utf-8")).hexdigest(),
            ]
            if any(hmac.compare_digest(expected.lower(), received.lower()) for expected in expected_values):
                return True
    return False


def _callback_candidates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = [payload]
    for key in ("data", "payload", "order"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            merged = dict(nested)
            for top_key, top_value in payload.items():
                if top_key != key and top_key not in merged:
                    merged[top_key] = top_value
            candidates.append(merged)
    return candidates


def normalize_callback_payload(payload: dict[str, Any]) -> dict[str, Any]:
    for candidate in _callback_candidates(payload):
        if any(
            key in candidate
            for key in ("merchantOrderId", "out_trade_no", "outTradeNo", "trade_order_id", "attach")
        ):
            return candidate
    return payload


def safe_callback_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


@dataclass
class Pay188CreateResult:
    pay188_order_no: str | None
    pay_body: str
    status: str
    raw: dict[str, Any]


class Pay188Client:
    def __init__(self) -> None:
        self.gateway_url = settings.pay188_gateway_url
        self.merchant_id = settings.pay188_merchant_id
        self.secret = settings.pay188_secret_key

    async def create_payment(
        self,
        *,
        order_no: str,
        title: str,
        amount: Decimal,
    ) -> Pay188CreateResult:
        required = {
            "PAY188_GATEWAY_URL": self.gateway_url,
            "PAY188_MERCHANT_ID": self.merchant_id,
            "PAY188_SECRET_KEY": self.secret,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError(f"missing 188Pay config: {', '.join(missing)}")

        payload: dict[str, Any] = {
            "merchantId": self.merchant_id,
            "merchantOrderId": order_no,
            "amount": f"{amount:.2f}",
            "paymentMethod": settings.pay188_payment_method,
            "notifyUrl": settings.effective_pay188_notify_url,
            "returnUrl": settings.effective_pay188_return_url,
            "subject": title[:120],
        }
        if settings.pay188_coin_type:
            payload["coinType"] = settings.pay188_coin_type
        payload["sign"] = sign_standard_params(payload, self.secret)

        async with httpx.AsyncClient(
            timeout=settings.pay188_request_timeout_seconds,
            follow_redirects=False,
        ) as client:
            response = await client.post(self.gateway_url, json=payload)

        if response.status_code in {301, 302, 303, 307, 308}:
            location = response.headers.get("location")
            if not location:
                raise RuntimeError("188Pay redirect response missing Location header")
            return Pay188CreateResult(
                pay188_order_no=None,
                pay_body=str(response.url.join(location)),
                status="progress",
                raw={"status_code": response.status_code, "location": location},
            )

        response.raise_for_status()
        data = response.json()
        code = data.get("code")
        if data.get("success") is False or (code not in {None, ""} and str(code) not in {"0", "200"}):
            raise RuntimeError(f"188Pay create payment failed: {data.get('message') or data.get('msg') or data}")

        body = data.get("data") if isinstance(data.get("data"), dict) else data
        cashier_url = body.get("cashierUrl") or body.get("cashier_url") or body.get("url") or body.get("payUrl")
        if not cashier_url:
            raise RuntimeError(f"188Pay create payment response missing cashierUrl: {data}")

        return Pay188CreateResult(
            pay188_order_no=body.get("orderId") or body.get("id"),
            pay_body=str(cashier_url),
            status=str(body.get("status") or "progress"),
            raw=data,
        )
