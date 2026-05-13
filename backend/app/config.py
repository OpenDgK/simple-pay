from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


def _getenv(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return default if value is None else value.strip()


def _get_bool(name: str, default: bool = False) -> bool:
    value = _getenv(name, str(default)).lower()
    return value in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    value = _getenv(name, str(default))
    try:
        return int(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    app_name: str = _getenv("APP_NAME", "Simple Order Pay")
    public_base_url: str = _getenv("PUBLIC_BASE_URL", "http://127.0.0.1:3001").rstrip("/")
    app_secret: str = _getenv("APP_SECRET", "")

    product_name: str = _getenv("PRODUCT_NAME", "PLUS一月")
    product_description: str = _getenv(
        "PRODUCT_DESCRIPTION",
        "",
    )
    product_price_cents: int = _get_int("PRODUCT_PRICE_CENTS", 9900)
    product_currency: str = _getenv("PRODUCT_CURRENCY", "CNY")
    inventory_reservation_minutes: int = _get_int("INVENTORY_RESERVATION_MINUTES", 10)

    admin_username: str = _getenv("ADMIN_USERNAME", "admin")
    admin_password: str = _getenv("ADMIN_PASSWORD", "")
    admin_panel_path: str = _getenv("ADMIN_PANEL_PATH", "/ops-7q4-panel")
    admin_api_prefix: str = _getenv("ADMIN_API_PREFIX", "/api/order-ops-7q4")

    mysql_host: str = _getenv("MYSQL_HOST", "mysql")
    mysql_port: int = _get_int("MYSQL_PORT", 3306)
    mysql_database: str = _getenv("MYSQL_DATABASE", "simple_order_pay")
    mysql_user: str = _getenv("MYSQL_USER", "simple_order_pay")
    mysql_password: str = _getenv("MYSQL_PASSWORD", "")
    database_url_override: str = _getenv("DATABASE_URL", "")

    upload_dir: Path = Path(_getenv("UPLOAD_DIR", "/app/uploads"))
    max_upload_mb: int = _get_int("MAX_UPLOAD_MB", 20)
    allowed_upload_extensions: str = _getenv(
        "ALLOWED_UPLOAD_EXTENSIONS",
        ".jpg,.jpeg,.png,.pdf,.doc,.docx,.xls,.xlsx,.zip,.txt",
    )
    allowed_upload_mime_prefixes: str = _getenv(
        "ALLOWED_UPLOAD_MIME_PREFIXES",
        "image/,application/pdf,application/zip,application/vnd,application/msword,text/plain",
    )

    payment_mode: str = _getenv("PAYMENT_MODE", "mock").lower()

    manual_payment_qr_url: str = _getenv("MANUAL_PAYMENT_QR_URL", "")
    manual_payment_instructions: str = _getenv(
        "MANUAL_PAYMENT_INSTRUCTIONS",
        "请扫码付款，付款后点击“我已付款，等待确认”。管理员确认到账后会自动发货。",
    )

    alipay_gateway_url: str = _getenv("ALIPAY_GATEWAY_URL", "https://openapi.alipay.com/gateway.do").rstrip("/")
    alipay_app_id: str = _getenv("ALIPAY_APP_ID", "")
    alipay_app_private_key: str = _getenv("ALIPAY_APP_PRIVATE_KEY", "")
    alipay_public_key: str = _getenv("ALIPAY_PUBLIC_KEY", "")
    alipay_notify_url: str = _getenv("ALIPAY_NOTIFY_URL", "")
    alipay_return_url: str = _getenv("ALIPAY_RETURN_URL", "")
    alipay_sign_type: str = _getenv("ALIPAY_SIGN_TYPE", "RSA2").upper()
    alipay_charset: str = _getenv("ALIPAY_CHARSET", "utf-8")
    alipay_page_pay_product_code: str = _getenv("ALIPAY_PAGE_PAY_PRODUCT_CODE", "FAST_INSTANT_TRADE_PAY")
    alipay_timeout_express: str = _getenv("ALIPAY_TIMEOUT_EXPRESS", "30m")

    daxpay_api_url: str = _getenv("DAXPAY_API_URL", "").rstrip("/")
    daxpay_app_id: str = _getenv("DAXPAY_APP_ID", "")
    daxpay_mch_no: str = _getenv("DAXPAY_MCH_NO", "")
    daxpay_sign_secret: str = _getenv("DAXPAY_SIGN_SECRET", "")
    daxpay_notify_url: str = _getenv("DAXPAY_NOTIFY_URL", "")
    daxpay_return_url: str = _getenv("DAXPAY_RETURN_URL", "")
    daxpay_sign_type: str = _getenv("DAXPAY_SIGN_TYPE", "HMAC_SHA256").upper()
    daxpay_channel: str = _getenv("DAXPAY_CHANNEL", "wechat_pay")
    daxpay_method: str = _getenv("DAXPAY_METHOD", "qrcode")
    daxpay_request_timeout_seconds: int = _get_int("DAXPAY_REQUEST_TIMEOUT_SECONDS", 15)

    xunhupay_gateway_url: str = _getenv("XUNHUPAY_GATEWAY_URL", "https://api.xunhupay.com/payment/do.html").rstrip("/")
    xunhupay_app_id: str = _getenv("XUNHUPAY_APP_ID", "")
    xunhupay_app_secret: str = _getenv("XUNHUPAY_APP_SECRET", "")
    xunhupay_notify_url: str = _getenv("XUNHUPAY_NOTIFY_URL", "")
    xunhupay_return_url: str = _getenv("XUNHUPAY_RETURN_URL", "")
    xunhupay_version: str = _getenv("XUNHUPAY_VERSION", "1.1")
    xunhupay_plugins: str = _getenv("XUNHUPAY_PLUGINS", "simple-order-pay")
    xunhupay_request_timeout_seconds: int = _get_int("XUNHUPAY_REQUEST_TIMEOUT_SECONDS", 15)

    ezboti_api_url: str = _getenv("EZBOTI_API_URL", "https://revenue.ezboti.com/api/v1/server").rstrip("/")
    ezboti_project_id: str = _getenv("EZBOTI_PROJECT_ID", "")
    ezboti_project_secret: str = _getenv("EZBOTI_PROJECT_SECRET", "")
    ezboti_paywall_id: str = _getenv("EZBOTI_PAYWALL_ID", "")
    ezboti_paywall_alias: str = _getenv("EZBOTI_PAYWALL_ALIAS", "")
    ezboti_extra_paywall_id: str = _getenv("EZBOTI_EXTRA_PAYWALL_ID", "")
    ezboti_extra_paywall_alias: str = _getenv("EZBOTI_EXTRA_PAYWALL_ALIAS", "")
    ezboti_equity_id: str = _getenv("EZBOTI_EQUITY_ID", "")
    ezboti_equity_alias: str = _getenv("EZBOTI_EQUITY_ALIAS", "")
    ezboti_require_charged: bool = _get_bool("EZBOTI_REQUIRE_CHARGED", True)
    ezboti_require_usable: bool = _get_bool("EZBOTI_REQUIRE_USABLE", True)
    ezboti_request_timeout_seconds: int = _get_int("EZBOTI_REQUEST_TIMEOUT_SECONDS", 15)

    smtp_host: str = _getenv("SMTP_HOST", "")
    smtp_port: int = _get_int("SMTP_PORT", 465)
    smtp_user: str = _getenv("SMTP_USER", "")
    smtp_password: str = _getenv("SMTP_PASSWORD", "")
    smtp_from: str = _getenv("SMTP_FROM", "")
    smtp_from_name: str = _getenv("SMTP_FROM_NAME", app_name)
    smtp_use_ssl: bool = _get_bool("SMTP_USE_SSL", True)
    smtp_use_tls: bool = _get_bool("SMTP_USE_TLS", False)
    smtp_timeout_seconds: int = _get_int("SMTP_TIMEOUT_SECONDS", 15)

    cors_allow_origins: str = _getenv("CORS_ALLOW_ORIGINS", "")
    trusted_proxy_headers: bool = _get_bool("TRUSTED_PROXY_HEADERS", True)

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            return self.database_url_override
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"
        )

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def allowed_extensions(self) -> set[str]:
        return {
            item.strip().lower()
            for item in self.allowed_upload_extensions.split(",")
            if item.strip()
        }

    @property
    def allowed_mime_prefixes(self) -> tuple[str, ...]:
        return tuple(
            item.strip()
            for item in self.allowed_upload_mime_prefixes.split(",")
            if item.strip()
        )

    @property
    def amount_yuan(self) -> Decimal:
        return (Decimal(self.product_price_cents) / Decimal(100)).quantize(Decimal("0.01"))

    @property
    def effective_daxpay_notify_url(self) -> str:
        if self.daxpay_notify_url:
            return self.daxpay_notify_url
        return f"{self.public_base_url}/api/payments/daxpay/notify"

    @property
    def effective_daxpay_return_url(self) -> str:
        if self.daxpay_return_url:
            return self.daxpay_return_url
        return f"{self.public_base_url}/"

    @property
    def effective_alipay_notify_url(self) -> str:
        if self.alipay_notify_url:
            return self.alipay_notify_url
        return f"{self.public_base_url}/api/payments/alipay/notify"

    @property
    def effective_alipay_return_url(self) -> str:
        if self.alipay_return_url:
            return self.alipay_return_url
        return f"{self.public_base_url}/"

    @property
    def effective_xunhupay_notify_url(self) -> str:
        if self.xunhupay_notify_url:
            return self.xunhupay_notify_url
        return f"{self.public_base_url}/api/payments/xunhupay/notify"

    @property
    def effective_xunhupay_return_url(self) -> str:
        if self.xunhupay_return_url:
            return self.xunhupay_return_url
        return f"{self.public_base_url}/"


settings = Settings()

if not settings.app_secret:
    raise RuntimeError("APP_SECRET is required")
if not settings.admin_password:
    raise RuntimeError("ADMIN_PASSWORD is required")
