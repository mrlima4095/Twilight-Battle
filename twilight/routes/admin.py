"""Painel e APIs administrativas."""
import json
import os
import random
from datetime import datetime

from flask import Blueprint, jsonify, redirect, render_template, request

from twilight.auth.admin import admin_required, is_admin, is_super_admin
from twilight.auth.service import get_current_user, load_accounts, login_required, save_accounts
from twilight.cards.definitions import CARDS
from twilight.extensions import socketio
from twilight.state import games
from twilight.storage.story_saves import get_user_save_file
from twilight.game.chat import broadcast_system_message

bp = Blueprint('admin', __name__)

@bp.route('/admin')
@login_required
def admin_panel(username):
    """Painel administrativo web"""
    if not is_admin(username):
        return redirect('/')
    return render_template('admin.html', username=username, is_super=is_super_admin(username))

@bp.route('/api/admin/users')
@admin_required
def api_admin_users(username):
    """Lista todos os usuários cadastrados"""
    accounts = load_accounts()
    users = []
    
    for uname, data in accounts.items():
        # Encontrar jogo atual
        current_game = data.get('current_game')
        game_info = None
        if current_game and current_game in games:
            game = games[current_game]
            if uname in game.player_data:
                player = game.player_data[uname]
                game_info = {
                    'game_id': current_game,
                    'started': game.started,
                    'is_dead': player.get('dead', False),
                    'life': player.get('life', 0),
                    'hand_count': len(player.get('hand', []))
                }
        
        users.append({
            'username': uname,
            'created_at': data.get('created_at', 'Desconhecido'),
            'admin_level': data.get('admin_level', 0),
            'current_game': current_game,
            'game_info': game_info
        })
    
    return jsonify({'success': True, 'users': users})

@bp.route('/api/admin/user/<target_username>', methods=['DELETE'])
@admin_required
def api_admin_delete_user(admin_username, target_username):
    """Deleta um usuário (super admin only)"""
    if not is_super_admin(admin_username):
        return jsonify({'success': False, 'message': 'Apenas super admin pode deletar usuários'}), 403
    
    if target_username == admin_username:
        return jsonify({'success': False, 'message': 'Não pode deletar a si mesmo'}), 400
    
    accounts = load_accounts()
    if target_username not in accounts:
        return jsonify({'success': False, 'message': 'Usuário não encontrado'}), 404
    
    # Remover usuário de qualquer jogo ativo
    game_id = accounts[target_username].get('current_game')
    if game_id and game_id in games:
        game = games[game_id]
        if target_username in game.player_data:
            game.remove_player(target_username)
    
    # Deletar arquivo de save se existir
    save_file = get_user_save_file(target_username)
    if os.path.exists(save_file):
        os.remove(save_file)
    
    del accounts[target_username]
    save_accounts(accounts)
    
    return jsonify({'success': True, 'message': f'Usuário {target_username} deletado'})

@bp.route('/api/admin/user/<target_username>/admin-level', methods=['PUT'])
@admin_required
def api_admin_set_level(admin_username, target_username):
    """Define nível de admin de um usuário (super admin only)"""
    if not is_super_admin(admin_username):
        return jsonify({'success': False, 'message': 'Apenas super admin pode definir níveis de admin'}), 403
    
    data = request.json
    level = data.get('level', 0)
    
    if not isinstance(level, int) or level < 0 or level > 5:
        return jsonify({'success': False, 'message': 'Nível inválido (0-5)'}), 400
    
    accounts = load_accounts()
    if target_username not in accounts:
        return jsonify({'success': False, 'message': 'Usuário não encontrado'}), 404
    
    accounts[target_username]['admin_level'] = level
    save_accounts(accounts)
    
    return jsonify({'success': True, 'message': f'Nível de admin de {target_username} alterado para {level}'})

