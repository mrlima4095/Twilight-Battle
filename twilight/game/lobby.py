"""Helpers do lobby (lista de jogadores, bots e sincronização WebSocket)."""
from __future__ import annotations

from twilight.extensions import socketio

BOT_DIFFICULTIES = ('easy', 'normal', 'hard')
BOT_DIFFICULTY_LABELS = {
    'easy': 'Fácil',
    'normal': 'Normal',
    'hard': 'Difícil',
}
_ALIASES = {
    'facil': 'easy',
    'fácil': 'easy',
    'dificil': 'hard',
    'difícil': 'hard',
}


def normalize_bot_difficulty(value) -> str:
    """Normaliza a dificuldade escolhida; fallback seguro = normal."""
    key = str(value or '').strip().lower()
    key = _ALIASES.get(key, key)
    return key if key in BOT_DIFFICULTIES else 'normal'


def is_bot(game, username: str) -> bool:
    return bool((game.player_data.get(username) or {}).get('is_bot'))


def bot_difficulty_for(game, username: str) -> str:
    data = game.player_data.get(username) or {}
    return normalize_bot_difficulty(data.get('bot_difficulty'))


def lobby_players(game) -> list[dict]:
    """Lista de jogadores do lobby, com metadados dos bots."""
    return [
        {
            'username': p,
            'name': (game.player_data.get(p) or {}).get('name') or p,
            'is_bot': is_bot(game, p),
            'bot_difficulty': bot_difficulty_for(game, p) if is_bot(game, p) else None,
        }
        for p in game.players
        if p in game.player_data
    ]


def lobby_payload(game, message: str | None = None) -> dict:
    payload = {
        'game_id': game.game_id,
        'players': lobby_players(game),
        'players_count': len(game.players),
        'max_players': int(getattr(game, 'max_players', 6) or 6),
        'bots_count': sum(1 for p in game.players if is_bot(game, p)),
        'bot_difficulty': normalize_bot_difficulty(getattr(game, 'bot_difficulty', 'normal')),
        'creator': game.creator,
        'started': bool(game.started),
        'finished': bool(getattr(game, 'finished', False)),
        'tutorial': bool(getattr(game, 'tutorial', False)),
    }
    if message:
        payload['message'] = message
    return payload


def emit_lobby_update(game, message: str | None = None) -> dict:
    """Broadcaster único de mudanças no lobby (entrada, bots, rematch)."""
    payload = lobby_payload(game, message)
    socketio.emit('lobby_updated', payload, room=game.game_id)
    return payload
