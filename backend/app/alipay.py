from __future__ import annotations

import base64
import json
import textwrap
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from .config import settings


ALIPAY_PAID_STATUSES = {"TRADE_SUCCESS", "TRADE_FINISHED"}
ALIPAY_FAILED_STATUSES = {"TRADE_CLOSED"}


@dataclass
class AlipayCreateResult:
    alipay_trade_no: str | None
    pay_body: str
    status: str
    raw: dict[str, Any]


def _normalize_key(raw: str, key_type: str) -> bytes:
    text = raw.strip().replace("\\n", "\n")
    if "-----BEGIN " in text:
        return text.encode("utf-8")
    compact = "".join(text.split())
    wrapped = "\n".join(textwrap.wrap(compact, 64))
    return f"-----BEGIN {key_type}-----\n{wrapped}\n-----END {key_type}-----\n".encode("utf-8")


def _load_private_key(raw: str):
    try:
        return serialization.load_pem_private_key(_normalize_key(raw, "PRIVATE KEY"), password=None)
    except ValueError:
        return serialization.load_pem_private_key(_normalize_key(raw, "RSA PRIVATE KEY"), password=None)


def _load_public_key(raw: str):
    return serialization.load_pem_public_key(_normalize_key(raw, "PUBLIC KEY"))


def _sign_content(params: dict[str, Any], *, exclude_sign_type: bool = False) -> str:
    excluded = {"sign"}
    if exclude_sign_type:
        excluded.add("sign_type")
    pairs = []
    for key, value in params.items():
        if key in excluded or value is None:
            continue
        text = str(value)
        if text == "":
            continue
        pairs.append((key, text))
    return "&".join(f"{key}={value}" for key, value in sorted(pairs, key=lambda item: item[0]))


def sign_alipay_params(params: dict[str, Any], private_key: str) -> str:
    key = _load_private_key(private_key)
    signature = key.sign(
        _sign_content(params, exclude_sign_type=True).encode(settings.alipay_charset),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("ascii")


def verify_alipay_signature(params: dict[str, Any], public_key: str) -> bool:
    sign = str(params.get("sign") or "")
    if not sign:
        return False
    try:
        key = _load_public_key(public_key)
        key.verify(
            base64.b64decode(sign),
            _sign_content(params, exclude_sign_type=True).encode(settings.alipay_charset),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except (ValueError, InvalidSignature, TypeError):
        return False


class AlipayClient:
    def __init__(self) -> None:
        self.gateway = settings.alipay_gateway_url
        self.private_key = settings.alipay_app_private_key

    def _check_config(self) -> None:
        if settings.alipay_sign_type != "RSA2":
            raise RuntimeError("only Alipay RSA2 sign type is supported")
        required = {
            "ALIPAY_APP_ID": settings.alipay_app_id,
            "ALIPAY_APP_PRIVATE_KEY": settings.alipay_app_private_key,
            "ALIPAY_PUBLIC_KEY": settings.alipay_public_key,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError(f"missing Alipay config: {', '.join(missing)}")

    async def create_payment(
        self,
        *,
        order_no: str,
        title: str,
        description: str,
        amount: Decimal,
    ) -> AlipayCreateResult:
        self._check_config()
        biz_content = {
            "out_trade_no": order_no,
            "total_amount": f"{amount:.2f}",
            "subject": title[:256],
            "body": description[:128],
            "product_code": settings.alipay_page_pay_product_code,
            "timeout_express": settings.alipay_timeout_express,
        }
        params: dict[str, Any] = {
            "app_id": settings.alipay_app_id,
            "method": "alipay.trade.page.pay",
            "format": "JSON",
            "charset": settings.alipay_charset,
            "sign_type": settings.alipay_sign_type,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "version": "1.0",
            "notify_url": settings.effective_alipay_notify_url,
            "return_url": settings.effective_alipay_return_url,
            "biz_content": json.dumps(biz_content, ensure_ascii=False, separators=(",", ":")),
        }
        params["sign"] = sign_alipay_params(params, self.private_key)
        pay_url = f"{self.gateway}?{urlencode(params)}"
        return AlipayCreateResult(
            alipay_trade_no=None,
            pay_body=pay_url,
            status="progress",
            raw={"gateway": self.gateway, "method": params["method"], "out_trade_no": order_no},
        )