@bp.route('/api/admin/games')
@admin_required
def api_admin_games(username):
    """Lista todos os jogos ativos"""
    games_list = []
    for game_id, game in games.items():
        players_info = []
        for p in game.players:
            if p in game.player_data:
                player = game.player_data[p]
                players_info.append({
                    'username': p,
                    'name': player.get('name', p),
                    'life': player.get('life', 0),
                    'dead': player.get('dead', False),
                    'hand_count': len(player.get('hand', []))
                })
        
        spectators = [uname for uname, data in game.player_data.items() if data.get('spectator', False)]
        
        games_list.append({
            'id': game_id,
            'creator': game.creator,
            'started': game.started,
            'players': players_info,
            'player_count': len(game.players),
            'max_players': game.max_players,
            'spectators': spectators,
            'time_of_day': game.time_of_day,
            'current_turn': game.players[game.current_turn] if game.players else None,
            'deck_count': len(game.deck),
            'graveyard_count': len(game.graveyard),
            'private': game.private,
            'modifiers': game.modifiers
        })
    
    return jsonify({'success': True, 'games': games_list})

@bp.route('/api/admin/game/<game_id>/force-end', methods=['POST'])
@admin_required
def api_admin_force_end(admin_username, game_id):
    """Força o fim de um jogo (admin apenas)"""
    if game_id not in games:
        return jsonify({'success': False, 'message': 'Jogo não encontrado'}), 404
    
    game = games[game_id]
    
    # Notificar todos os jogadores
    socketio.emit('game_force_ended', {
        'message': f'Admin {admin_username} encerrou o jogo',
        'admin': admin_username
    }, room=game_id)
    
    # Limpar referências dos jogadores
    accounts = load_accounts()
    for username in game.players:
        if username in accounts and accounts[username].get('current_game') == game_id:
            accounts[username]['current_game'] = None
    
    # Remover espectadores também
    for username, data in game.player_data.items():
        if data.get('spectator', False) and username in accounts:
            if accounts[username].get('current_game') == game_id:
                accounts[username]['current_game'] = None
    
    save_accounts(accounts)
    
    # Remover o jogo
    del games[game_id]
    
    return jsonify({'success': True, 'message': f'Jogo {game_id} encerrado'})

@bp.route('/api/admin/game/<game_id>/sync')
@admin_required
def api_admin_sync_game(admin_username, game_id):
    """Força sincronização de um jogo"""
    if game_id not in games:
        return jsonify({'success': False, 'message': 'Jogo não encontrado'}), 404
    
    game = games[game_id]
    synced = 0
    
    for username in game.players:
        socket_id = game.get_socket_id(username)
        if socket_id and username in game.player_data:
            # Construir estado para cada jogador
            current_turn_username = None
            if game.players and game.current_turn < len(game.players):
                current_turn_username = game.players[game.current_turn]
            
            state = {
                'game_id': game_id,
                'started': game.started,
                'time_of_day': game.time_of_day,
                'time_cycle': game.time_cycle,
                'current_turn': current_turn_username,
                'players': {},
                'deck_count': len(game.deck),
                'graveyard_count': len(game.graveyard),
                'current_player_dead': game.player_data[username].get('dead', False)
            }
            
            for uname in game.players:
                if uname in game.player_data:
                    player_info = {
                        'name': game.player_data[uname]['name'],
                        'username': uname,
                        'life': game.player_data[uname]['life'] if not game.player_data[uname].get('dead', False) else 0,
                        'attack_bases': game.player_data[uname]['attack_bases'],
                        'defense_bases': game.player_data[uname]['defense_bases'],
                        'talisman_count': len(game.player_data[uname]['talismans']),
                        'runes': game.player_data[uname]['runes'],
                        'dead': game.player_data[uname].get('dead', False),
                        'observer': game.player_data[uname].get('observer', False)
                    }
                    
                    if uname == username and not player_info.get('dead', False):
                        player_info['hand'] = game.player_data[uname]['hand']
                        player_info['equipment'] = game.player_data[uname]['equipment']
                        player_info['talismans'] = game.player_data[uname]['talismans']
                    
                    state['players'][uname] = player_info
            
            socketio.emit('game_state', state, room=socket_id)
            synced += 1
    
    socketio.emit('admin_sync_complete', {
        'message': f'Admin {admin_username} forçou sincronização do jogo'
    }, room=game_id)
    
    return jsonify({'success': True, 'synced': synced, 'message': f'{synced} jogadores sincronizados'})

