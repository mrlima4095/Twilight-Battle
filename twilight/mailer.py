"""Envio de email via SMTP (Postfix local em produção).

Usa ``run_offloop`` para não bloquear o worker gevent enquanto o SMTP responde.
"""
from __future__ import annotations

import smtplib
from email.message import EmailMessage

from twilight.config import (
    MAIL_ENABLED,
    MAIL_FROM,
    MAIL_PASSWORD,
    MAIL_PORT,
    MAIL_SERVER,
    MAIL_TIMEOUT_SECONDS,
    MAIL_USE_TLS,
    MAIL_USERNAME,
)
from twilight.offload import run_offloop


def _send(message: EmailMessage) -> None:
    with smtplib.SMTP(MAIL_SERVER, MAIL_PORT, timeout=MAIL_TIMEOUT_SECONDS) as smtp:
        if MAIL_USE_TLS:
            smtp.starttls()
        if MAIL_USERNAME:
            smtp.login(MAIL_USERNAME, MAIL_PASSWORD)
        smtp.send_message(message)


def send_email(to: str, subject: str, body: str) -> bool:
    """Envia um email simples. Retorna False se não houver SMTP configurado."""
    if not MAIL_ENABLED or not to:
        return False

    message = EmailMessage()
    message['From'] = MAIL_FROM
    message['To'] = to
    message['Subject'] = subject
    message.set_content(body)

    try:
        run_offloop(_send, message)
        return True
    except Exception as exc:  # never derruba o request por causa de email
        print(f'[mail] falha ao enviar para {to}: {exc}')
        return False


def send_verification_email(to: str, username: str, verify_url: str) -> bool:
    body = (
        f'Olá, {username}!\n\n'
        'Confirme seu email para ativar sua conta no Twilight Battle:\n'
        f'{verify_url}\n\n'
        'O link expira em 24 horas. Se não foi você que criou a conta, ignore este email.\n\n'
        '— Twilight Battle\n'
    )
    return send_email(to, 'Confirme seu email — Twilight Battle', body)
