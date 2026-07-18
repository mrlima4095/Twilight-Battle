# Twilight Battle — Flask + SocketIO (gevent)
# Coolify: detecta este Dockerfile automaticamente.
# Porta: 5000 (ou $PORT). Só 1 worker — estado do jogo fica em memória.

FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5000

WORKDIR /app

# Dependências de sistema mínimas (gevent/compila se precisar de wheels)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Persistência: no Coolify, volume em /app/data
# data/accounts.json, data/journal.json, data/admin_levels.json, data/saves/
RUN mkdir -p /app/data/saves
VOLUME ["/app/data"]

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:' + __import__('os').environ.get('PORT','5000') + '/', timeout=3)" || exit 1

# 1 worker: games/players ficam em dicts em memória + WebSocket sticky
CMD ["sh", "-c", "exec gunicorn --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker --workers 1 --bind 0.0.0.0:${PORT:-5000} --timeout 120 --keep-alive 5 --access-logfile - --error-logfile - app:app"]
