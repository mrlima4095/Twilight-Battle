"""API do journal / diário do reino."""
import time
import uuid
from datetime import datetime

from flask import Blueprint, jsonify, request

from twilight.auth.service import load_accounts, login_required
from twilight.storage.journal import load_journal, save_journal

bp = Blueprint('journal', __name__)


@bp.route('/api/journal/entries')
def api_journal_entries():
    entries = load_journal()
    entries_sorted = sorted(entries, key=lambda x: x.get('date', ''), reverse=True)
    return jsonify({'success': True, 'entries': entries_sorted})


@bp.route('/api/journal/entry/<entry_id>')
def api_journal_entry(entry_id):
    entries = load_journal()
    for entry in entries:
        if entry.get('id') == entry_id:
            return jsonify({'success': True, 'entry': entry})
    return jsonify({'success': False, 'message': 'Entrada não encontrada'}), 404


@bp.route('/api/journal/create', methods=['POST'])
@login_required
def api_journal_create(username):
    accounts = load_accounts()
    admin_level = accounts.get(username, {}).get('level', 0)
    
    if admin_level < 4:
        return jsonify({'success': False, 'message': 'Apenas administradores podem criar entradas'}), 403
    
    data = request.json
    
    # Validar campos obrigatórios
    if not data.get('version') or not data.get('title'):
        return jsonify({'success': False, 'message': 'Versão e título são obrigatórios'}), 400
    
    entry_id = str(int(time.time() * 1000))
    
    new_entry = {
        'id': entry_id,
        'version': data['version'],
        'title': data['title'],
        'description': data.get('description', ''),
        'date': datetime.utcnow().isoformat() + 'Z',
        'type': data.get('type', 'minor'),
        'features': data.get('features', []),
        'improvements': data.get('improvements', []),
        'bugfixes': data.get('bugfixes', []),
        'tags': data.get('tags', [])
    }
    
    entries = load_journal()
    entries.append(new_entry)
    save_journal(entries)
    
    return jsonify({'success': True, 'entry': new_entry})


@bp.route('/api/journal/update/<entry_id>', methods=['PUT'])
@login_required
def api_journal_update(username, entry_id):
    accounts = load_accounts()
    admin_level = accounts.get(username, {}).get('level', 0)
    
    if admin_level < 4:
        return jsonify({'success': False, 'message': 'Apenas administradores podem editar entradas'}), 403
    
    data = request.json
    entries = load_journal()
    
    entry_index = None
    for i, entry in enumerate(entries):
        if entry.get('id') == entry_id:
            entry_index = i
            break
    
    if entry_index is None:
        return jsonify({'success': False, 'message': 'Entrada não encontrada'}), 404
    
    # Atualizar campos
    entries[entry_index].update({
        'version': data.get('version', entries[entry_index]['version']),
        'title': data.get('title', entries[entry_index]['title']),
        'description': data.get('description', entries[entry_index].get('description', '')),
        'type': data.get('type', entries[entry_index].get('type', 'minor')),
        'features': data.get('features', entries[entry_index].get('features', [])),
        'improvements': data.get('improvements', entries[entry_index].get('improvements', [])),
        'bugfixes': data.get('bugfixes', entries[entry_index].get('bugfixes', [])),
        'tags': data.get('tags', entries[entry_index].get('tags', []))
    })
    
    save_journal(entries)
    
    return jsonify({'success': True, 'entry': entries[entry_index]})


@bp.route('/api/journal/delete/<entry_id>', methods=['DELETE'])
@login_required
def api_journal_delete(username, entry_id):
    accounts = load_accounts()
    admin_level = accounts.get(username, {}).get('level', 0)
    
    if admin_level < 4:
        return jsonify({'success': False, 'message': 'Apenas administradores podem excluir entradas'}), 403
    
    entries = load_journal()
    
    entry_index = None
    for i, entry in enumerate(entries):
        if entry.get('id') == entry_id:
            entry_index = i
            break
    
    if entry_index is None:
        return jsonify({'success': False, 'message': 'Entrada não encontrada'}), 404
    
    removed = entries.pop(entry_index)
    save_journal(entries)
    
    return jsonify({'success': True, 'removed': removed})



