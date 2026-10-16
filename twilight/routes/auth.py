"""Registro, login e sessão."""
import re
import threading
import time
from collections import defaultdict, deque

from flask import Blueprint, jsonify, request

from twilight.auth.service import (
    clear_user_game,
    create_token,
    get_current_user,
    hash_password,
    load_accounts,
    save_accounts,
    update_account,
    verify_password,
)
from twilight.config import JWT_EXPIRATION_HOURS, SECURE_COOKIES, now_sp_iso
from twilight.state import games

bp = Blueprint('auth', __name__)

# Só letras minúsculas, números e underscore — evita XSS/HTML em nomes e
# mantém os nomes seguros em atributos/JS do painel admin.
USERNAME_RE = re.compile(r'^[a-z0-9_]{3,20}$')

# Rate limiting simples em memória (por IP): login e registro
_attempts = defaultdict(deque)
_MAX_FAILED_LOGINS = 10
_LOGIN_WINDOW = 300  # 5 min
_MAX_REGISTERS = 10
_REGISTER_WINDOW = 600  # 10 min
_attempts_lock = threading.Lock()


def _client_ip():
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or 'unknown'


def _prune(bucket, window):
    now = time.time()
    while bucket and bucket[0] < now - window:
        bucket.popleft()


def _too_many(key, window, limit):
    with _attempts_lock:
        bucket = _attempts[key]
        _prune(bucket, window)
        return len(bucket) >= limit


def _record(key):
    with _attempts_lock:
        _attempts[key].append(time.time())


def _set_auth_cookie(response, token):
    response.set_cookie(
        'auth_token',
        token,
        httponly=True,
        secure=SECURE_COOKIES,
        samesite='Lax',
        max_age=JWT_EXPIRATION_HOURS * 3600,
    )
    return response


@bp.route('/api/register', methods=['POST'])
def register():
    data = request.json or {}
    username = data.get('username', '').strip().lower()
    password = data.get('password', '').strip()

    if not username or not password:
        return jsonify({'success': False, 'message': 'Usuário e senha obrigatórios'})
    if not USERNAME_RE.match(username):
        return jsonify({
            'success': False,
            'message': 'Usuário deve ter 3-20 caracteres: apenas letras, números e _ (sem espaços/acentos)',
        })
    if len(password) < 4:
        return jsonify({'success': False, 'message': 'Senha deve ter pelo menos 4 caracteres'})

    reg_key = f'reg:{_client_ip()}'
    if _too_many(reg_key, _REGISTER_WINDOW, _MAX_REGISTERS):
        return jsonify({'success': False, 'message': 'Muitas tentativas. Tente novamente mais tarde.'}), 429
    _record(reg_key)

    accounts = load_accounts()

    if username in accounts:
        return jsonify({'success': False, 'message': 'Usuário já existe'})

    # Criar nova conta
    accounts[username] = {
        'password': hash_password(password),
        'created_at': now_sp_iso(),
        'current_game': None  # Nenhum jogo ativo
    }

    save_accounts(accounts)

    # Criar token
    token = create_token(username)

    response = jsonify({'success': True, 'username': username})
    return _set_auth_cookie(response, token)



@bp.route('/api/login', methods=['POST'])
def login():
    data = request.json or {}
    username = data.get('username', '').strip().lower()
    password = data.get('password', '').strip()

    if not username or not password:
        return jsonify({'success': False, 'message': 'Usuário e senha obrigatórios'})

    login_key = f'login:{_client_ip()}:{username}'
    if _too_many(login_key, _LOGIN_WINDOW, _MAX_FAILED_LOGINS):
        return jsonify({'success': False, 'message': 'Muitas tentativas de login. Aguarde 5 minutos.'}), 429

    accounts = load_accounts()

    if username not in accounts or not verify_password(password, accounts[username]['password']):
        _record(login_key)
        return jsonify({'success': False, 'message': 'Usuário ou senha inválidos'})

    # Criar token
    token = create_token(username)

    response = jsonify({
        'success': True,
        'username': username,
        'current_game': accounts[username].get('current_game')
    })
    return _set_auth_cookie(response, token)



@bp.route('/api/logout', methods=['POST'])
def logout():
    response = jsonify({'success': True})
    response.delete_cookie('auth_token')
    return response



@bp.route('/api/check-auth')
def check_auth():
    username = get_current_user()
    
    if not username:
        return jsonify({'authenticated': False})
    
    accounts = load_accounts()
    current_game = accounts.get(username, {}).get('current_game')
    
    # Verificar se o jogo ainda existe (lobby pós-rematch conta como ativo)
    if current_game and current_game in games:
        game = games[current_game]
        return jsonify({
            'authenticated': True,
            'username': username,
            'current_game': current_game,
            'game_exists': True,
            'game_started': bool(getattr(game, 'started', False)),
            'game_finished': bool(getattr(game, 'finished', False)),
        })
    else:
        # Se o jogo não existe mais, limpar da conta
        if current_game:
            update_account(username, {'current_game': None})
        
        return jsonify({
            'authenticated': True,
            'username': username,
            'current_game': None,
            'game_exists': False
        })



@bp.route('/api/clear-current-game', methods=['POST'])
def clear_current_game():
    """Limpa current_game da conta (chamar no fim da partida / sair)."""
    username = get_current_user()
    if not username:
        return jsonify({'success': False, 'message': 'Não autenticado'}), 401

    data = request.json or {}
    game_id = data.get('game_id')
    clear_user_game(username, game_id)
    return jsonify({'success': True, 'current_game': None})


@bp.route('/api/auth/status')
def api_auth_status():
    username = get_current_user()
    if not username:
        return jsonify({'logged_in': False})
    
    accounts = load_accounts()
    user_data = accounts.get(username, {})
    admin_level = int(user_data.get('admin_level', user_data.get('level', 0)) or 0)
    
    return jsonify({
        'logged_in': True,
        'user': {
            'username': username,
            'realname': user_data.get('realname', username),
            # level legado + admin_level (journal/admin usam admin_level)
            'level': admin_level,
            'admin_level': admin_level,
        }
    })


