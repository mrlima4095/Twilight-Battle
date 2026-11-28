"""Snapshots de partidas: sobrevivem a restart/redeploy do servidor.

O estado continua vivendo em ``twilight.state.games``; aqui ele apenas é
materializado no banco (Postgres em produção, SQLite no dev) e reconstruído
no boot. Sids de Socket.IO são voláteis e nunca são persistidos: a reconexão
é feita pelo usuário autenticado via evento ``reconnect_game``/``join_game``.
"""
from __future__ import annotations

import json
import logging
import time
from collections import deque
from copy import deepcopy

from twilight.extensions import socketio
from twilight.game.chat import MAX_CHAT_MESSAGES
from twilight.game.engine import Game
from twilight.state import chat_messages, games
from twilight.storage.db import (
    delete_game_snapshot,
    load_game_snapshots,
    save_game_snapshot,
)

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

# Campos que não fazem sentido (ou não são seguros) depois de um restart.
_VOLATILE_FIELDS = frozenset({
    'socket_to_username',
    'attacker_hand_for_oracle',
    '_last_day_effects_signature',
})


def _json_payload(game, chat):
    state = {}
    for key, value in vars(game).items():
        if key in _VOLATILE_FIELDS:
            continue
        if key == 'players_acted':
            value = sorted(value or [])
        elif key == 'player_data':
            # Sids reais não podem vazar para o banco nem voltar no restore.
            value = deepcopy(value or {})
            for username, player in value.items():
                if player.get('is_bot') or username == 'mentor':
                    player['socket_id'] = f'bot:{username}:{game.game_id}'
                else:
                    player['socket_id'] = None
        state[key] = value
    return {
        'schema_version': SCHEMA_VERSION,
        'game_id': game.game_id,
        'updated_at': time.time(),
        'state': state,
        'chat': list(chat),
    }


def snapshot_game(game_id: str) -> bool:
    """Grava o estado atual de uma sala. Retorna False se ela não existe."""
    game = games.get(game_id)
    if game is None:
        return False
    try:
        payload = _json_payload(game, chat_messages.get(game_id, ()))
        save_game_snapshot(
            game_id=game_id,
            schema_version=SCHEMA_VERSION,
            version=1,
            updated_at=payload['updated_at'],
            state_json=json.dumps(payload, ensure_ascii=False, separators=(',', ':')),
            chat_json=json.dumps(payload['chat'], ensure_ascii=False),
        )
        return True
    except Exception:
        # Nunca derruba uma ação do jogo por falha de persistência.
        logger.exception('Falha ao salvar snapshot da sala %s', game_id)
        return False


def snapshot_all_games() -> int:
    saved = 0
    for game_id in list(games):
        if snapshot_game(game_id):
            saved += 1
    return saved


def remove_game_snapshot(game_id: str) -> bool:
    try:
        return delete_game_snapshot(game_id)
    except Exception:
        logger.exception('Falha ao apagar snapshot da sala %s', game_id)
        return False


def _restore_one(row: dict) -> bool:
    state = row.get('state') or {}
    game_id = str(row.get('game_id') or state.get('game_id') or '')
    if not game_id or row.get('schema_version') != SCHEMA_VERSION:
        logger.warning('Snapshot incompatível ignorado: %s', game_id)
        return False

    try:
        game = Game(game_id, state.get('creator') or '', state.get('config') or {})
        for key, value in state.items():
            if key in _VOLATILE_FIELDS:
                continue
            setattr(game, key, value)

        game.players_acted = set(state.get('players_acted') or [])
        game.socket_to_username = {}
        game._last_day_effects_signature = None
        game.game_id = game_id

        # Sids humanos morreram com o processo; bots têm sid determinístico.
        for username, player in (game.player_data or {}).items():
            if player.get('is_bot') or username == 'mentor':
                sid = f'bot:{username}:{game_id}'
                player['socket_id'] = sid
                game.socket_to_username[sid] = username
            else:
                player['socket_id'] = None

        # Partidas terminadas voltam ao lobby, como já acontece no game_over.
        if getattr(game, 'finished', False):
            game.reset_to_lobby(last_winner=getattr(game, 'winner', None))

        # Janela de graça: o reaper não pode apagar a sala logo no boot.
        if game.started and not game.socket_to_username:
            game.empty_since = time.time()

        chat_messages[game_id] = deque(row.get('chat') or [], maxlen=MAX_CHAT_MESSAGES)
        games[game_id] = game
        return True
    except Exception:
        logger.exception('Falha ao restaurar a sala %s', game_id)
        return False


def restore_games(*, schedule_bots: bool = True) -> dict:
    """Reconstrói salas a partir do banco. Seguro para chamar no boot."""
    result = {'restored': 0, 'skipped': 0}
    try:
        rows = load_game_snapshots()
    except Exception:
        logger.exception('Falha ao ler snapshots de partidas')
        return result

    for row in rows:
        game_id = row.get('game_id')
        if game_id in games:
            result['skipped'] += 1
            continue
        if _restore_one(row):
            result['restored'] += 1
        else:
            result['skipped'] += 1

    if schedule_bots and result['restored']:
        _reschedule_bots()
    if result['restored']:
        logger.info('Partidas restauradas: %s', result['restored'])
    return result


def _reschedule_bots() -> None:
    try:
        from twilight.game.ai import schedule_bot_turn
        for game_id, game in list(games.items()):
            if not game.started or game.finished or not game.players:
                continue
            username = game.players[game.current_turn]
            player = game.player_data.get(username) or {}
            if player.get('is_bot') or username == 'mentor':
                schedule_bot_turn(game_id, delay=1.0)
    except Exception:
        logger.exception('Falha ao reagendar turnos de bots restaurados')


def start_snapshot_loop(interval_seconds: float = 5) -> None:
    """Background task: garante que mudanças recentes não se percam no redeploy."""
    def _loop():
        while True:
            socketio.sleep(max(1.0, interval_seconds))
            try:
                snapshot_all_games()
            except Exception:
                logger.exception('Falha no salvamento periódico de partidas')

    socketio.start_background_task(_loop)
