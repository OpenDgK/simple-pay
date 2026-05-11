from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from .config import settings


def _smtp_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_user and settings.smtp_password and settings.smtp_from)


def send_account_delivery_email(
    *,
    to_email: str,
    order_no: str,
    product_name: str,
    account: str,
    password: str,
) -> None:
    if not _smtp_configured():
        raise RuntimeError("SMTP is not configured")

    message = EmailMessage()
    message["Subject"] = f"{product_name} 账号已发货"
    message["From"] = formataddr((settings.smtp_from_name, settings.smtp_from))
    message["To"] = to_email
    message.set_content(
        "\n".join(
            [
                "您好，您的订单已支付成功，账号信息如下：",
                "",
                f"订单号：{order_no}",
                f"商品：{product_name}",
                f"账号：{account}",
                f"密码：{password}",
                "",
                "请妥善保存账号和密码。",
            ]
        )
    )

    if settings.smtp_use_ssl:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(
            settings.smtp_host,
            settings.smtp_port,
            timeout=settings.smtp_timeout_seconds,
            context=context,
        ) as smtp:
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)
        return

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls(context=ssl.create_default_context())
        smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)
