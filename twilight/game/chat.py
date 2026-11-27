"""Chat da partida e filtro de palavrões."""
import re
from collections import deque

from twilight.config import now_sp_str
from twilight.extensions import socketio
from twilight.state import chat_messages, games

MAX_CHAT_MESSAGES = 200

PROFANITY_LIST = [
    'porra', 'caralho', 'krl', 'krlh', 'puta', 'merda', 'foda',
    'bosta', 'cacete', 'desgraça', 'pqp', 'fdp', 'vsf', 'vtnc',
    'arrombado', 'cu', 'buceta', 'viado', 'corno'
]


# Compiladas uma única vez no import (antes: 19 re.compile por mensagem).
PROFANITY_RE = re.compile(
    '|'.join(re.escape(word) for word in sorted(PROFANITY_LIST, key=len, reverse=True)),
    re.IGNORECASE,
)


def censor_text(text):
    return PROFANITY_RE.sub('***', text)


def add_chat_message(game_id, username, message, is_system=False):
    if game_id not in chat_messages:
        # deque com teto: sem copiar a lista a cada mensagem.
        chat_messages[game_id] = deque(maxlen=MAX_CHAT_MESSAGES)

    final_message = message
    if not is_system:
        final_message = censor_text(message)

    chat_messages[game_id].append({
        'username': username,
        'message': final_message,
        'timestamp': now_sp_str('%H:%M:%S'),
        'is_system': is_system
    })

    return final_message


def broadcast_system_message(game_id, message, fog_message=None):
    """
    Envia mensagem de sistema para a sala.
    Com Névoa de Guerra (fog_of_war), se fog_message for passado, usa ela
    no chat público (evita vazar nomes/stats de cartas).
    """
    if game_id not in games:
        return

    game = games[game_id]
    public = message
    if fog_message is not None and 'fog_of_war' in (getattr(game, 'modifiers', None) or []):
        public = fog_message

    add_chat_message(game_id, 'Sistema', public, is_system=True)

    socketio.emit('chat_message', {
        'username': 'Sistema',
        'message': public,
        'timestamp': now_sp_str('%H:%M:%S'),
        'is_system': True
    }, room=game_id)
