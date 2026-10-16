"""Extensões Flask compartilhadas (inicializadas em create_app)."""
from flask_socketio import SocketIO

from twilight.config import CORS_ALLOWED_ORIGINS

# Sem CORS_ALLOWED_ORIGINS → mesma origem (None). Nunca "*" com cookie auth.
socketio = SocketIO(
    logging=False,
    cors_allowed_origins=CORS_ALLOWED_ORIGINS or None,
    async_mode='gevent',
)