@bp.route('/api/admin/game/<game_id>/kick/<target_username>', methods=['POST'])
@admin_required
def api_admin_kick_player(admin_username, game_id, target_username):
    """Remove um jogador de um jogo (admin only)"""
    if game_id not in games:
        return jsonify({'success': False, 'message': 'Jogo não encontrado'}), 404
    
    game = games[game_id]
    
    if target_username not in game.player_data:
        return jsonify({'success': False, 'message': 'Jogador não encontrado no jogo'}), 404
    
    # Remover jogador
    success, was_creator, winner = game.remove_player(target_username)
    
    # Limpar jogo atual da conta
    accounts = load_accounts()
    if target_username in accounts and accounts[target_username].get('current_game') == game_id:
        accounts[target_username]['current_game'] = None
        save_accounts(accounts)
    
    # Notificar sala
    socketio.emit('player_kicked', {
        'username': target_username,
        'kicked_by': admin_username,
        'message': f'Jogador {target_username} foi removido pelo admin {admin_username}'
    }, room=game_id)
    
    if was_creator and game_id in games:
        # Criador foi removido, fechar jogo
        socketio.emit('room_closed', {
            'message': f'O criador foi removido pelo admin. A sala foi fechada.'
        }, room=game_id)
        del games[game_id]
        return jsonify({'success': True, 'message': f'Jogador {target_username} removido e sala fechada'})
    
    return jsonify({'success': True, 'message': f'Jogador {target_username} removido do jogo'})

# ==================== ADMIN GAME CONTROL ====================

@bp.route('/api/admin/game/<game_id>/state')
@admin_required
def api_admin_game_state(admin_username, game_id):
    """Retorna estado completo de um jogo para o admin"""
    if game_id not in games:
        return jsonify({'success': False, 'message': 'Jogo não encontrado'}), 404
    
    game = games[game_id]
    
    # Construir estado completo para admin (vê tudo)
    players_data = {}
    for username in game.players:
        if username in game.player_data:
            p = game.player_data[username]
            players_data[username] = {
                'name': p.get('name', username),
                'life': p.get('life', 0),
                'dead': p.get('dead', False),
                'hand': p.get('hand', []),
                'attack_bases': p.get('attack_bases', [None, None, None]),
                'defense_bases': p.get('defense_bases', [None, None, None, None, None, None]),
                'equipment': p.get('equipment', {}),
                'talismans': p.get('talismans', []),
                'runes': sum(1 for c in p.get('hand', []) if c.get('type') in ['rune', 'ritual'] or c.get('id') == 'runa'),
                'active_effects': p.get('active_effects', [])
            }
    
    spectators = [uname for uname, data in game.player_data.items() if data.get('spectator', False)]
    
    return jsonify({
        'success': True,
        'game': {
            'id': game_id,
            'started': game.started,
            'time_of_day': game.time_of_day,
            'current_turn': game.players[game.current_turn] if game.players else None,
            'players': game.players,
            'player_data': players_data,
            'spectators': spectators,
            'deck_count': len(game.deck),
            'graveyard_count': len(game.graveyard),
            'graveyard': [{'instance_id': c.get('instance_id'), 'name': c.get('name'), 'type': c.get('type')} for c in game.graveyard],
            'max_players': game.max_players,
            'modifiers': game.modifiers,
            'first_round': game.first_round,
            'attacks_blocked': game.attacks_blocked
        }
    })

