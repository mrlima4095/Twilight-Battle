"""API de saves do modo história."""
import json
import os

from flask import Blueprint, jsonify, request

from twilight.auth.service import login_required, update_account
from twilight.config import MAX_STORY_SAVE_BYTES, now_sp_iso
from twilight.storage.story_saves import get_user_save_file

bp = Blueprint('story', __name__)

# Limites de sanidade para o modo história (o cliente é autoritativo, então
# valores absurdos vindos do localStorage são higienizados aqui).
_MAX_LEVEL = 200
_MAX_GOLD = 10_000_000
_MAX_EXP = 100_000_000
_MAX_STAT = 1_000_000
_MAX_INVENTORY_SLOTS = 60
_MAX_NAME_LEN = 60
_MAX_SURVIVAL = 100


def _coerce_int(value, default, lo=None, hi=None):
    """Converte para int com limites; tipos inesperados caem no default."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    n = int(value)
    if lo is not None and n < lo:
        n = lo
    if hi is not None and n > hi:
        n = hi
    return n


def validate_and_normalize_save(save_data):
    """Valida e normaliza um save do modo história no servidor.

    O cliente monta o save livremente (localStorage), então o servidor não pode
    confiar em nenhum número. Esta função:
      * rejeita saves estruturalmente inválidos (retorna None + motivo);
      * normaliza tipos e limita campos numéricos a faixas plausíveis;
      * mantém a coerência vida <= vida máxima e isDead == (vida <= 0).

    Retorna (save_normalizado, None) ou (None, mensagem_de_erro).
    """
    if not isinstance(save_data, dict):
        return None, 'Save inválido'

    character = save_data.get('character')
    if not isinstance(character, dict):
        return None, 'Save sem personagem válido'

    name = str(character.get('name') or '').strip()
    if not name:
        return None, 'Personagem sem nome'
    character['name'] = name[:_MAX_NAME_LEN]

    max_life = _coerce_int(character.get('maxLife'), 1, lo=1, hi=_MAX_STAT)
    max_mana = _coerce_int(character.get('maxMana'), 0, lo=0, hi=_MAX_STAT)
    character['maxLife'] = max_life
    character['maxMana'] = max_mana
    character['life'] = _coerce_int(character.get('life'), max_life, lo=0, hi=max_life)
    character['mana'] = _coerce_int(character.get('mana'), max_mana, lo=0, hi=max_mana)
    character['level'] = _coerce_int(character.get('level'), 1, lo=1, hi=_MAX_LEVEL)
    character['exp'] = _coerce_int(character.get('exp'), 0, lo=0, hi=_MAX_EXP)
    character['gold'] = _coerce_int(character.get('gold'), 0, lo=0, hi=_MAX_GOLD)

    # Sobrevivência (fome/sede): sempre 0..100, com o padrão "cheio".
    survival = save_data.get('survival')
    if not isinstance(survival, dict):
        survival = {}
    survival['hunger'] = _coerce_int(survival.get('hunger'), _MAX_SURVIVAL, lo=0, hi=_MAX_SURVIVAL)
    survival['thirst'] = _coerce_int(survival.get('thirst'), _MAX_SURVIVAL, lo=0, hi=_MAX_SURVIVAL)
    save_data['survival'] = survival

    if not isinstance(save_data.get('inventory'), list):
        save_data['inventory'] = []
    save_data['inventory'] = save_data['inventory'][:_MAX_INVENTORY_SLOTS]

    if not isinstance(save_data.get('equipment'), dict):
        save_data['equipment'] = {}

    if not isinstance(save_data.get('location'), str) or not save_data['location']:
        save_data['location'] = 'home'

    if 'activeQuest' in save_data and save_data['activeQuest'] is not None \
            and not isinstance(save_data['activeQuest'], dict):
        save_data['activeQuest'] = None

    # Consistência: morte é exatamente vida <= 0.
    save_data['isDead'] = bool(character['life'] <= 0)

    return save_data, None


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

    # Valida e normaliza no servidor (o cliente é autoritativo).
    save_data, error = validate_and_normalize_save(save_data)
    if error:
        return jsonify({'success': False, 'message': error}), 400

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




