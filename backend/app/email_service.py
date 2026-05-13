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


def send_manual_payment_review_email(
    *,
    to_email: str,
    order_no: str,
    contact: str,
    product_name: str,
    amount_text: str,
    currency: str,
    admin_url: str,
) -> None:
    if not _smtp_configured():
        raise RuntimeError("SMTP is not configured")

    message = EmailMessage()
    message["Subject"] = f"待确认收款：{order_no}"
    message["From"] = formataddr((settings.smtp_from_name, settings.smtp_from))
    message["To"] = to_email
    message.set_content(
        "\n".join(
            [
                "有用户提交了人工付款确认，请核对支付宝到账记录后再发货。",
                "",
                f"订单号：{order_no}",
                f"邮箱：{contact}",
                f"商品：{product_name}",
                f"金额：{amount_text} {currency}",
                f"后台：{admin_url}",
                "",
                "确认到账后，请在后台把支付状态改为 paid 并保存，系统会自动发账号密码邮件。",
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