@bp.route('/api/admin/game/<game_id>/player/<target_username>/give-card', methods=['POST'])
@admin_required
def api_admin_give_card(admin_username, game_id, target_username):
    """Dá uma carta específica para um jogador"""
    data = request.json
    card_id = data.get('card_id')
    quantity = data.get('quantity', 1)
    
    if not card_id:
        return jsonify({'success': False, 'message': 'ID da carta é obrigatório'}), 400
    
    if game_id not in games:
        return jsonify({'success': False, 'message': 'Jogo não encontrado'}), 404
    
    game = games[game_id]
    
    if target_username not in game.player_data:
        return jsonify({'success': False, 'message': 'Jogador não encontrado'}), 404
    
    # Encontrar a carta
    if card_id in CARDS:
        card_info = CARDS[card_id]
    else:
        # Procurar por nome
        for cid, cinfo in CARDS.items():
            if cinfo['name'].lower() == card_id.lower():
                card_info = cinfo
                card_id = cid
                break
        else:
            return jsonify({'success': False, 'message': f'Carta "{card_id}" não encontrada'}), 404
    
    player = game.player_data[target_username]
    cards_given = []
    
    for _ in range(min(quantity, 50)):  # Máximo 50 cartas por vez
        new_card = card_info.copy()
        new_card['instance_id'] = str(uuid.uuid4())[:8]
        player['hand'].append(new_card)
        cards_given.append(new_card['name'])
    
    # Notificar o jogador
    socketio.emit('admin_action', {
        'type': 'cards_given',
        'cards': cards_given,
        'quantity': len(cards_given),
        'message': f'Admin deu {len(cards_given)}x {card_info["name"]} para sua mão'
    }, room=game_id)
    
    broadcast_system_message(game_id, f'📦 Admin deu {len(cards_given)}x {card_info["name"]} para {target_username}')
    
    return jsonify({
        'success': True,
        'cards_given': len(cards_given),
        'card_name': card_info['name'],
        'message': f'{len(cards_given)}x {card_info["name"]} dada para {target_username}'
    })

@bp.route('/api/admin/game/<game_id>/player/<target_username>/remove-card', methods=['POST'])
@admin_required
def api_admin_remove_card(admin_username, game_id, target_username):
    """Remove uma carta específica da mão do jogador"""
    data = request.json
    card_instance_id = data.get('card_instance_id')
    card_name = data.get('card_name')
    quantity = data.get('quantity', 1)
    
    if not card_instance_id and not card_name:
        return jsonify({'success': False, 'message': 'ID da carta ou nome é obrigatório'}), 400
    
    if game_id not in games:
        return jsonify({'success': False, 'message': 'Jogo não encontrado'}), 404
    
    game = games[game_id]
    
    if target_username not in game.player_data:
        return jsonify({'success': False, 'message': 'Jogador não encontrado'}), 404
    
    player = game.player_data[target_username]
    cards_removed = []
    
    if card_instance_id:
        # Remover por instance_id
        for i, card in enumerate(player['hand']):
            if card.get('instance_id') == card_instance_id:
                cards_removed.append(player['hand'].pop(i))
                break
    else:
        # Remover por nome
        to_remove = []
        for card in player['hand']:
            if card['name'].lower() == card_name.lower() and len(to_remove) < quantity:
                to_remove.append(card)
        
        for card in to_remove:
            player['hand'].remove(card)
            cards_removed.append(card)
    
    if cards_removed:
        socketio.emit('admin_action', {
            'type': 'cards_removed',
            'cards': [c['name'] for c in cards_removed],
            'message': f'Admin removeu {len(cards_removed)}x {cards_removed[0]["name"]} da sua mão'
        }, room=game_id)
        
        broadcast_system_message(game_id, f'🗑️ Admin removeu {len(cards_removed)}x {cards_removed[0]["name"]} de {target_username}')
    
    return jsonify({
        'success': True,
        'cards_removed': len(cards_removed),
        'removed_cards': [c['name'] for c in cards_removed]
    })

@bp.route('/api/admin/game/<game_id>/player/<target_username>/modify-life', methods=['POST'])
@admin_required
def api_admin_modify_life(admin_username, game_id, target_username):
    """Modifica a vida de um jogador"""
    data = request.json
    delta = data.get('delta', 0)  # pode ser positivo (cura) ou negativo (dano)
    new_life = data.get('new_life')
    
    if game_id not in games:
        return jsonify({'success': False, 'message': 'Jogo não encontrado'}), 404
    
    game = games[game_id]
    
    if target_username not in game.player_data:
        return jsonify({'success': False, 'message': 'Jogador não encontrado'}), 404
    
    player = game.player_data[target_username]
    old_life = player['life']
    
    if new_life is not None:
        player['life'] = max(0, int(new_life))
        message = f'Admin alterou vida de {target_username}: {old_life} → {player["life"]}'
    else:
        player['life'] = max(0, player['life'] + delta)
        if delta < 0:
            message = f'Admin causou {abs(delta)} de dano a {target_username}: {old_life} → {player["life"]}'
        else:
            message = f'Admin curou {delta} de {target_username}: {old_life} → {player["life"]}'
    
    # Verificar morte
    if player['life'] <= 0 and not player.get('dead', False):
        game.process_player_death(target_username)
        message += f' 💀 {target_username} MORREU!'
    
    socketio.emit('admin_action', {
        'type': 'life_change',
        'target': target_username,
        'old_life': old_life,
        'new_life': player['life'],
        'message': message
    }, room=game_id)
    
    return jsonify({
        'success': True,
        'old_life': old_life,
        'new_life': player['life'],
        'dead': player.get('dead', False)
    })

