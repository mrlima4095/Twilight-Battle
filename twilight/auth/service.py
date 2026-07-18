"""Contas, senhas, JWT e usuário atual."""
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta
from functools import wraps

import jwt
from flask import redirect, request

from twilight.config import (
    ACCOUNTS_FILE,
    JWT_ALGORITHM,
    JWT_EXPIRATION_HOURS,
    JWT_SECRET,
)

def load_accounts():
    try:
        with open(ACCOUNTS_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
def save_accounts(accounts):
    with open(ACCOUNTS_FILE, 'w') as f:
        json.dump(accounts, f, indent=4)
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

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        username = get_current_user()
        if not username:
            return redirect('/')
        return f(username, *args, **kwargs)
    return decorated_function

