"""Ciclo de vida da sala: encerrar partidas e limpar salas fantasma."""
from __future__ import annotations

import threading
import time
from typing import Optional

from twilight.auth.service import clear_game_from_all_accounts
from twilight.config import (
    ABANDONED_LOBBY_TTL_SECONDS,
    CLEANUP_INTERVAL_SECONDS,
    FINISHED_ROOM_TTL_SECONDS,
    TURN_TIMEOUT_SECONDS,
)
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


def _count_human_sockets(game) -> int:
    """Sockets conectados que não são bots."""
    players = set(getattr(game, 'players', []) or [])
    count = 0
    for sid, uname in (getattr(game, 'socket_to_username', {}) or {}).items():
        if uname in players and not str(sid).startswith('bot:'):
            count += 1
    return count


def enforce_turn_timeout() -> list:
    """
    Encerra automaticamente turnos travados (jogador humano que não age),
    para que partidas abandonadas não fiquem presas para sempre.
    """
    if TURN_TIMEOUT_SECONDS <= 0:
        return []
    now = time.time()
    acted = []
    for game_id, game in list(games.items()):
        if not getattr(game, 'started', False) or getattr(game, 'finished', False):
            continue
        if not getattr(game, 'players', None):
            continue
        last = getattr(game, 'last_action_at', None) or getattr(game, 'created_at', now)
        if now - last < TURN_TIMEOUT_SECONDS:
            continue
        try:
            current = game.players[game.current_turn]
        except (IndexError, KeyError):
            continue
        # não mexe em turno de bot
        if (game.player_data.get(current) or {}).get('is_bot'):
            continue
        try:
            game.next_turn()
            game.last_action_at = time.time()
        except Exception:
            continue
        acted.append({'game_id': game_id, 'player': current})
        # Notificação é best-effort: nunca deve impedir a troca de turno.
        try:
            socketio.emit('turn_timeout', {
                'message': f'⏱️ {current} não agiu a tempo — turno passou automaticamente.',
            }, room=game_id)
        except Exception:
            pass
    return acted


def cleanup_stale_games() -> dict:
    """
    Remove salas que ficariam eternas na memória:
    - partidas finished há mais de FINISHED_MAX_AGE;
    - salas iniciadas sem jogadores;
    - lobbies nunca iniciados sem ninguém conectado (TTL);
    - partidas em andamento sem nenhum humano conectado (TTL).
    """
    now = time.time()
    removed = []
    for game_id, game in list(games.items()):
        finished = getattr(game, 'finished', False)
        finished_at = getattr(game, 'finished_at', None) or 0
        players = list(getattr(game, 'players', []) or [])
        no_players = len(players) == 0
        started = getattr(game, 'started', False)

        # marca/limpa o "vazio desde" com base em sockets humanos conectados
        humans = _count_human_sockets(game)
        empty_since = getattr(game, 'empty_since', None)
        if humans == 0:
            if empty_since is None:
                game.empty_since = now
                empty_since = now
        else:
            game.empty_since = None
            empty_since = None

        should_close = False
        reason = ''
        if finished and (not finished_at or (now - finished_at) >= FINISHED_MAX_AGE):
            should_close = True
            reason = 'finished'
        elif no_players and started:
            should_close = True
            reason = 'empty'
        elif empty_since is not None and not started:
            # lobby abandonado (ninguém conectado há muito tempo)
            if (now - empty_since) >= ABANDONED_LOBBY_TTL_SECONDS:
                should_close = True
                reason = 'abandoned_lobby'
        elif empty_since is not None and started:
            # partida em andamento mas todos os humanos saíram
            if (now - empty_since) >= FINISHED_ROOM_TTL_SECONDS:
                should_close = True
                reason = 'abandoned_game'

        if should_close:
            if close_game(
                game_id,
                message=f'Sala {game_id} removida ({reason}).',
                notify=True,
            ):
                removed.append({'id': game_id, 'reason': reason})

    return {'removed': removed, 'count': len(removed), 'active': len(games)}


_reaper_started = False


def start_reaper() -> None:
    """
    Inicia (uma vez) a tarefa de fundo que limpa salas abandonadas e
    encerra turnos travados. Substitui a dependência do polling dos clientes
    em /api/cleanup-games.
    """
    global _reaper_started
    with _lock:
        if _reaper_started:
            return
        _reaper_started = True

    def _loop():
        while True:
            try:
                cleanup_stale_games()
            except Exception as exc:  # nunca deixa a thread morrer
                print(f'[reaper] cleanup falhou: {exc}')
            try:
                enforce_turn_timeout()
            except Exception as exc:
                print(f'[reaper] turn timeout falhou: {exc}')
            socketio.sleep(max(5, CLEANUP_INTERVAL_SECONDS))

    socketio.start_background_task(_loop)
