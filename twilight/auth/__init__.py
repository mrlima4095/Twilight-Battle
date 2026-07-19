"""Autenticação, contas e permissões."""

from twilight.auth.admin import admin_required, is_admin, is_super_admin
from twilight.auth.service import (
    clear_game_from_all_accounts,
    clear_user_game,
    create_token,
    get_current_user,
    hash_password,
    load_accounts,
    login_required,
    save_accounts,
    update_user_game,
    verify_password,
    verify_token,
)

__all__ = [
    'admin_required',
    'clear_game_from_all_accounts',
    'clear_user_game',
    'create_token',
    'get_current_user',
    'hash_password',
    'is_admin',
    'is_super_admin',
    'load_accounts',
    'login_required',
    'save_accounts',
    'update_user_game',
    'verify_password',
    'verify_token',
]
