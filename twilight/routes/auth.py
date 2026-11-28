"""Registro, login e sessão."""
import re
import threading
import time
from collections import defaultdict, deque

from flask import Blueprint, jsonify, redirect, request

from twilight.auth import email_verification
from twilight.auth.service import (
    account_exists,
    clear_user_game,
    create_token,
    delete_account,
    get_account as get_account_record,
    get_current_user,
    hash_password,
    is_account_active,
    update_account,
    upsert_account,
    verify_password,
)
from twilight.config import (
    AUTH_MODE,
    EMAIL_VERIFICATION_REQUIRED,
    JWT_EXPIRATION_HOURS,
    SECURE_COOKIES,
    TRUST_PROXY_HEADERS,
    auth_allows_internal,
    now_sp_iso,
)
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
_MAX_ATTEMPT_KEYS = 10_000
_attempts_lock = threading.Lock()


def _client_ip():
    # X-Forwarded-For só é confiável atrás de proxy conhecido (Coolify/Traefik).
    if TRUST_PROXY_HEADERS:
        forwarded = request.headers.get('X-Forwarded-For', '')
        if forwarded:
            return forwarded.split(',')[0].strip()
    return request.remote_addr or 'unknown'


def _prune(bucket, window):
    now = time.time()
    while bucket and bucket[0] < now - window:
        bucket.popleft()
    return bool(bucket)


def _prune_all():
    """Limita o dicionário inteiro (chaves criadas por IPs aleatórios)."""
    if len(_attempts) <= _MAX_ATTEMPT_KEYS:
        return
    now = time.time()
    for key in list(_attempts):
        bucket = _attempts[key]
        while bucket and bucket[0] < now - _REGISTER_WINDOW:
            bucket.popleft()
        if not bucket:
            _attempts.pop(key, None)


def _too_many(key, window, limit):
    with _attempts_lock:
        _prune_all()
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


def _internal_login_disabled():
    """Resposta usada quando a instância não permite login por senha."""
    return jsonify({
        'success': False,
        'message': 'Esta instância usa apenas login da Lucy.',
        'auth_mode': AUTH_MODE,
    }), 403


@bp.route('/api/register', methods=['POST'])
def register():
    if not auth_allows_internal():
        return _internal_login_disabled()

    require_verify = EMAIL_VERIFICATION_REQUIRED
    data = request.json or {}
    username = data.get('username', '').strip().lower()
    password = data.get('password', '').strip()
    email = email_verification.normalize_email(data.get('email'))

    if not username or not password or (require_verify and not email):
        return jsonify({
            'success': False,
            'message': 'Usuário, senha e email obrigatórios' if require_verify
                       else 'Usuário e senha obrigatórios',
        })
    if not USERNAME_RE.match(username):
        return jsonify({
            'success': False,
            'message': 'Usuário deve ter 3-20 caracteres: apenas letras, números e _ (sem espaços/acentos)',
        })
    if len(password) < 4:
        return jsonify({'success': False, 'message': 'Senha deve ter pelo menos 4 caracteres'})
    if require_verify and not email_verification.valid_email(email):
        return jsonify({'success': False, 'message': 'Email inválido'})

    reg_key = f'reg:{_client_ip()}'
    if _too_many(reg_key, _REGISTER_WINDOW, _MAX_REGISTERS):
        return jsonify({'success': False, 'message': 'Muitas tentativas. Tente novamente mais tarde.'}), 429
    _record(reg_key)

    if account_exists(username):
        return jsonify({'success': False, 'message': 'Usuário já existe'})
    if require_verify and email_verification.find_by_email(email):
        return jsonify({'success': False, 'message': 'Este email já está em uso'})

    fields = {
        'password': hash_password(password),
        'created_at': now_sp_iso(),
        'current_game': None,
        'auth_provider': 'internal',
    }
    if require_verify:
        fields['email'] = email
        fields['email_verified'] = False
    upsert_account(username, fields)

    if not require_verify:
        # Compatibilidade com instalações que desligaram a verificação.
        return _set_auth_cookie(
            jsonify({'success': True, 'username': username}), create_token(username)
        )

    sent, _ = email_verification.send_verification(username, email)
    response = jsonify({
        'success': True,
        'username': username,
        'requires_verification': True,
        'email_sent': sent,
        'message': (
            'Conta criada! Confirme seu email para entrar.'
            if sent else
            'Conta criada, mas o email não pôde ser enviado. Use "Reenviar verificação" na tela de login.'
        ),
    })
    return response



