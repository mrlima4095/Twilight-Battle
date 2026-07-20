"""Handlers Socket.IO da partida multiplayer."""
import time

from flask import request
from flask_socketio import emit, join_room, leave_room

from twilight.config import now_sp_str
from twilight.auth.service import (
    clear_game_from_all_accounts,
    clear_user_game,
    get_current_user,
    load_accounts,
    save_accounts,
    update_user_game,
)
from twilight.extensions import socketio
from twilight.game.chat import add_chat_message, broadcast_system_message, censor_text
from twilight.game.engine import Game
from twilight.game.session import close_game, schedule_close_finished_game
from twilight.state import chat_messages, games, players


def _emit_game_over_and_rematch(game_id, game, winner, winner_name):
    """Emite vitória e reabre a mesma sala em lobby (mesmo id/mods)."""
    # limpa ponteiros só se alguém não for ficar — aqui mantemos current_game
    broadcast_system_message(game_id, f'🏆 {winner_name} VENCEU O JOGO! 🏆')
    emit('game_over', {
        'winner': winner,
        'winner_name': winner_name,
        'message': f'🏆 {winner_name} VENCEU O JOGO!',
        'rematch': True,
        'same_room': True,
        'game_id': game_id,
    }, room=game_id)

    lobby = game.reset_to_lobby(last_winner=winner)
    players_list = [
        {'username': p, 'name': game.player_data[p]['name']}
        for p in game.players
        if p in game.player_data
    ]
    broadcast_system_message(
        game_id,
        f'🔄 Sala reaberta para nova partida! (mesmo código {game_id}) — o criador pode iniciar de novo.'
    )
    socketio.emit('lobby_reset', {
        'game_id': game_id,
        'last_winner': winner,
        'last_winner_name': winner_name,
        'players': players_list,
        'modifiers': lobby.get('modifiers', []),
        'creator': game.creator,
        'message': 'Sala pronta para jogar de novo. Aguardando o criador iniciar.',
    }, room=game_id)

@socketio.on('connect')
def handle_connect(): pass

@socketio.on('disconnect')
def handle_disconnect():
    # Encontrar jogo e jogador
    for game_id, game in games.items():
        username = game.get_player_by_socket(request.sid)
        if username:
            # Remover mapeamento socket
            if request.sid in game.socket_to_username:
                del game.socket_to_username[request.sid]
            
            # Não remover o jogador automaticamente, apenas marcar como offline
            # O jogador pode reconectar depois
            emit('player_disconnected', {
                'username': username
            }, room=game_id)
            break

@socketio.on('join_game')
def handle_join_game(data):
    game_id = data['game_id']
    username = get_current_user()
    if not username:
        emit('error', {'message': 'Usuário não autenticado'})
        return
    if game_id not in games:
        emit('error', {'message': 'Jogo não encontrado'})
        return
    game = games[game_id]

    # Se já começou e o usuário não está no jogo, não permite
    if game.started and username not in game.player_data:
        emit('error', {'message': 'Jogo já começou. Use espectador se quiser assistir.'})
        return

    # Caso 1: jogador já existe (reconexão) — também no lobby pós-rematch
    if username in game.player_data:
        result = game.reconnect_player(request.sid, username)
        if result['success']:
            join_room(game_id)
            update_user_game(username, game_id)
            if not game.started:
                broadcast_system_message(game_id, f'{username} entrou na sala')
            else:
                broadcast_system_message(game_id, f'{username} reconectou ao jogo')
            payload = dict(result) if isinstance(result, dict) else {'success': True}
            payload.update({
                'username': username,
                'game_started': game.started,
                'finished': bool(getattr(game, 'finished', False)),
                'winner': getattr(game, 'winner', None),
                'winner_name': None,
            })
            emit('reconnect_success', payload)
            # avisa lista de jogadores no lobby
            if not game.started:
                players_list = [
                    {'username': p, 'name': game.player_data[p]['name']}
                    for p in game.players if p in game.player_data
                ]
                emit('player_joined', {
                    'username': username,
                    'players': players_list,
                }, room=game_id)
        else:
            emit('error', {'message': result['message']})
        return

    # Caso 2: novo jogador (apenas se jogo não começou)
    if game.started:
        emit('error', {'message': 'Jogo já começou. Use espectador se quiser assistir.'})
        return

    if game.add_player(request.sid, username):
        join_room(game_id)
        update_user_game(username, game_id)
        broadcast_system_message(game_id, f'{username} entrou na sala')
        # Tutorial: humano joga primeiro
        if getattr(game, 'tutorial', False) and username in game.players:
            try:
                game.players.remove(username)
                game.players.insert(0, username)
                game.current_turn = 0
            except ValueError:
                pass
        players_list = [
            {
                'username': p,
                'name': game.player_data[p]['name'],
                'is_bot': bool(game.player_data[p].get('is_bot')),
            }
            for p in game.players
        ]
        emit('player_joined', {
            'username': username,
            'players': players_list,
            'tutorial': bool(getattr(game, 'tutorial', False)),
        }, room=game_id)

        # Tutorial: auto-inicia com 2 jogadores (humano + mentor)
        if (
            getattr(game, 'tutorial', False)
            and not game.started
            and len(game.players) >= 2
        ):
            game.started = True
            game.finished = False
            game.finished_at = None
            game.winner = None
            game._game_over_emitted = False
            broadcast_system_message(
                game_id,
                '🎓 Tutorial iniciado! Você treina contra o Mentor (fácil). Veja as dicas no painel.',
            )
            socketio.emit('game_started', {
                'game_id': game_id,
                'tutorial': True,
            }, room=game_id)
            from twilight.game.ai import schedule_bot_turn
            schedule_bot_turn(game_id, delay=1.2)
    else:
        emit('error', {'message': 'Não foi possível entrar no jogo'})

