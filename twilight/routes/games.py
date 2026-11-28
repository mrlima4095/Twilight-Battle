"""Listagem, criação e start de partidas."""
import random
import string
import time

from flask import Blueprint, jsonify, request

from twilight.auth.service import get_current_user, login_required
from twilight.cards.definitions import MODIFIERS
from twilight.extensions import socketio
from twilight.game.ai import (
    TUTORIAL_BOT_NAME,
    TUTORIAL_TIPS,
    add_tutorial_bot,
    fill_bots,
    remove_all_bots,
    schedule_bot_turn,
)
from twilight.game.chat import broadcast_system_message
from twilight.game.engine import Game
from twilight.game.lobby import (
    BOT_DIFFICULTY_LABELS,
    emit_lobby_update,
    lobby_payload,
    normalize_bot_difficulty,
)
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
        'max_players': max(2, min(int(data.get('max_players', 6)), 12)),
        'private': data.get('private', False),
        'allow_spectators': data.get('allow_spectators', True),
        'chat_enabled': data.get('chat_enabled', True),
        'bot_difficulty': normalize_bot_difficulty(data.get('bot_difficulty')),
        'modifiers': data.get('modifiers', [])
    }
    
    game_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    games[game_id] = Game(game_id, username, config)
    try:
        from twilight.game.persistence import snapshot_game
        snapshot_game(game_id)
    except Exception:
        pass

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
    try:
        from twilight.game.persistence import snapshot_game
        snapshot_game(game_id)
    except Exception:
        pass

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
        game.last_action_at = time.time()
        if getattr(game, 'tutorial', False):
            broadcast_system_message(
                game_id,
                '🎓 Tutorial: você treina contra o Mentor (fácil). Siga as dicas no painel!',
            )
        else:
            broadcast_system_message(game_id, '🎮 O jogo começou! Que comece a batalha! ⚔️')
        socketio.emit('game_started', {
            'game_id': game_id,
            'tutorial': bool(getattr(game, 'tutorial', False)),
        }, room=game_id)
        # se o primeiro turno for do bot, joga
        schedule_bot_turn(game_id, delay=1.0)
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'message': 'Mínimo de 2 jogadores para começar'}), 400



def _host_game(game_id):
    """Retorna (game, None) ou (None, resposta de erro) para ações do dono."""
    username = get_current_user()
    if not username:
        return None, (jsonify({'success': False, 'message': 'Usuário não autenticado'}), 401)
    game = games.get(game_id)
    if not game:
        return None, (jsonify({'success': False, 'message': 'Jogo não encontrado'}), 404)
    if game.creator != username:
        return None, (
            jsonify({'success': False, 'message': 'Apenas o criador da sala pode configurar os bots'}),
            401,
        )
    return game, None


@bp.route('/api/games/<game_id>/bots', methods=['POST'])
def manage_bots(game_id):
    """Dono da sala: preencher vagas com bots, remover bots ou mudar dificuldade."""
    game, error = _host_game(game_id)
    if error:
        return error

    if getattr(game, 'started', False) or getattr(game, 'finished', False):
        return jsonify({
            'success': False,
            'message': 'Só é possível configurar bots antes do início da partida',
        }), 400

    data = request.json or {}
    action = str(data.get('action') or 'fill').strip().lower()
    difficulty = normalize_bot_difficulty(data.get('difficulty') or game.bot_difficulty)
    added: list = []
    removed: list = []

    if action == 'fill':
        raw_count = data.get('count')
        count = None
        if raw_count not in (None, ''):
            try:
                count = int(raw_count)
            except (TypeError, ValueError):
                return jsonify({'success': False, 'message': 'Quantidade inválida'}), 400
            if count < 1:
                return jsonify({'success': False, 'message': 'Escolha ao menos 1 bot'}), 400
        # Nunca ocupar a última vaga: o dono precisa conseguir entrar na sala.
        added = fill_bots(
            game, count=count, difficulty=difficulty, reserve_creator_slot=True
        )
        if not added:
            return jsonify({
                'success': False,
                'message': 'Não há vagas livres nesta sala',
                **lobby_payload(game),
            }), 400
        label = BOT_DIFFICULTY_LABELS[difficulty]
        message = (
            f'🤖 {len(added)} bot(s) ({label}) entrou(ram) na sala. '
            f'{len(game.players)}/{game.max_players} jogadores.'
        )

    elif action == 'remove':
        removed = remove_all_bots(game)
        if not removed:
            return jsonify({
                'success': False,
                'message': 'Não há bots na sala',
                **lobby_payload(game),
            }), 400
        message = f'🤖 {len(removed)} bot(s) removido(s) da sala.'

    elif action == 'difficulty':
        game.bot_difficulty = difficulty
        changed = 0
        for player in game.players:
            if (game.player_data.get(player) or {}).get('is_bot'):
                game.player_data[player]['bot_difficulty'] = difficulty
                changed += 1
        label = BOT_DIFFICULTY_LABELS[difficulty]
        message = (
            f'🎚️ Dificuldade dos bots alterada para {label}'
            + (f' ({changed} bot(s) atualizado(s)).' if changed else '.')
        )

    else:
        return jsonify({'success': False, 'message': 'Ação desconhecida'}), 400

    broadcast_system_message(game_id, message)
    payload = emit_lobby_update(game, message)
    return jsonify({
        'success': True,
        'message': message,
        'added': added,
        'removed': removed,
        **payload,
    })


@bp.route('/api/check-start-permission/<game_id>')
def check_start_permission(game_id):
    username = get_current_user()
    
    if not username:
        return jsonify({'can_start': False, 'message': 'Usuário não autenticado'}), 401
    
    if game_id not in games:
        return jsonify({'can_start': False, 'message': 'Jogo não encontrado'}), 404
    
    game = games[game_id]
    can_start = (game.creator == username and len(game.players) >= 2)
    payload = {
        **lobby_payload(game),
        'is_creator': game.creator == username,
        'can_start': can_start,
    }

    if not can_start:
        payload['message'] = (
            'Apenas o criador da sala pode iniciar o jogo (mínimo 2 jogadores)'
        )
        return jsonify(payload), 401

    payload['message'] = 'Você pode iniciar o jogo'
    return jsonify(payload)



@bp.route('/api/cleanup-games', methods=['POST'])
@login_required
def cleanup_games(username):
    """Remove salas finished/vazias. Exige login (não é mais público)."""
    from twilight.game.session import cleanup_stale_games
    result = cleanup_stale_games()
    return jsonify({'success': True, **result})