@bp.route('/api/admin/game/<game_id>/player/<target_username>/modify-hand', methods=['POST'])
@admin_required
def api_admin_modify_hand(admin_username, game_id, target_username):
    """Adiciona ou remove cartas da mão (operação completa)"""
    data = request.json
    action = data.get('action')  # 'add', 'remove', 'clear', 'set'
    cards = data.get('cards', [])  # lista de card_ids para adicionar
    
    if game_id not in games:
        return jsonify({'success': False, 'message': 'Jogo não encontrado'}), 404
    
    game = games[game_id]
    
    if target_username not in game.player_data:
        return jsonify({'success': False, 'message': 'Jogador não encontrado'}), 404
    
    player = game.player_data[target_username]
    
    if action == 'clear':
        player['hand'] = []
        message = f'Admin limpou toda a mão de {target_username}'
    elif action == 'add':
        for card_id in cards:
            if card_id in CARDS:
                new_card = CARDS[card_id].copy()
                new_card['instance_id'] = str(uuid.uuid4())[:8]
                player['hand'].append(new_card)
        message = f'Admin adicionou {len(cards)} carta(s) para {target_username}'
    elif action == 'set':
        player['hand'] = []
        for card_id in cards:
            if card_id in CARDS:
                new_card = CARDS[card_id].copy()
                new_card['instance_id'] = str(uuid.uuid4())[:8]
                player['hand'].append(new_card)
        message = f'Admin definiu a mão de {target_username} com {len(cards)} carta(s)'
    else:
        return jsonify({'success': False, 'message': 'Ação inválida'}), 400
    
    socketio.emit('admin_action', {
        'type': 'hand_modified',
        'target': target_username,
        'hand_count': len(player['hand']),
        'message': message
    }, room=game_id)
    
    return jsonify({
        'success': True,
        'hand_count': len(player['hand']),
        'message': message
    })

@bp.route('/api/admin/game/<game_id>/player/<target_username>/field', methods=['POST'])
@admin_required
def api_admin_modify_field(admin_username, game_id, target_username):
    """Modifica o campo (adiciona/remove cartas em ataque/defesa)"""
    data = request.json
    position_type = data.get('position_type')  # 'attack' ou 'defense'
    position_index = data.get('position_index')
    card_id = data.get('card_id')
    action = data.get('action')  # 'set', 'remove'
    
    if game_id not in games:
        return jsonify({'success': False, 'message': 'Jogo não encontrado'}), 404
    
    game = games[game_id]
    
    if target_username not in game.player_data:
        return jsonify({'success': False, 'message': 'Jogador não encontrado'}), 404
    
    player = game.player_data[target_username]
    
    if action == 'remove':
        if position_type == 'attack' and 0 <= position_index < len(player['attack_bases']):
            card = player['attack_bases'][position_index]
            if card:
                player['attack_bases'][position_index] = None
                game.graveyard.append(card)
                message = f'Admin removeu {card["name"]} da posição de ataque {position_index} de {target_username}'
        elif position_type == 'defense' and 0 <= position_index < len(player['defense_bases']):
            card = player['defense_bases'][position_index]
            if card:
                player['defense_bases'][position_index] = None
                game.graveyard.append(card)
                message = f'Admin removeu {card["name"]} da posição de defesa {position_index} de {target_username}'
        else:
            return jsonify({'success': False, 'message': 'Posição inválida'}), 400
    
    elif action == 'set':
        if not card_id or card_id not in CARDS:
            return jsonify({'success': False, 'message': 'Carta inválida'}), 400
        
        new_card = CARDS[card_id].copy()
        new_card['instance_id'] = str(uuid.uuid4())[:8]
        
        if position_type == 'attack' and 0 <= position_index < len(player['attack_bases']):
            # Se já tem carta, vai pro cemitério
            if player['attack_bases'][position_index]:
                game.graveyard.append(player['attack_bases'][position_index])
            player['attack_bases'][position_index] = new_card
            message = f'Admin colocou {new_card["name"]} na posição de ataque {position_index} de {target_username}'
        elif position_type == 'defense' and 0 <= position_index < len(player['defense_bases']):
            if player['defense_bases'][position_index]:
                game.graveyard.append(player['defense_bases'][position_index])
            player['defense_bases'][position_index] = new_card
            message = f'Admin colocou {new_card["name"]} na posição de defesa {position_index} de {target_username}'
        else:
            return jsonify({'success': False, 'message': 'Posição inválida'}), 400
    else:
        return jsonify({'success': False, 'message': 'Ação inválida'}), 400
    
    socketio.emit('admin_action', {
        'type': 'field_modified',
        'target': target_username,
        'message': message
    }, room=game_id)
    
    return jsonify({'success': True, 'message': message})