@socketio.on('leave_game')
def handle_leave_game(data):
    """Jogador sai voluntariamente do jogo"""
    game_id = data['game_id']
    
    # Obter username do token
    username = get_current_user()
    if not username:
        emit('error', {'message': 'Usuário não autenticado'})
        return
    
    if game_id not in games:
        emit('error', {'message': 'Jogo não encontrado'})
        return
    
    game = games[game_id]

    if username not in game.player_data:
        # ainda limpa ponteiro da conta se sobrou
        clear_user_game(username, game_id)
        emit('error', {'message': 'Jogador não encontrado'})
        return
    
    # Remover jogador
    success, was_creator, winner = game.remove_player(username)
    broadcast_system_message(game_id, f'{username} saiu da sala')
    
    # Limpar jogo atual da conta do usuário
    clear_user_game(username, game_id)
    
    if was_creator:
        close_game(
            game_id,
            message=f'O criador da sala saiu. A sala {game_id} foi fechada.',
            notify=True,
        )
        emit('force_redirect', {
            'url': '/',
            'message': 'A sala foi fechada porque o criador saiu.'
        }, room=game_id)
    else:
        emit('player_left', {
            'username': username,
            'message': f'{username} saiu do jogo'
        }, room=game_id)

        # Último em pé por desistência → vitória + rematch na mesma sala
        if winner:
            already = getattr(game, '_game_over_emitted', False)
            game.end_game(winner)
            if not already:
                game._game_over_emitted = True
                winner_name = game.player_data.get(winner, {}).get('name', winner)
                _emit_game_over_and_rematch(game_id, game, winner, winner_name)

        # Sala vazia (ninguém restou) → fecha
        if game_id in games and len(games[game_id].players) == 0:
            close_game(game_id, message=f'Sala {game_id} vazia — fechada.', notify=False)
    
    # Remover da sala
    leave_room(game_id)

