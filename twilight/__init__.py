"""Twilight Battle — factory da aplicação Flask + SocketIO."""
import os

from twilight.config import (
    CORS_ALLOWED_ORIGINS,
    JWT_EXPIRATION_HOURS,
    JWT_SECRET,
    SECRET_KEY,
    TIMEZONE_NAME,
    ensure_data_dirs,
)
from twilight.extensions import socketio

# Raiz do projeto (onde ficam templates/, data/, etc.)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_UNSAFE_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}


def _install_csrf_origin_guard(app):
    """
    Mitigação de CSRF sem reescrever o frontend: para métodos que mudam estado,
    se a requisição trouxer Origin, ela precisa bater com o host do servidor
    (ou estar em CORS_ALLOWED_ORIGINS). Requisições sem Origin (webhooks,
    curl, same-origin antigos) seguem normalmente.
    """
    from urllib.parse import urlparse

    allowed = {origin.rstrip('/') for origin in CORS_ALLOWED_ORIGINS}

    @app.before_request
    def _check_origin():
        from flask import jsonify, request

        if request.method not in _UNSAFE_METHODS:
            return None
        origin = request.headers.get('Origin')
        if not origin:
            return None
        origin = origin.rstrip('/')
        if origin in allowed:
            return None
        parsed = urlparse(origin)
        if parsed.netloc and parsed.netloc == request.host:
            return None
        return jsonify({'success': False, 'message': 'Origem não permitida'}), 403


def create_app():
    """Cria e configura a app Flask com rotas e sockets."""
    from flask import Flask

    from twilight.routes import register_blueprints
    from twilight.sockets import register_socket_handlers

    # Fuso São Paulo (GMT-3) — reforça no processo (Docker já seta TZ)
    os.environ.setdefault('TZ', TIMEZONE_NAME)
    try:
        import time as _time
        if hasattr(_time, 'tzset'):
            _time.tzset()
    except Exception:
        pass

    ensure_data_dirs()

    # SQLite: accounts + journal (migra JSON legado se existir)
    from twilight.storage.db import init_db
    init_db()

    app = Flask(
        __name__,
        template_folder=os.path.join(_PROJECT_ROOT, 'templates'),
        static_folder=os.path.join(_PROJECT_ROOT, 'static'),
        static_url_path='/static',
    )
    app.config['SECRET_KEY'] = SECRET_KEY
    app.config['JWT_SECRET'] = JWT_SECRET
    app.config['JWT_EXPIRATION_HOURS'] = JWT_EXPIRATION_HOURS
    app.config['TIMEZONE'] = TIMEZONE_NAME
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    _install_csrf_origin_guard(app)

    socketio.init_app(app)
    register_blueprints(app)
    register_socket_handlers()

    # Reaper de salas abandonadas / turnos travados (desligável em testes)
    if not os.environ.get('DISABLE_REAPER'):
        from twilight.game.session import start_reaper
        start_reaper()

    return app
