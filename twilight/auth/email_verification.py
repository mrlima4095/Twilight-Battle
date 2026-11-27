"""Verificação de email das contas locais.

Contas Lucy já nascem verificadas (o provedor valida o email). Contas locais
 antigas sem email continuam valendo — só cadastros novos exigem confirmação.
"""
from __future__ import annotations

import hashlib
import re
import secrets
import time

from twilight.config import APP_BASE_URL, EMAIL_VERIFICATION_TTL_SECONDS
from twilight.storage.db import find_account_by_meta, get_account, update_account

EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
META_TOKEN_KEY = 'email_verify_token_hash'


def normalize_email(value) -> str:
    return str(value or '').strip().lower()[:254]


def valid_email(value) -> bool:
    email = normalize_email(value)
    return bool(email and EMAIL_RE.match(email))


def find_by_email(email: str):
    return find_account_by_meta('email', normalize_email(email))


def new_token() -> tuple[str, str, int]:
    """Devolve (token limpo, hash salvo no banco, expiração em epoch)."""
    raw = secrets.token_urlsafe(32)
    return raw, hashlib.sha256(raw.encode('utf-8')).hexdigest(), int(time.time()) + EMAIL_VERIFICATION_TTL_SECONDS


def mark_unverified(username: str, email: str) -> tuple[str, int]:
    """Cria/atualiza o token e grava o email na conta. Retorna (token, expiry)."""
    raw, token_hash, expires = new_token()
    update_account(username, {
        'email': normalize_email(email),
        'email_verified': False,
        META_TOKEN_KEY: token_hash,
        'email_verify_expires': expires,
    })
    return raw, expires


def confirm_token(token: str) -> str | None:
    """Confirma o token. Idempotente; devolve o username ou None."""
    raw = str(token or '').strip()
    if not raw:
        return None
    token_hash = hashlib.sha256(raw.encode('utf-8')).hexdigest()
    found = find_account_by_meta(META_TOKEN_KEY, token_hash)
    if not found:
        return None
    username, account = found
    expires = int(account.get('email_verify_expires') or 0)
    if expires and int(time.time()) > expires:
        return None
    update_account(username, {
        'email_verified': True,
        META_TOKEN_KEY: None,
        'email_verify_expires': None,
    })
    return username


def verify_url(token: str) -> str:
    return f'{APP_BASE_URL}/verify-email/{token}'


def is_verified(account: dict | None) -> bool:
    """Legacy sem email continua válido; conta com email exige confirmação."""
    if not account:
        return False
    if not account.get('email'):
        return True
    return bool(account.get('email_verified'))


def send_verification(username: str, email: str) -> tuple[bool, str]:
    """Gera o token e envia o email. Nunca lança exceção."""
    from twilight.mailer import send_verification_email

    token, _ = mark_unverified(username, email)
    sent = send_verification_email(normalize_email(email), username, verify_url(token))
    return sent, token


def get_account_by_username(username: str):
    return get_account(username)
