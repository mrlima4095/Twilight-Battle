"""Listagem, criação e start de partidas."""
import random
import string
import uuid

from flask import Blueprint, jsonify, request

from twilight.auth.service import get_current_user, update_user_game
from twilight.cards.definitions import MODIFIERS
from twilight.extensions import socketio
from twilight.game.ai import TUTORIAL_BOT_NAME, TUTORIAL_TIPS, add_tutorial_bot, schedule_bot_turn
from twilight.game.chat import broadcast_system_message
from twilight.game.engine import Game
from twilight.state import games

bp = Blueprint('games', __name__)


@bp.route('/api/games')
def get_games():
    games_list = []
    for game_id, game in games.items():
        if game.private:
            continue
        # Não listar só se finished sem ter resetado (estado inválido)
        if getattr(game, 'finished', False) and game.started:
            continue
            
        games_list.append({
            'id': game_id,
            'players': len(game.players),
            'max_players': game.max_players,
            'started': game.started,
            'allow_spectators': game.allow_spectators,
            'modifiers': game.modifiers
        })
    return jsonify(games_list)



@bp.route('/api/modifiers')
def get_modifiers():
    return jsonify({'modifiers': MODIFIERS})


@bp.route('/api/create-game', methods=['POST'])
def create_game():
    username = get_current_user()
    if not username:
        return jsonify({'success': False, 'message': 'Usuário não autenticado'}), 401
    
    data = request.json or {}
    config = {
        'max_players': min(int(data.get('max_players', 6)), 12),
        'private': data.get('private', False),
        'allow_spectators': data.get('allow_spectators', True),
        'chat_enabled': data.get('chat_enabled', True),
        'modifiers': data.get('modifiers', []) 
    }
    
    game_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    games[game_id] = Game(game_id, username, config)
    
    return jsonify({'game_id': game_id, 'config': config})


@bp.route('/api/tutorial/start', methods=['POST'])
def start_tutorial():
    """
    Cria partida privada 1v1 de treino com o Mentor (IA fácil).
    O jogador entra na sala; o bot já está presente e a partida inicia ao entrar.
    """
    username = get_current_user()
    if not username:
        return jsonify({'success': False, 'message': 'Usuário não autenticado'}), 401

    # evita colisão com o nome reservado do bot
    if username.lower() == TUTORIAL_BOT_NAME:
        return jsonify({
            'success': False,
            'message': f'Use outra conta (nome "{TUTORIAL_BOT_NAME}" é reservado ao tutorial).',
        }), 400

    config = {
        'max_players': 2,
        'private': True,
        'allow_spectators': False,
        'chat_enabled': True,
        # ciclo mais curto para treinar dia/noite sem partidas eternas
        'modifiers': ['fast_cycle'],
        'tutorial': True,
    }
    game_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    game = Game(game_id, username, config)
    game.tutorial = True
    add_tutorial_bot(game, TUTORIAL_BOT_NAME)
    games[game_id] = game

    return jsonify({
        'success': True,
        'game_id': game_id,
        'tutorial': True,
        'bot': TUTORIAL_BOT_NAME,
        'tips': TUTORIAL_TIPS,
        'message': 'Tutorial criado. Entre na sala e pratique contra o Mentor.',
    })


@bp.route('/api/tutorial/tips')
def tutorial_tips():
    return jsonify({'tips': TUTORIAL_TIPS})



@bp.route('/start-game/<game_id>', methods=['POST'])
def start_game(game_id):
    username = get_current_user()
    
    if not username:
        return jsonify({'success': False, 'message': 'Usuário não autenticado'}), 401
    
    if game_id not in games:
        return jsonify({'success': False, 'message': 'Jogo não encontrado'}), 404
    
    game = games[game_id]
    
    # Verificar se o usuário é o criador
    if game.creator != username:
        return jsonify({'success': False, 'message': 'Apenas o criador da sala pode iniciar o jogo'}), 401

    # Se ainda estiver "finished" por algum motivo, reabre lobby
    if getattr(game, 'finished', False):
        game.reset_to_lobby(last_winner=getattr(game, 'winner', None))

    if game.started:
        return jsonify({'success': False, 'message': 'O jogo já está em andamento'}), 400
    
    if len(game.players) >= 2:  # Mínimo 2 jogadores
        game.started = True
        game.finished = False
        game.finished_at = None
        game.winner = None
        game._game_over_emitted = False
        if getattr(game, 'tutorial', False):
            broadcast_system_message(
                game_id,
                '🎓 Tutorial: você treina contra o Mentor (fácil). Siga as dicas no painel!',
            )
        else:
            broadcast_system_message(game_id, f'🎮 O jogo começou! Que comece a batalha! ⚔️')
        socketio.emit('game_started', {
            'game_id': game_id,
            'tutorial': bool(getattr(game, 'tutorial', False)),
        }, room=game_id)
        # se o primeiro turno for do bot, joga
        schedule_bot_turn(game_id, delay=1.0)
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'message': 'Mínimo de 2 jogadores para começar'}), 400



@bp.route('/api/check-start-permission/<game_id>')
def check_start_permission(game_id):
    username = get_current_user()
    
    if not username:
        return jsonify({'can_start': False, 'message': 'Usuário não autenticado'}), 401
    
    if game_id not in games:
        return jsonify({'can_start': False, 'message': 'Jogo não encontrado'}), 404
    
    game = games[game_id]
    can_start = (game.creator == username and len(game.players) >= 2)
    
    if not can_start:
        return jsonify({
            'can_start': False,
            'is_creator': game.creator == username,
            'players_count': len(game.players),
            'message': 'Apenas o criador da sala pode iniciar o jogo (mínimo 2 jogadores)'
        }), 401
    
    return jsonify({
        'can_start': True,
        'is_creator': True,
        'players_count': len(game.players),
        'message': 'Você pode iniciar o jogo'
    })



@bp.route('/api/cleanup-games', methods=['POST'])
def cleanup_games():
    """Remove salas finished/vazias que ficariam eternas na memória."""
    from twilight.game.session import cleanup_stale_games
    result = cleanup_stale_games()
    return jsonify({'success': True, **result})
