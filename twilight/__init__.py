"""Twilight Battle — factory da aplicação Flask + SocketIO."""
import os

from twilight.config import (
    APP_TZ,
    JWT_EXPIRATION_HOURS,
    JWT_SECRET,
    SECRET_KEY,
    TIMEZONE_NAME,
    ensure_data_dirs,
)
from twilight.extensions import socketio

# Raiz do projeto (onde ficam templates/, data/, etc.)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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

    socketio.init_app(app)
    register_blueprints(app)
    register_socket_handlers()

    return app
