"""API do journal / diário do reino."""
import time
import uuid

from flask import Blueprint, jsonify, request

from twilight.auth.service import get_current_user, load_accounts, login_required
from twilight.config import now_sp_iso
from twilight.storage.journal import load_journal, save_journal

bp = Blueprint('journal', __name__)

# Tipos públicos de release
PUBLIC_TYPES = frozenset({'major', 'minor', 'patch'})
# ROADMAP e afins: só staff
ADMIN_ONLY_TYPES = frozenset({'roadmap', 'plan', 'internal'})


def _admin_level(username):
    if not username:
        return 0
    acc = load_accounts().get(username, {}) or {}
    try:
        return int(acc.get('admin_level', acc.get('level', 0)) or 0)
    except (TypeError, ValueError):
        return 0


def _is_admin_only_entry(entry):
    """ROADMAP / visibility admin — oculto de usuários comuns."""
    if not entry:
        return False
    t = (entry.get('type') or '').strip().lower()
    if t in ADMIN_ONLY_TYPES:
        return True
    vis = (entry.get('visibility') or entry.get('visible') or 'public')
    if isinstance(vis, str) and vis.strip().lower() in ('admin', 'private', 'hidden', 'staff'):
        return True
    if entry.get('hidden') is True:
        return True
    return False


def _normalize_entry_visibility(entry):
    """Garante visibility coerente com type=roadmap."""
    if not entry:
        return entry
    t = (entry.get('type') or '').strip().lower()
    if t in ADMIN_ONLY_TYPES:
        entry['visibility'] = 'admin'
        entry['type'] = 'roadmap' if t in ('plan', 'internal', 'roadmap') else t
    else:
        entry.setdefault('visibility', 'public')
    return entry


@bp.route('/api/journal/entries')
def api_journal_entries():
    username = get_current_user()
    can_see_roadmap = _admin_level(username) >= 1

    entries = load_journal()
    if not can_see_roadmap:
        entries = [e for e in entries if not _is_admin_only_entry(e)]

    entries_sorted = sorted(entries, key=lambda x: x.get('date', ''), reverse=True)
    return jsonify({
        'success': True,
        'entries': entries_sorted,
        'can_see_roadmap': can_see_roadmap,
    })


@bp.route('/api/journal/entry/<entry_id>')
def api_journal_entry(entry_id):
    username = get_current_user()
    can_see_roadmap = _admin_level(username) >= 1

    entries = load_journal()
    for entry in entries:
        if entry.get('id') == entry_id:
            if _is_admin_only_entry(entry) and not can_see_roadmap:
                return jsonify({'success': False, 'message': 'Entrada não encontrada'}), 404
            return jsonify({'success': True, 'entry': entry})
    return jsonify({'success': False, 'message': 'Entrada não encontrada'}), 404


@bp.route('/api/journal/create', methods=['POST'])
@login_required
def api_journal_create(username):
    admin_level = _admin_level(username)
    
    if admin_level < 4:
        return jsonify({'success': False, 'message': 'Apenas administradores podem criar entradas'}), 403
    
    data = request.json or {}
    
    # Validar campos obrigatórios
    if not data.get('version') or not data.get('title'):
        return jsonify({'success': False, 'message': 'Versão e título são obrigatórios'}), 400

    entry_type = (data.get('type') or 'minor').strip().lower()
    if entry_type in ('plan', 'internal'):
        entry_type = 'roadmap'
    
    entry_id = str(int(time.time() * 1000))
    
    new_entry = {
        'id': entry_id,
        'version': data['version'],
        'title': data['title'],
        'description': data.get('description', ''),
        'date': now_sp_iso(),
        'type': entry_type,
        'visibility': 'admin' if entry_type in ADMIN_ONLY_TYPES else data.get('visibility', 'public'),
        'features': data.get('features', []),
        'improvements': data.get('improvements', []),
        'bugfixes': data.get('bugfixes', []),
        'tags': data.get('tags', [])
    }
    _normalize_entry_visibility(new_entry)
    
    entries = load_journal()
    entries.append(new_entry)
    save_journal(entries)
    
    return jsonify({'success': True, 'entry': new_entry})


@bp.route('/api/journal/update/<entry_id>', methods=['PUT'])
@login_required
def api_journal_update(username, entry_id):
    admin_level = _admin_level(username)
    
    if admin_level < 4:
        return jsonify({'success': False, 'message': 'Apenas administradores podem editar entradas'}), 403
    
    data = request.json or {}
    entries = load_journal()
    
    entry_index = None
    for i, entry in enumerate(entries):
        if entry.get('id') == entry_id:
            entry_index = i
            break
    
    if entry_index is None:
        return jsonify({'success': False, 'message': 'Entrada não encontrada'}), 404

    entry_type = data.get('type', entries[entry_index].get('type', 'minor'))
    if isinstance(entry_type, str):
        entry_type = entry_type.strip().lower()
        if entry_type in ('plan', 'internal'):
            entry_type = 'roadmap'
    
    # Atualizar campos
    entries[entry_index].update({
        'version': data.get('version', entries[entry_index]['version']),
        'title': data.get('title', entries[entry_index]['title']),
        'description': data.get('description', entries[entry_index].get('description', '')),
        'type': entry_type,
        'features': data.get('features', entries[entry_index].get('features', [])),
        'improvements': data.get('improvements', entries[entry_index].get('improvements', [])),
        'bugfixes': data.get('bugfixes', entries[entry_index].get('bugfixes', [])),
        'tags': data.get('tags', entries[entry_index].get('tags', []))
    })
    if 'visibility' in data:
        entries[entry_index]['visibility'] = data.get('visibility')
    _normalize_entry_visibility(entries[entry_index])
    
    save_journal(entries)
    
    return jsonify({'success': True, 'entry': entries[entry_index]})


@bp.route('/api/journal/delete/<entry_id>', methods=['DELETE'])
@login_required
def api_journal_delete(username, entry_id):
    accounts = load_accounts()
    acc = accounts.get(username, {})
    admin_level = acc.get('admin_level', acc.get('level', 0))
    
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



