"""Helpers e decorator de admin."""
from functools import wraps

from flask import jsonify

from twilight.auth.service import get_account, get_current_user


def is_admin(username):
    """Verifica se um usuário é admin (level >= 1)"""
    if not username:
        return False
    account = get_account(username)
    # Admin level 1+ tem acesso ao painel
    return bool(account and int(account.get('admin_level', 0) or 0) >= 1)


def is_super_admin(username):
    """Verifica se é super admin (level >= 4)"""
    if not username:
        return False
    account = get_account(username)
    return bool(account and int(account.get('admin_level', 0) or 0) >= 4)


def admin_required(f):
    """Decorator para rotas que exigem admin"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        username = get_current_user()
        if not username or not is_admin(username):
            return jsonify({'success': False, 'message': 'Acesso negado'}), 403
        return f(username, *args, **kwargs)
    return decorated_function
