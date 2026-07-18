"""API de saves do modo história."""
import json
import os
from datetime import datetime

from flask import Blueprint, jsonify, request

from twilight.auth.service import load_accounts, login_required, save_accounts
from twilight.storage.story_saves import get_user_save_file

bp = Blueprint('story', __name__)


@bp.route('/api/save-game', methods=['POST'])
@login_required
def api_save_game(username):
    """Salva o jogo do modo história na nuvem"""
    data = request.json
    save_data = data.get('save_data')
    
    if not save_data:
        return jsonify({'success': False, 'message': 'Dados de save vazios'}), 400
    
    # Verificar se já existe um save
    save_file = get_user_save_file(username)
    
    try:
        with open(save_file, 'w') as f:
            json.dump(save_data, f, indent=2)
        
        # Adicionar metadados da conta
        accounts = load_accounts()
        if username in accounts:
            accounts[username]['last_save_time'] = datetime.utcnow().isoformat()
            accounts[username]['last_save_character'] = save_data.get('character', {}).get('name')
            save_accounts(accounts)
        
        return jsonify({
            'success': True, 
            'message': f'Jogo salvo na nuvem!',
            'saved_at': datetime.utcnow().isoformat(),
            'character_name': save_data.get('character', {}).get('name')
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro ao salvar: {str(e)}'}), 500



@bp.route('/api/load-game', methods=['GET'])
@login_required
def api_load_game(username):
    """Carrega o jogo do modo história da nuvem"""
    save_file = get_user_save_file(username)
    
    if not os.path.exists(save_file):
        return jsonify({'success': False, 'message': 'Nenhum save encontrado na nuvem'}), 404
    
    try:
        with open(save_file, 'r') as f:
            save_data = json.load(f)
        
        # Verificar se o save é válido
        if save_data.get('isDead', False):
            return jsonify({
                'success': False, 
                'message': 'Este save é de um personagem MORTO. Não pode ser carregado.',
                'is_dead': True
            }), 410
        
        if save_data.get('character', {}).get('life', 0) <= 0:
            return jsonify({
                'success': False, 
                'message': 'Este save é de um personagem com vida zero.',
                'is_dead': True
            }), 410
        
        # Atualizar metadados da conta
        accounts = load_accounts()
        if username in accounts:
            accounts[username]['last_load_time'] = datetime.utcnow().isoformat()
            save_accounts(accounts)
        
        return jsonify({
            'success': True, 
            'save_data': save_data,
            'loaded_at': datetime.utcnow().isoformat(),
            'character_name': save_data.get('character', {}).get('name')
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro ao carregar: {str(e)}'}), 500