@socketio.on('get_game_state')
def handle_get_game_state(data):
    game_id = data['game_id']
    
    if game_id not in games:
        emit('error', {'message': 'Jogo não encontrado'})
        return
    
    game = games[game_id]
    username = game.get_player_by_socket(request.sid)
    
    if not username:
        emit('error', {'message': 'Jogador não encontrado'})
        return
    
    # Determinar o jogador da vez
    current_turn_username = None
    if game.players and game.current_turn < len(game.players):
        current_turn_username = game.players[game.current_turn]
    
    # Verificar se é espectador
    is_spectator = game.player_data[username].get('spectator', False)
    
    # Filtrar informações para o jogador
    state = {
        'game_id': game_id,
        'started': game.started,
        'finished': bool(getattr(game, 'finished', False)),
        'winner': getattr(game, 'winner', None),
        'winner_name': (
            game.player_data.get(game.winner, {}).get('name')
            if getattr(game, 'winner', None) and game.winner in game.player_data
            else getattr(game, 'winner', None)
        ),
        'time_of_day': game.time_of_day,
        'time_cycle': game.time_cycle,
        'current_turn': current_turn_username,
        'players': {},
        'deck_count': len(game.deck),
        'graveyard_count': len(game.graveyard),
        'is_spectator': is_spectator,
        'spectators': [],
        'modifiers': list(game.modifiers or []),
        'attack_slot_count': getattr(game, 'attack_slot_count', 3),
        'defense_slot_count': getattr(game, 'defense_slot_count', 6),
        'tutorial': bool(getattr(game, 'tutorial', False)),
        'starting_life': getattr(game, 'starting_life', 1200),
        'day_cycle_length': getattr(game, 'day_cycle_length', 24),
        'first_round': bool(getattr(game, 'first_round', False)),
        'attacks_blocked': bool(getattr(game, 'attacks_blocked', False)),
    }
    
    # Coletar lista de espectadores
    for uname, data in game.player_data.items():
        if data.get('spectator', False) and uname != username:
            state['spectators'].append({
                'username': uname,
                'name': data['name']
            })
    
    # Informações de todos os jogadores
    for uname in game.players:
        if uname in game.player_data:
            player_data = game.player_data[uname]
            
            # Para cada carta em campo, verificar se precisa ofuscar
            attack_bases = []
            for card in player_data['attack_bases']:
                if card:
                    attack_bases.append(game.get_card_for_player(card, username, uname))
                else:
                    attack_bases.append(None)
            
            defense_bases = []
            for card in player_data['defense_bases']:
                if card:
                    defense_bases.append(game.get_card_for_player(card, username, uname))
                else:
                    defense_bases.append(None)
            
            player_info = {
                'name': player_data['name'],
                'username': uname,
                'life': player_data['life'] if not player_data.get('dead', False) else 0,
                'attack_bases': attack_bases,
                'defense_bases': defense_bases,
                'talisman_count': game.get_player_talismans_count(uname),
                'runes': game.get_player_runes_count(uname),
                'dead': player_data.get('dead', False),
                'observer': player_data.get('observer', False),
                'is_bot': bool(player_data.get('is_bot', False)),
            }
            
            # Informações privadas apenas para o próprio jogador (não para espectadores)
            if uname == username and not is_spectator and not player_info.get('dead', False):
                player_info['hand'] = player_data['hand']
                player_info['equipment'] = player_data['equipment']
                player_info['talismans'] = player_data['talismans']
            
            state['players'][uname] = player_info
    
    emit('game_state', state)

@socketio.on('get_graveyard')
def handle_get_graveyard(data):
    """Retorna lista de cartas no cemitério"""
    game_id = data['game_id']

    if game_id not in games:
        emit('error', {'message': 'Jogo não encontrado'})
        return
    
    game = games[game_id]
    username = game.get_player_by_socket(request.sid)
    
    if not username:
        emit('error', {'message': 'Jogador não encontrado'})
        return
    
    graveyard_cards = game.get_graveyard_cards()
    
    emit('graveyard_list', {
        'cards': graveyard_cards,
        'count': len(graveyard_cards)
    })

@socketio.on('get_spells')
def handle_get_spells(data):
    """Retorna lista de feitiços disponíveis para o jogador"""
    game_id = data['game_id']
    
    if game_id not in games:
        emit('error', {'message': 'Jogo não encontrado'})
        return
    
    game = games[game_id]
    username = game.get_player_by_socket(request.sid)
    
    if not username:
        emit('error', {'message': 'Jogador não encontrado'})
        return
    
    spells_data = game.get_available_spells(username)
    
    emit('spells_list', spells_data)

@socketio.on('get_rituals')
def handle_get_rituals(data):
    """Retorna lista de rituais disponíveis para o jogador"""
    game_id = data['game_id']
    
    if game_id not in games:
        emit('error', {'message': 'Jogo não encontrado'})
        return
    
    game = games[game_id]
    player_id = request.sid
    
    if player_id not in game.player_data:
        emit('error', {'message': 'Jogador não encontrado'})
        return
    
    rituals = game.get_available_rituals(player_id)
    
    emit('rituals_list', {
        'rituals': rituals,
        'count': len(rituals)
    })

