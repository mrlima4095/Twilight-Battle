"""Ciclo de vida da sala: encerrar partidas e limpar salas fantasma."""
from __future__ import annotations

import threading
import time
from typing import Optional

from twilight.auth.service import clear_game_from_all_accounts
from twilight.extensions import socketio
from twilight.state import chat_messages, games

# salas com close já agendado (evita timer duplicado)
_pending_close: set[str] = set()
_lock = threading.Lock()

# segundos após o fim antes de apagar a sala da memória
FINISHED_CLOSE_DELAY = 12
# cleanup: remove finished com mais de N segundos
FINISHED_MAX_AGE = 15


def mark_finished_timestamp(game) -> None:
    if game is None:
        return
    if not getattr(game, 'finished_at', None):
        game.finished_at = time.time()
    game.finished = True


def close_game(game_id: str, message: Optional[str] = None, notify: bool = True) -> bool:
    """
    Remove a sala da memória e limpa current_game de todos.
    Idempotente.
    """
    with _lock:
        _pending_close.discard(game_id)
        game = games.get(game_id)
        if not game:
            # ainda limpa contas residual
            try:
                clear_game_from_all_accounts(game_id)
            except Exception:
                pass
            chat_messages.pop(game_id, None)
            return False

        try:
            clear_game_from_all_accounts(game_id)
        except Exception:
            pass

        if notify:
            msg = message or f'A sala {game_id} foi encerrada.'
            try:
                socketio.emit(
                    'room_closed',
                    {'message': msg, 'game_id': game_id, 'reason': 'finished'},
                    room=game_id,
                )
            except Exception:
                pass

        try:
            del games[game_id]
        except KeyError:
            pass
        chat_messages.pop(game_id, None)
        return True


def _delayed_close(game_id: str, delay: float, message: Optional[str]) -> None:
    time.sleep(max(0.5, delay))
    with _lock:
        still = game_id in _pending_close
    if not still and game_id not in games:
        return
    # só fecha se ainda finished (ou sumiu do pending e já foi fechada)
    game = games.get(game_id)
    if game is None:
        with _lock:
            _pending_close.discard(game_id)
        return
    if not getattr(game, 'finished', False):
        with _lock:
            _pending_close.discard(game_id)
        return
    close_game(game_id, message=message, notify=True)


def schedule_close_finished_game(
    game_id: str,
    delay: float = FINISHED_CLOSE_DELAY,
    message: Optional[str] = None,
) -> None:
    """Agenda remoção da sala após o fim (jogadores veem o modal de vitória)."""
    game = games.get(game_id)
    if game:
        mark_finished_timestamp(game)

    with _lock:
        if game_id in _pending_close:
            return
        _pending_close.add(game_id)

    msg = message or (
        f'Partida encerrada. A sala {game_id} foi fechada automaticamente.'
    )
    t = threading.Thread(
        target=_delayed_close,
        args=(game_id, delay, msg),
        daemon=True,
        name=f'close-game-{game_id}',
    )
    t.start()


def cleanup_stale_games() -> dict:
    """
    Remove:
    - partidas finished há mais de FINISHED_MAX_AGE
    - salas sem jogadores (se started e vazia, ou finished)
    """
    now = time.time()
    removed = []
    for game_id, game in list(games.items()):
        finished = getattr(game, 'finished', False)
        finished_at = getattr(game, 'finished_at', None) or 0
        no_players = len(getattr(game, 'players', []) or []) == 0

        should_close = False
        reason = ''
        if finished and (not finished_at or (now - finished_at) >= FINISHED_MAX_AGE):
            should_close = True
            reason = 'finished'
        elif no_players and getattr(game, 'started', False):
            should_close = True
            reason = 'empty'

        if should_close:
            if close_game(
                game_id,
                message=f'Sala {game_id} removida ({reason}).',
                notify=True,
            ):
                removed.append({'id': game_id, 'reason': reason})

    return {'removed': removed, 'count': len(removed), 'active': len(games)}
