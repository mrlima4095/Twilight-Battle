"""Extensões Flask compartilhadas (inicializadas em create_app)."""
from flask_socketio import SocketIO

socketio = SocketIO(logging=False, cors_allowed_origins="*", async_mode='gevent')