@socketio.on('spectate_game')
def handle_spectate_game(data):
    """Entrar como espectador em um jogo em andamento"""
    game_id = data['game_id']
    
    # Obter username do token
    username = get_current_user()
    if not username:
        emit('error', {'message': 'Usuário não autenticado'})
        return
    
    if game_id not in games:
        emit('error', {'message': 'Jogo não encontrado'})
        return
    
    game = games[game_id]
    
    # Verificar se já está como jogador
    if username in game.players:
        # Já é jogador, fazer reconnect normal
        socketio.emit('reconnect_game', {'game_id': game_id})
        return
    
    # Verificar se já é espectador
    if username in game.player_data and game.player_data[username].get('spectator', False):
        # Atualizar socket
        game.reconnect_player(request.sid, username)
        join_room(game_id)
        emit('spectate_success', {
            'username': username,
            'game_started': game.started,
            'spectator': True
        })
        return
    
    # Adicionar como novo espectador
    success, message = game.add_spectator(request.sid, username)
    
    if success:
        join_room(game_id)
        broadcast_system_message(game_id, f'👁️ {username} entrou como espectador')
        
        # Atualizar jogo atual na conta (opcional para espectadores)
        update_user_game(username, game_id)
        
        # Lista de jogadores para o espectador
        players_list = [{'username': p, 'name': game.player_data[p]['name']} for p in game.players]
        
        # Notificar todos que um espectador entrou
        emit('spectator_joined', {
            'username': username,
            'players': players_list,
            'spectator': True
        }, room=game_id)
        
        # Notificar o espectador
        emit('spectate_success', {
            'username': username,
            'game_started': game.started,
            'spectator': True
        })
    else:
        emit('error', {'message': message})

@socketio.on('reconnect_game')
def handle_reconnect_game(data):
    """Gerencia reconexão de jogadores"""
    game_id = data['game_id']
    
    # Obter username do token
    username = get_current_user()
    if not username:
        emit('error', {'message': 'Usuário não autenticado'})
        return

    if game_id not in games:
        emit('error', {'message': 'Jogo não encontrado'})
        return
    
    game = games[game_id]
    
    # Tentar reconectar
    result = game.reconnect_player(request.sid, username)
    
    if result['success']:
        # Adicionar à sala
        join_room(game_id)
        update_user_game(username, game_id)

        players_list = [
            {'username': p, 'name': game.player_data[p]['name']}
            for p in game.players if p in game.player_data
        ]

        emit('player_joined', {
            'username': username,
            'players': players_list,
            'reconnected': True
        }, room=game_id)
        if game.started:
            broadcast_system_message(game_id, f'{username} reconectou ao jogo')
        else:
            broadcast_system_message(game_id, f'{username} entrou na sala')
        
        emit('reconnect_success', {
            'username': username,
            'game_started': game.started,
            'finished': bool(getattr(game, 'finished', False)),
            'winner': getattr(game, 'winner', None),
            'winner_name': None,
        })
    else:
        # Se não estava na partida mas a sala está em lobby, tenta entrar
        if not game.started and username not in game.player_data:
            if game.add_player(request.sid, username):
                join_room(game_id)
                update_user_game(username, game_id)
                players_list = [
                    {'username': p, 'name': game.player_data[p]['name']}
                    for p in game.players if p in game.player_data
                ]
                broadcast_system_message(game_id, f'{username} entrou na sala')
                emit('player_joined', {
                    'username': username,
                    'players': players_list,
                }, room=game_id)
                emit('reconnect_success', {
                    'username': username,
                    'game_started': False,
                    'finished': False,
                })
                return
        emit('error', {'message': result['message']})

@socketio.on('ping_game')
def handle_ping_game(data):
    """Mantém a conexão ativa e verifica se jogador ainda está no jogo"""
    game_id = data['game_id']
    player_id = data['player_id']
    
    if game_id in games:
        game = games[game_id]
        if player_id in game.player_data:
            # Jogador ainda está no jogo
            emit('pong_game', {'status': 'ok'})
        else:
            emit('pong_game', {'status': 'player_not_found'})

@socketio.on('send_chat_message')
def handle_send_chat_message(data):
    """Envia mensagem de chat para a sala"""
    game_id = data.get('game_id')
    message = data.get('message', '').strip()
    
    if not game_id or not message:
        emit('chat_error', {'message': 'Mensagem vazia'})
        return
    
    if not games[game_id].chat_enabled:
        emit('chat_error', {'message': 'Chat desabilitado nesta sala'})
        return

    # Obter username
    username = get_current_user()
    if not username:
        # Tentar obter do socket mapping
        for gid, game in games.items():
            if gid == game_id:
                username = game.get_player_by_socket(request.sid)
                break
    
    if not username:
        emit('chat_error', {'message': 'Usuário não identificado'})
        return
    
    if game_id not in games:
        emit('chat_error', {'message': 'Sala não encontrada'})
        return
    
    # Limitar tamanho da mensagem
    if len(message) > 500:
        emit('chat_error', {'message': 'Mensagem muito longa (máx. 500 caracteres)'})
        return
    
    # Adicionar mensagem ao histórico
    censored_message = add_chat_message(game_id, username, message, is_system=False)
    
    # Emitir para toda a sala
    emit('chat_message', {
        'username': username,
        'message': censored_message,
        'timestamp': now_sp_str('%H:%M:%S'),
        'is_system': False
    }, room=game_id)

