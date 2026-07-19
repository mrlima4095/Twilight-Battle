"""Contas, senhas, JWT e usuário atual."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from functools import wraps

import jwt
from flask import redirect, request

from twilight.config import (
    JWT_ALGORITHM,
    JWT_EXPIRATION_HOURS,
    JWT_SECRET,
)
from twilight.storage.db import load_accounts, save_accounts

# reexport para imports legados: from twilight.auth.service import load_accounts
def hash_password(password):
    salt = secrets.token_hex(16)
    password_hash = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    ).hex()
    return f"{salt}${password_hash}"
def verify_password(password, hashed):
    try:
        salt, password_hash = hashed.split('$')
        check_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        ).hex()
        return hmac.compare_digest(check_hash, password_hash)
    except:
        return False
def create_token(username):
    payload = {
        'username': username,
        'exp': datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
        'iat': datetime.utcnow()
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
    accounts = load_accounts()
    if username in accounts:
        accounts[username]['current_game'] = game_id
        save_accounts(accounts)

def clear_user_game(username, game_id=None):
    """Remove current_game da conta (opcionalmente só se for o game_id)."""
    accounts = load_accounts()
    if username not in accounts:
        return
    current = accounts[username].get('current_game')
    if game_id is None or current == game_id:
        accounts[username]['current_game'] = None
        save_accounts(accounts)

def clear_game_from_all_accounts(game_id, usernames=None):
    """
    Limpa current_game de todos os jogadores da sala.
    Evita loop: fim de jogo → / → check-auth redireciona de volta pro game.
    """
    if not game_id:
        return
    accounts = load_accounts()
    changed = False
    if usernames is None:
        # limpa qualquer conta apontando para essa sala
        for uname, data in accounts.items():
            if data.get('current_game') == game_id:
                accounts[uname]['current_game'] = None
                changed = True
    else:
        for uname in usernames:
            if uname in accounts and accounts[uname].get('current_game') == game_id:
                accounts[uname]['current_game'] = None
                changed = True
    if changed:
        save_accounts(accounts)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        username = get_current_user()
        if not username:
            return redirect('/')
        return f(username, *args, **kwargs)
    return decorated_function

