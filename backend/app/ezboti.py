from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt

from .config import settings


@dataclass
class EzbotiCustomerInfo:
    customer_id: str | None
    pay_url: str | None
    is_paid: bool
    raw: dict[str, Any]


class EzbotiClient:
    def __init__(self) -> None:
        self.api_url = settings.ezboti_api_url
        self.project_id = settings.ezboti_project_id
        self.project_secret = settings.ezboti_project_secret

    def _ensure_configured(self) -> None:
        required = {
            "EZBOTI_API_URL": self.api_url,
            "EZBOTI_PROJECT_ID": self.project_id,
            "EZBOTI_PROJECT_SECRET": self.project_secret,
        }
        if not (settings.ezboti_paywall_id or settings.ezboti_paywall_alias):
            required["EZBOTI_PAYWALL_ID or EZBOTI_PAYWALL_ALIAS"] = ""
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError(f"missing Ezboti config: {', '.join(missing)}")

    def _encode(self, method: str, params: dict[str, Any]) -> str:
        payload = {
            "method": method,
            "params": params,
            "exp": int(time.time()) + 30 * 60,
            "nonce": secrets.token_urlsafe(16)[:32],
        }
        token = jwt.encode(
            payload,
            key=self.project_secret,
            algorithm="HS256",
            headers={"project_id": self.project_id},
        )
        return token if isinstance(token, str) else token.decode("utf-8")

    def _decode(self, token: str) -> dict[str, Any]:
        return jwt.decode(
            token,
            key=self.project_secret,
            options={"require": ["exp", "nonce"]},
            algorithms=["HS256"],
        )

    async def call(self, method: str, params: dict[str, Any]) -> Any:
        self._ensure_configured()
        body = self._encode(method, params)
        async with httpx.AsyncClient(timeout=settings.ezboti_request_timeout_seconds) as client:
            response = await client.post(
                f"{self.api_url.rstrip('/')}/{method}",
                content=body,
                headers={"Content-Type": "text/plain"},
            )
            response.raise_for_status()
        payload = self._decode(response.text)
        return payload["result"]

    def _customer_info_params(self, *, external_id: str, nickname: str | None) -> dict[str, Any]:
        params: dict[str, Any] = {
            "customer": {
                "external_id": external_id,
                "nickname": nickname or external_id,
            },
            "include_balance": True,
        }
        if settings.ezboti_paywall_id:
            params["paywall_id"] = settings.ezboti_paywall_id
        if settings.ezboti_paywall_alias:
            params["paywall_alias"] = settings.ezboti_paywall_alias
        if settings.ezboti_extra_paywall_id:
            params["extra_paywall_id"] = settings.ezboti_extra_paywall_id
        if settings.ezboti_extra_paywall_alias:
            params["extra_paywall_alias"] = settings.ezboti_extra_paywall_alias
        return params

    def _balance_matches(self, item: dict[str, Any]) -> bool:
        equity = item.get("equity") if isinstance(item.get("equity"), dict) else {}
        if settings.ezboti_equity_id and item.get("equity_id") != settings.ezboti_equity_id:
            return False
        if settings.ezboti_equity_alias and equity.get("alias") != settings.ezboti_equity_alias:
            return False
        if settings.ezboti_require_charged and not item.get("has_charged"):
            return False
        if settings.ezboti_require_usable and not item.get("is_balance_usable"):
            return False
        return True

    def _is_paid(self, result: dict[str, Any]) -> bool:
        balances = result.get("balance_s") if isinstance(result.get("balance_s"), list) else []
        return any(self._balance_matches(item) for item in balances if isinstance(item, dict))

    async def customer_info(self, *, external_id: str, nickname: str | None = None) -> EzbotiCustomerInfo:
        result = await self.call(
            "customer.info",
            self._customer_info_params(external_id=external_id, nickname=nickname),
        )
        home_link = result.get("home_link") if isinstance(result.get("home_link"), dict) else {}
        pay_url = home_link.get("url") or home_link.get("promoter_url")
        return EzbotiCustomerInfo(
            customer_id=str(result.get("id")) if result.get("id") else None,
            pay_url=str(pay_url) if pay_url else None,
            is_paid=self._is_paid(result),
            raw=result,
        )
