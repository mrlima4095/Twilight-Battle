"""
Ponto de entrada do Twilight Battle.

Gunicorn/Coolify:  app:app
Local:             python app.py
"""
import os

from twilight import create_app
from twilight.extensions import socketio

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    # 0.0.0.0 é obrigatório em Docker/Coolify
    socketio.run(app, host='0.0.0.0', debug=False, port=port, allow_unsafe_werkzeug=True)
