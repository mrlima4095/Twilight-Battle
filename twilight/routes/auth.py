"""Registro, login e sessão."""
from datetime import datetime

from flask import Blueprint, jsonify, make_response, request

from twilight.auth.service import (
    create_token,
    get_current_user,
    hash_password,
    load_accounts,
    save_accounts,
    verify_password,
)
from twilight.config import JWT_EXPIRATION_HOURS

bp = Blueprint('auth', __name__)


@bp.route('/api/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username', '').strip().lower()
    password = data.get('password', '').strip()
    
    if not username or not password: return jsonify({'success': False, 'message': 'Usuário e senha obrigatórios'})
    if len(username) < 3 or len(username) > 20: return jsonify({'success': False, 'message': 'Usuário deve ter entre 3 e 20 caracteres'})
    if len(password) < 4: return jsonify({'success': False, 'message': 'Senha deve ter pelo menos 4 caracteres'})
    
    accounts = load_accounts()
    
    if username in accounts: return jsonify({'success': False, 'message': 'Usuário já existe'})
    
    # Criar nova conta
    accounts[username] = {
        'password': hash_password(password),
        'created_at': datetime.utcnow().isoformat(),
        'current_game': None  # Nenhum jogo ativo
    }
    
    save_accounts(accounts)
    
    # Criar token
    token = create_token(username)
    
    response = jsonify({'success': True, 'username': username})
    response.set_cookie(
        'auth_token',
        token,
        httponly=True,
        secure=True,  # True em produção com HTTPS
        samesite='Lax',
        max_age=JWT_EXPIRATION_HOURS * 3600
    )
    
    return response



@bp.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username', '').strip().lower()
    password = data.get('password', '').strip()
    
    if not username or not password: return jsonify({'success': False, 'message': 'Usuário e senha obrigatórios'})
    
    accounts = load_accounts()
    
    if username not in accounts: return jsonify({'success': False, 'message': 'Usuário ou senha inválidos'})
    if not verify_password(password, accounts[username]['password']): return jsonify({'success': False, 'message': 'Usuário ou senha inválidos'})
    
    # Criar token
    token = create_token(username)
    
    response = jsonify({
        'success': True,
        'username': username,
        'current_game': accounts[username].get('current_game')
    })
    
    response.set_cookie(
        'auth_token',
        token,
        httponly=True,
        secure=True,  # True em produção com HTTPS
        samesite='Lax',
        max_age=JWT_EXPIRATION_HOURS * 3600
    )
    
    return response



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
    
    # Verificar se o jogo ainda existe
    if current_game and current_game in games:
        return jsonify({
            'authenticated': True,
            'username': username,
            'current_game': current_game,
            'game_exists': True
        })
    else:
        # Se o jogo não existe mais, limpar da conta
        if current_game and username in accounts:
            accounts[username]['current_game'] = None
            save_accounts(accounts)
        
        return jsonify({
            'authenticated': True,
            'username': username,
            'current_game': None,
            'game_exists': False
        })



@bp.route('/api/auth/status')
def api_auth_status():
    username = get_current_user()
    if not username:
        return jsonify({'logged_in': False})
    
    accounts = load_accounts()
    user_data = accounts.get(username, {})
    
    return jsonify({
        'logged_in': True,
        'user': {
            'username': username,
            'realname': user_data.get('realname', username),
            'level': user_data.get('level', 1)
        }
    })


    response = jsonify({'success': True})
    response.delete_cookie('auth_token')
    return response


