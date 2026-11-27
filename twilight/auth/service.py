"""Contas, senhas, JWT e usuário atual."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import redirect, request

from twilight.config import (
    JWT_ALGORITHM,
    JWT_EXPIRATION_HOURS,
    JWT_SECRET,
)
from twilight.offload import run_offloop
from twilight.storage.db import (  # noqa: F401  (helpers re-exportados para imports legados)
    account_exists,
    clear_account_game,
    clear_accounts_current_game,
    delete_account,
    find_linked_account,
    get_account,
    load_accounts,
    save_accounts,
    update_account,
    upsert_account,
)

# reexport para imports legados: from twilight.auth.service import load_accounts
def _pbkdf2(password, salt):
    return hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000,
    ).hex()


def hash_password(password):
    salt = secrets.token_hex(16)
    password_hash = run_offloop(_pbkdf2, password, salt)
    return f"{salt}${password_hash}"


def verify_password(password, hashed):
    try:
        salt, password_hash = hashed.split('$')
        check_hash = run_offloop(_pbkdf2, password, salt)
        return hmac.compare_digest(check_hash, password_hash)
    except Exception:
        return False
def create_token(username):
    now = datetime.now(timezone.utc)
    payload = {
        'username': username,
        'exp': now + timedelta(hours=JWT_EXPIRATION_HOURS),
        'iat': now
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
def verify_token(token):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload['username']
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def get_current_user():
    token = request.cookies.get('auth_token')
    if token:
        return verify_token(token)
    return None

def update_user_game(username, game_id):
    """Atualiza o jogo atual do usuário"""
    update_account(username, {'current_game': game_id})

def clear_user_game(username, game_id=None):
    """Remove current_game da conta (opcionalmente só se for o game_id)."""
    clear_account_game(username, game_id)


def clear_game_from_all_accounts(game_id, usernames=None):
    """
    Limpa current_game de todos os jogadores da sala em UMA query indexada.
    Evita loop: fim de jogo → / → check-auth redireciona de volta pro game.
    """
    clear_accounts_current_game(game_id, usernames)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        username = get_current_user()
        if not username:
            return redirect('/login')
        return f(username, *args, **kwargs)
    return decorated_function

