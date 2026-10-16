"""Registro, login e sessão."""
import re
import threading
import time
from collections import defaultdict, deque

from flask import Blueprint, jsonify, request

from twilight.auth.service import (
    clear_user_game,
    create_token,
    delete_account,
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


# --------------------------------------------------------------------------
# Configurações da conta (página /settings)
# --------------------------------------------------------------------------
MIN_PASSWORD_LEN = 4
# Chaves aceitas nas preferências de sala (mesmas do modal de criar sala).
_PREF_BOOL_KEYS = ('private', 'allow_spectators', 'chat_enabled')
_DEFAULT_ROOM_PREFS = {
    'max_players': 6,
    'private': False,
    'allow_spectators': True,
    'chat_enabled': True,
}


def _require_auth_json():
    """Retorna o usuário logado ou uma resposta 401 pronta."""
    username = get_current_user()
    if not username:
        return None, (jsonify({'success': False, 'message': 'Não autenticado'}), 401)
    return username, None


@bp.route('/api/account')
def get_account():
    username, err = _require_auth_json()
    if err:
        return err

    account = load_accounts().get(username, {})
    prefs = account.get('room_preferences')
    if not isinstance(prefs, dict):
        prefs = {}
    # Mescla com os defaults para o cliente nunca receber campos faltando.
    preferences = dict(_DEFAULT_ROOM_PREFS)
    preferences.update({k: v for k, v in prefs.items() if k in _DEFAULT_ROOM_PREFS})

    return jsonify({
        'success': True,
        'account': {
            'username': username,
            'created_at': account.get('created_at'),
            'current_game': account.get('current_game'),
            'admin_level': int(account.get('admin_level', account.get('level', 0)) or 0),
            'preferences': preferences,
        },
    })


@bp.route('/api/account/change-password', methods=['POST'])
def change_password():
    username, err = _require_auth_json()
    if err:
        return err

    data = request.json or {}
    current_password = (data.get('current_password') or '').strip()
    new_password = (data.get('new_password') or '').strip()

    # Mesmo rate limit do login, por IP+usuário.
    key = f'pwd:{_client_ip()}:{username}'
    if _too_many(key, _LOGIN_WINDOW, _MAX_FAILED_LOGINS):
        return jsonify({'success': False, 'message': 'Muitas tentativas. Aguarde alguns minutos.'}), 429

    account = load_accounts().get(username, {})
    if not account or not verify_password(current_password, account.get('password', '')):
        _record(key)
        return jsonify({'success': False, 'message': 'Senha atual incorreta'}), 400

    if len(new_password) < MIN_PASSWORD_LEN:
        return jsonify({
            'success': False,
            'message': f'A nova senha deve ter pelo menos {MIN_PASSWORD_LEN} caracteres',
        }), 400
    if new_password == current_password:
        return jsonify({'success': False, 'message': 'A nova senha deve ser diferente da atual'}), 400

    update_account(username, {'password': hash_password(new_password)})
    return jsonify({'success': True, 'message': 'Senha alterada com sucesso'})


@bp.route('/api/account/preferences', methods=['POST'])
def save_preferences():
    username, err = _require_auth_json()
    if err:
        return err

    data = request.json or {}
    prefs = data.get('preferences')
    if not isinstance(prefs, dict):
        return jsonify({'success': False, 'message': 'Preferências inválidas'}), 400

    clean = dict(_DEFAULT_ROOM_PREFS)

    if 'max_players' in prefs:
        try:
            max_players = int(prefs['max_players'])
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': 'Máximo de jogadores inválido'}), 400
        if not 2 <= max_players <= 12:
            return jsonify({'success': False, 'message': 'Máximo de jogadores deve ser entre 2 e 12'}), 400
        clean['max_players'] = max_players

    for k in _PREF_BOOL_KEYS:
        if k in prefs:
            clean[k] = bool(prefs[k])

    if not update_account(username, {'room_preferences': clean}):
        return jsonify({'success': False, 'message': 'Conta não encontrada'}), 404
    return jsonify({'success': True, 'preferences': clean})


@bp.route('/api/account/delete', methods=['POST'])
def delete_own_account():
    username, err = _require_auth_json()
    if err:
        return err

    data = request.json or {}
    password = (data.get('password') or '').strip()
    confirm = (data.get('confirm') or '').strip()

    if confirm != 'APAGAR':
        return jsonify({'success': False, 'message': 'Confirmação inválida. Digite APAGAR.'}), 400

    account = load_accounts().get(username, {})
    admin_level = int(account.get('admin_level', account.get('level', 0)) or 0)
    if admin_level >= 1:
        return jsonify({
            'success': False,
            'message': 'Contas de administrador não podem ser excluídas por aqui.',
        }), 403

    if not account or not verify_password(password, account.get('password', '')):
        return jsonify({'success': False, 'message': 'Senha incorreta'}), 400

    # Evita deixar um "fantasma" numa partida em andamento.
    current_game = account.get('current_game')
    if current_game and current_game in games:
        return jsonify({
            'success': False,
            'message': 'Saia da partida em andamento antes de excluir a conta.',
        }), 409

    # Sai da partida atual (se houver) e remove a conta.
    clear_user_game(username, current_game)
    delete_account(username)

    response = jsonify({'success': True, 'message': 'Conta excluída'})
    response.delete_cookie('auth_token')
    return response


