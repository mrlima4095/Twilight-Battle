"""API de saves do modo história."""
import json
import os

from flask import Blueprint, jsonify, request

from twilight.auth.service import login_required, update_account
from twilight.config import MAX_STORY_SAVE_BYTES, now_sp_iso
from twilight.storage.story_saves import get_user_save_file

bp = Blueprint('story', __name__)


def _atomic_json_write(path, data):
    """Escreve JSON via arquivo temporário + os.replace (escrita atômica)."""
    tmp_path = f'{path}.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


@bp.route('/api/save-game', methods=['POST'])
@login_required
def api_save_game(username):
    """Salva o jogo do modo história na nuvem"""
    data = request.json or {}
    save_data = data.get('save_data')

    if not save_data or not isinstance(save_data, dict):
        return jsonify({'success': False, 'message': 'Dados de save vazios'}), 400

    # Limite de tamanho (evita encher o volume com payloads gigantes)
    try:
        serialized = json.dumps(save_data)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Save inválido'}), 400
    if len(serialized.encode('utf-8')) > MAX_STORY_SAVE_BYTES:
        return jsonify({
            'success': False,
            'message': f'Save grande demais (máx. {MAX_STORY_SAVE_BYTES // 1024} KB)',
        }), 413

    save_file = get_user_save_file(username)

    try:
        _atomic_json_write(save_file, save_data)

        # Metadados da conta (atômico, sem reescrever o conjunto inteiro)
        update_account(username, {
            'last_save_time': now_sp_iso(),
            'last_save_character': (save_data.get('character') or {}).get('name'),
        })

        return jsonify({
            'success': True, 
            'message': 'Jogo salvo na nuvem!',
            'saved_at': now_sp_iso(),
            'character_name': (save_data.get('character') or {}).get('name')
        })
    except OSError as e:
        return jsonify({'success': False, 'message': f'Erro ao salvar: {e}'}), 500



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
        update_account(username, {'last_load_time': now_sp_iso()})
        
        return jsonify({
            'success': True, 
            'save_data': save_data,
            'loaded_at': now_sp_iso(),
            'character_name': save_data.get('character', {}).get('name')
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro ao carregar: {str(e)}'}), 500