@bp.route('/api/admin/game/<game_id>/set-turn', methods=['POST'])
@admin_required
def api_admin_set_turn(admin_username, game_id):
    """Define o turno atual do jogo"""
    data = request.json
    target_username = data.get('target_username')
    
    if game_id not in games:
        return jsonify({'success': False, 'message': 'Jogo não encontrado'}), 404
    
    game = games[game_id]
    
    if target_username not in game.players:
        return jsonify({'success': False, 'message': 'Jogador não encontrado no jogo'}), 404
    
    # Encontrar índice do jogador
    for i, p in enumerate(game.players):
        if p == target_username:
            game.current_turn = i
            break
    
    broadcast_system_message(game_id, f'👑 Admin alterou o turno para {target_username}')
    
    socketio.emit('turn_changed', {
        'new_turn': target_username,
        'message': f'Turno alterado pelo admin para {target_username}'
    }, room=game_id)
    
    return jsonify({'success': True, 'current_turn': target_username})

@bp.route('/api/admin/game/<game_id>/set-time', methods=['POST'])
@admin_required
def api_admin_set_time(admin_username, game_id):
    """Define o ciclo de dia/noite"""
    data = request.json
    time_of_day = data.get('time_of_day')  # 'day' ou 'night'
    
    if game_id not in games:
        return jsonify({'success': False, 'message': 'Jogo não encontrado'}), 404
    
    game = games[game_id]
    
    if time_of_day not in ['day', 'night']:
        return jsonify({'success': False, 'message': 'Valor inválido'}), 400
    
    old_time = game.time_of_day
    game.time_of_day = time_of_day
    
    if time_of_day == 'day':
        game.apply_day_effects()
    
    broadcast_system_message(game_id, f'🌓 Admin alterou o ciclo: {old_time.upper()} → {time_of_day.upper()}')
    
    socketio.emit('time_changed', {
        'new_time': time_of_day,
        'old_time': old_time,
        'message': f'Ciclo alterado pelo admin para {time_of_day.upper()}'
    }, room=game_id)
    
    return jsonify({'success': True, 'time_of_day': time_of_day})

@bp.route('/api/admin/game/<game_id>/deck/shuffle', methods=['POST'])
@admin_required
def api_admin_shuffle_deck(admin_username, game_id):
    """Embaralha o deck do jogo"""
    if game_id not in games:
        return jsonify({'success': False, 'message': 'Jogo não encontrado'}), 404
    
    game = games[game_id]
    random.shuffle(game.deck)
    
    broadcast_system_message(game_id, f'🃏 Admin embaralhou o deck do jogo')
    
    return jsonify({'success': True, 'deck_count': len(game.deck)})