@bp.route('/api/login', methods=['POST'])
def login():
    if not auth_allows_internal():
        return _internal_login_disabled()

    data = request.json or {}
    username = data.get('username', '').strip().lower()
    password = data.get('password', '').strip()

    if not username or not password:
        return jsonify({'success': False, 'message': 'Usuário e senha obrigatórios'})

    login_key = f'login:{_client_ip()}:{username}'
    if _too_many(login_key, _LOGIN_WINDOW, _MAX_FAILED_LOGINS):
        return jsonify({'success': False, 'message': 'Muitas tentativas de login. Aguarde 5 minutos.'}), 429

    account = get_account_record(username)

    if not account or not verify_password(password, account.get('password', '')):
        _record(login_key)
        return jsonify({'success': False, 'message': 'Usuário ou senha inválidos'})

    if not is_account_active(account):
        return jsonify({'success': False, 'message': 'Esta conta foi desativada'}), 403

    if EMAIL_VERIFICATION_REQUIRED and not email_verification.is_verified(account):
        return jsonify({
            'success': False,
            'requires_verification': True,
            'message': 'Confirme seu email antes de entrar. Verifique sua caixa de entrada.',
        }), 403

    token = create_token(username)
    response = jsonify({
        'success': True,
        'username': username,
        'current_game': account.get('current_game')
    })
    return _set_auth_cookie(response, token)


@bp.route('/verify-email/<token>')
def verify_email(token):
    """Link do email: confirma a conta e já loga o jogador."""
    username = email_verification.confirm_token(token)
    if not username:
        return redirect('/login?verify_error=1')
    if not is_account_active(get_account_record(username)):
        return redirect('/login?error=account_disabled')

    response = redirect('/?email_verified=1')
    return _set_auth_cookie(response, create_token(username))


@bp.route('/api/resend-verification', methods=['POST'])
def resend_verification():
    """Reenvia o link de confirmação para uma conta local não verificada."""
    if not auth_allows_internal() or not EMAIL_VERIFICATION_REQUIRED:
        return jsonify({'success': False, 'message': 'Verificação de email indisponível'}), 400

    data = request.json or {}
    username = data.get('username', '').strip().lower()
    email = email_verification.normalize_email(data.get('email'))
    key = f'verify:{_client_ip()}:{username}'
    if _too_many(key, _REGISTER_WINDOW, _MAX_REGISTERS):
        return jsonify({'success': False, 'message': 'Muitas tentativas. Aguarde alguns minutos.'}), 429
    _record(key)

    account = get_account_record(username)
    if not account:
        return jsonify({'success': False, 'message': 'Conta não encontrada'})
    if account.get('email_verified') or email_verification.is_verified(account):
        return jsonify({'success': True, 'message': 'Esta conta já está verificada'})

    saved_email = account.get('email') or ''
    if email and saved_email and email != saved_email:
        return jsonify({'success': False, 'message': 'Email não corresponde ao da conta'})
    if not saved_email:
        if not email_verification.valid_email(email):
            return jsonify({'success': False, 'message': 'Informe um email válido'})
        saved_email = email

    sent, _ = email_verification.send_verification(username, saved_email)
    return jsonify({
        'success': sent,
        'message': ('Link reenviado. Verifique sua caixa de entrada.' if sent
                    else 'Não foi possível enviar o email. Tente novamente mais tarde.'),
    })



@bp.route('/api/logout', methods=['POST'])
def logout():
    response = jsonify({'success': True})
    response.delete_cookie('auth_token')
    return response



@bp.route('/api/check-auth')
def check_auth():
    username = get_current_user()
    
    if not username:
        return jsonify({'authenticated': False, 'auth_mode': AUTH_MODE})
    
    account = get_account_record(username) or {}
    current_game = account.get('current_game')

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
            'auth_mode': AUTH_MODE,
            'auth_provider': account.get('auth_provider', 'internal'),
        })
    else:
        # Se o jogo não existe mais, limpar da conta
        if current_game:
            clear_user_game(username, current_game)
        
        return jsonify({
            'authenticated': True,
            'username': username,
            'current_game': None,
            'game_exists': False,
            'auth_mode': AUTH_MODE,
            'auth_provider': account.get('auth_provider', 'internal'),
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
        return jsonify({'logged_in': False, 'auth_mode': AUTH_MODE})
    
    user_data = get_account_record(username) or {}
    admin_level = int(user_data.get('admin_level', user_data.get('level', 0)) or 0)
    
    return jsonify({
        'logged_in': True,
        'user': {
            'username': username,
            'realname': user_data.get('realname', username),
            # level legado + admin_level (journal/admin usam admin_level)
            'level': admin_level,
            'admin_level': admin_level,
            'auth_provider': user_data.get('auth_provider', 'internal'),
        },
        'auth_mode': AUTH_MODE,
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

    account = get_account_record(username) or {}
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
            'auth_provider': account.get('auth_provider', 'internal'),
            'email': account.get('email'),
            'email_verified': bool(account.get('email_verified')),
            'preferences': preferences,
        },
        'auth_mode': AUTH_MODE,
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

    account = get_account_record(username) or {}
    if account.get('auth_provider') == 'lucy':
        return jsonify({
            'success': False,
            'message': 'Conta vinculada à Lucy: a senha é gerenciada por ela.',
        }), 400
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

    account = get_account_record(username) or {}
    admin_level = int(account.get('admin_level', account.get('level', 0)) or 0)
    if admin_level >= 1:
        return jsonify({
            'success': False,
            'message': 'Contas de administrador não podem ser excluídas por aqui.',
        }), 403

    if not account:
        return jsonify({'success': False, 'message': 'Conta não encontrada'}), 404
    if account.get('auth_provider') != 'lucy' and not verify_password(
        password, account.get('password', '')
    ):
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