@socketio.on('get_chat_history')
def handle_get_chat_history(data):
    """Retorna o histórico de mensagens do chat"""
    game_id = data.get('game_id')
    
    if not game_id:
        emit('chat_history', {'messages': []})
        return
    
    messages = chat_messages.get(game_id, [])
    emit('chat_history', {'messages': messages})

@socketio.on('player_action')
def handle_player_action(data):
    game_id = data['game_id']
    action = data['action']
    params = data.get('params', {})
    
    # Verificar autenticação
    username = get_current_user()
    if not username:
        emit('error', {'message': 'Usuário não autenticado'})
        return
    
    if game_id not in games:
        emit('error', {'message': 'Jogo não encontrado'})
        return
    
    game = games[game_id]
    
    # Verificar se o socket corresponde ao username
    socket_username = game.get_player_by_socket(request.sid)
    if socket_username != username:
        emit('error', {'message': 'Sessão inválida'})
        return
    
    if not game.started:
        emit('error', {'message': 'O jogo ainda não começou'})
        return

    # Partida já acabou — não processar mais ações (evita spam de game_over)
    if getattr(game, 'finished', False):
        emit('action_error', {
            'message': 'A partida já terminou.',
            'player_name': username,
            'action': action,
            'timestamp': now_sp_str('%H:%M:%S'),
            'game_finished': True,
            'winner': getattr(game, 'winner', None),
        })
        return
    
    if username not in game.player_data:
        emit('error', {'message': 'Jogador não encontrado'})
        return
    
    if game.player_data[username].get('dead', False):
        emit('error', {'message': 'Você está morto e não pode mais realizar ações.'})
        return
    
    if game.players[game.current_turn] != username:
        emit('error', {'message': 'Não é o seu turno'})
        return

    result = None
    player_name = username
    timestamp = now_sp_str('%H:%M:%S')
    log_message = ""
    
    try:
        if action == 'draw':
            result = game.draw_card(player_name)
            if result and result.get('success'):
                log_message = f"📥 {player_name} comprou uma carta"

        elif action == 'play_card':
            result = game.play_card(player_name, params['card_id'], params['position_type'], params['position_index'])
            if result and result.get('success'):
                card_name = result.get('card', {}).get('name', 'uma carta')
                log_message = f"🎴 {player_name} jogou {card_name}"

        elif action == 'attack':
            result = game.attack(player_name, params['target_id'])
            if result and result.get('success'):
                target_name = result.get('target_name', 'um oponente')
                damage = result.get('damage_to_player', 0)
                total = result.get('total_attack', damage)
                life_left = result.get('target_life')
                if result.get('attack_cancelled'):
                    log_message = f"⚔️ {player_name} atacou {target_name}, mas o ataque foi cancelado!"
                elif result.get('damage_reflected'):
                    log_message = (
                        f"🪞 {player_name} atacou {target_name} e o dano foi refletido "
                        f"({result.get('reflected_damage', total)})!"
                    )
                else:
                    life_txt = f" → ❤️{life_left}" if life_left is not None else ""
                    log_message = (
                        f"⚔️ {player_name} atacou {target_name} "
                        f"(poder {total}, dano {damage}){life_txt}"
                    )
                # Sempre no chat da sala (todos veem sem Swal)
                broadcast_system_message(game_id, log_message)

        elif action == 'equip_item':
            result = game.equip_item_to_creature(player_name, params['item_card_id'], params['creature_card_id'])
            if result and result.get('success'):
                log_message = f"🔰 {player_name} equipou {result.get('item', 'um item')} em {result.get('creature', 'uma criatura')}"

        elif action == 'cast_spell':
            result = game.cast_spell(player_name, params['spell_id'], params.get('target_player_id'), params.get('target_card_id'))
            if result and result.get('success'):
                spell_name = result.get('spell', {}).get('name', 'um feitiço')
                log_message = f"✨ {player_name} usou {spell_name}"

        elif action == 'call_centaurs':
            result = game.call_centaurs(player_name)
            if result and result.get('success'):
                log_message = f"🐎 {player_name} usou CHAMAR CENTAUROS e coletou {result.get('centaurs_collected', 0)} centauro(s)"

        elif action == 'ritual':
            result = game.perform_ritual(player_name, params['ritual_id'], params.get('target_player_id'))
            if result and result.get('success'):
                log_message = f"📿 {player_name} realizou {result.get('message', 'um ritual')}"

        elif action == 'swap_positions':
            result = game.swap_positions(
                player_name, 
                params['pos1_type'], 
                params['pos1_index'], 
                params['pos2_type'], 
                params['pos2_index']
            )
            if result and result.get('success'):
                log_message = f"🔄 {player_name} trocou posições das cartas"

        elif action == 'move_card':
            result = game.move_card(player_name, params['from_type'], params['from_index'], params['to_type'], params['to_index'])
            if result and result.get('success'):
                log_message = f"↔️ {player_name} moveu uma carta"

        elif action == 'prophet_curse':
            result = game.prophet_curse(
                player_name, 
                params['target_player_id'], 
                params['target_card_id']
            )
            if result and result.get('success'):
                log_message = f"🔮 {player_name} amaldiçoou {result.get('target_card', 'uma carta')} de {result.get('target_player', 'um oponente')} (morre em 2 rodadas)"

        elif action == 'revive':
            # Verificar se params['card_id'] existe
            card_id = params.get('card_id') or params.get('target_card_id')
            if not card_id:
                emit('action_error', {
                    'message': 'ID da carta não fornecido',
                    'player_name': player_name,
                    'action': action,
                    'timestamp': timestamp
                })
                return
            
            result = game.revive_from_graveyard(player_name, card_id)
            if result and result.get('success'):
                card_name = result.get('card', {}).get('name', 'uma carta')
                log_message = f"🔄 {player_name} reviveu {card_name} do cemitério"

        elif action == 'flip_card':
            result = game.flip_card(player_name, params['position_type'], params['position_index'])
            if result and result.get('success'):
                log_message = f"🔄 {player_name} desvirou uma carta"

        elif action == 'oracle':
            result = game.perform_oracle(player_name, params['target_id'])
            if result and result.get('success'):
                log_message = f"👁️ {player_name} realizou um oráculo"

        elif action == 'toggle_time':
            result = game.toggle_time_of_day(player_name)
            if result and result.get('success'):
                log_message = f"🔥 {player_name} usou a habilidade da Fênix para mudar o ciclo para {result['new_time'].upper()}"

        elif action == 'end_turn':
            game.next_turn()
            next_player_name = game.players[game.current_turn]
            next_player_name = game.player_data[next_player_name]['name']
            result = {'success': True, 'next_turn': next_player_name}
        
        if result and result.get('success'):
            # Registrar ação para primeira rodada (exceto end_turn)
            first_round_ended = False
            if action != 'end_turn':
                first_round_ended = game.register_action(player_name, action)
            
            if first_round_ended:
                result['first_round_ended'] = True
                # Notificar todos que a primeira rodada terminou
                emit('first_round_ended', {
                    'message': '🎉 PRIMEIRA RODADA CONCLUÍDA! Todos já jogaram, ataques liberados!'
                }, room=game_id)
            
            # Emitir ação com todas as informações para o log
            emit('action_success', {
                'player_id': player_name,
                'player_name': player_name,
                'action': action,
                'result': result,
                'log_message': log_message,
                'timestamp': timestamp
            }, room=game_id)
            
            # Só emite game_over UMA vez por partida
            already_emitted = getattr(game, '_game_over_emitted', False)
            winner = game.check_winner()
            if winner and not already_emitted and getattr(game, 'finished', False):
                game._game_over_emitted = True
                winner_name = game.player_data[winner]['name']
                # Mantém a sala: modal de vitória + reset para lobby (mesmo id/mods)
                _emit_game_over_and_rematch(game_id, game, winner, winner_name)
            elif action == 'end_turn':
                # se o próximo for bot (tutorial / IA), agenda o turno
                from twilight.game.ai import schedule_bot_turn
                schedule_bot_turn(game_id, delay=0.8)
        else:
            error_msg = result['message'] if result else 'Ação inválida'
            emit('action_error', {
                'message': error_msg,
                'player_name': player_name,
                'action': action,
                'timestamp': timestamp
            })
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        emit('action_error', {
            'message': f'Erro interno: {str(e)}',
            'player_name': player_name,
            'action': action,
            'timestamp': timestamp
        })



