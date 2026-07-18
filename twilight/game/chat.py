"""Chat da partida e filtro de palavrões."""
import re
from datetime import datetime

from twilight.extensions import socketio
from twilight.state import chat_messages, games

MAX_CHAT_MESSAGES = 200

PROFANITY_LIST = [
    'porra', 'caralho', 'krl', 'krlh', 'puta', 'merda', 'foda',
    'bosta', 'cacete', 'desgraça', 'pqp', 'fdp', 'vsf', 'vtnc',
    'arrombado', 'cu', 'buceta', 'viado', 'corno'
]


def censor_text(text):
    censored = text
    for word in PROFANITY_LIST:
        if word in censored.lower():
            pattern = re.compile(re.escape(word), re.IGNORECASE)
            censored = pattern.sub('***', censored)
    return censored


def add_chat_message(game_id, username, message, is_system=False):
    if game_id not in chat_messages:
        chat_messages[game_id] = []

    final_message = message
    if not is_system:
        final_message = censor_text(message)

    chat_messages[game_id].append({
        'username': username,
        'message': final_message,
        'timestamp': datetime.now().strftime('%H:%M:%S'),
        'is_system': is_system
    })

    if len(chat_messages[game_id]) > MAX_CHAT_MESSAGES:
        chat_messages[game_id] = chat_messages[game_id][-MAX_CHAT_MESSAGES:]

    return final_message


def broadcast_system_message(game_id, message):
    if game_id not in games:
        return

    add_chat_message(game_id, 'Sistema', message, is_system=True)

    socketio.emit('chat_message', {
        'username': 'Sistema',
        'message': message,
        'timestamp': datetime.now().strftime('%H:%M:%S'),
        'is_system': True
    }, room=game_id)