@bp.route('/api/admin/game/<game_id>/deck/peek', methods=['GET'])
@admin_required
def api_admin_peek_deck(admin_username, game_id):
    """Vê as próximas N cartas do deck"""
    quantity = int(request.args.get('quantity', 10))
    
    if game_id not in games:
        return jsonify({'success': False, 'message': 'Jogo não encontrado'}), 404
    
    game = games[game_id]
    
    peek_cards = []
    for i in range(min(quantity, len(game.deck))):
        card = game.deck[i]
        peek_cards.append({
            'position': i,
            'name': card.get('name'),
            'type': card.get('type'),
            'attack': card.get('attack'),
            'life': card.get('life')
        })
    
    return jsonify({
        'success': True,
        'deck_count': len(game.deck),
        'peek_count': len(peek_cards),
        'cards': peek_cards
    })

@bp.route('/api/admin/game/<game_id>/graveyard/revive', methods=['POST'])
@admin_required
def api_admin_revive_card(admin_username, game_id):
    """Revive uma carta do cemitério para a mão de um jogador"""
    data = request.json
    target_username = data.get('target_username')
    card_index = data.get('card_index')
    
    if game_id not in games:
        return jsonify({'success': False, 'message': 'Jogo não encontrado'}), 404
    
    game = games[game_id]
    
    if target_username not in game.player_data:
        return jsonify({'success': False, 'message': 'Jogador não encontrado'}), 404
    
    if card_index is None or card_index < 0 or card_index >= len(game.graveyard):
        return jsonify({'success': False, 'message': 'Índice de carta inválido'}), 400
    
    card = game.graveyard.pop(card_index)
    game.player_data[target_username]['hand'].append(card)
    
    # Se for criatura, restaurar vida original
    if card.get('type') == 'creature' and card.get('id') in CARDS:
        card['life'] = CARDS[card['id']].get('life', card.get('life', 512))
    
    broadcast_system_message(game_id, f'✨ Admin reviveu {card["name"]} do cemitério para {target_username}')
    
    return jsonify({
        'success': True,
        'card': card['name'],
        'target': target_username
    })

@bp.route('/api/admin/game/<game_id>/player/<target_username>/kill', methods=['POST'])
@admin_required
def api_admin_kill_player(admin_username, game_id, target_username):
    """Mata um jogador instantaneamente"""
    if game_id not in games:
        return jsonify({'success': False, 'message': 'Jogo não encontrado'}), 404
    
    game = games[game_id]
    
    if target_username not in game.player_data:
        return jsonify({'success': False, 'message': 'Jogador não encontrado'}), 404
    
    if game.player_data[target_username].get('dead', False):
        return jsonify({'success': False, 'message': 'Jogador já está morto'}), 400
    
    game.process_player_death(target_username)
    
    broadcast_system_message(game_id, f'💀 Admin matou {target_username}!')
    
    return jsonify({'success': True, 'message': f'{target_username} foi morto'})

@bp.route('/api/admin/game/<game_id>/player/<target_username>/revive', methods=['POST'])
@admin_required
def api_admin_revive_player(admin_username, game_id, target_username):
    """Revive um jogador morto"""
    if game_id not in games:
        return jsonify({'success': False, 'message': 'Jogo não encontrado'}), 404
    
    game = games[game_id]
    
    if target_username not in game.player_data:
        return jsonify({'success': False, 'message': 'Jogador não encontrado'}), 404
    
    player = game.player_data[target_username]
    
    if not player.get('dead', False):
        return jsonify({'success': False, 'message': 'Jogador não está morto'}), 400
    
    player['dead'] = False
    player['observer'] = False
    player['life'] = 5000
    
    broadcast_system_message(game_id, f'✨ Admin reviveu {target_username}!')
    
    return jsonify({'success': True, 'message': f'{target_username} foi revivido'})

@bp.route('/api/admin/cards/list')
@admin_required
def api_admin_cards_list(admin_username):
    """Lista todas as cartas disponíveis"""
    cards_list = []
    for card_id, card_info in CARDS.items():
        cards_list.append({
            'id': card_id,
            'name': card_info['name'],
            'type': card_info['type'],
            'attack': card_info.get('attack', ''),
            'life': card_info.get('life', ''),
            'protection': card_info.get('protection', ''),
            'description': card_info.get('description', '')[:100]
        })
    
    # Ordenar por tipo e nome
    cards_list.sort(key=lambda x: (x['type'], x['name']))
    
    return jsonify({
        'success': True,
        'count': len(cards_list),
        'cards': cards_list
    })


