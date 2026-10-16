"""Configuração e caminhos de persistência."""
import os
import secrets
from datetime import datetime
from zoneinfo import ZoneInfo

# Persistência: monte o volume do Coolify em /app/data
DATA_DIR = os.environ.get('DATA_DIR') or 'data'
SAVES_DIR = os.path.join(DATA_DIR, 'saves')
# SQLite principal (contas + journal)
DATABASE_PATH = os.environ.get('DATABASE_PATH') or os.path.join(DATA_DIR, 'database.db')
# JSON legado — só usados na migração automática para o SQLite
ACCOUNTS_FILE = os.path.join(DATA_DIR, 'accounts.json')
JOURNAL_FILE = os.path.join(DATA_DIR, 'journal.json')
ADMIN_LEVEL_FILE = os.path.join(DATA_DIR, 'admin_levels.json')


def _resolve_secret(env_name: str, filename: str) -> str:
    """
    Segredo do ambiente (SECRET_KEY/JWT_SECRET) se existir.

    Caso contrário gera um valor aleatório e o persiste em DATA_DIR, de modo
    que tokens continuem válidos entre reinícios sem depender de um segredo
    público (hardcoded) no repositório.
    """
    value = (os.environ.get(env_name) or '').strip()
    if value:
        return value

    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except OSError:
        return secrets.token_hex(32)

    path = os.path.join(DATA_DIR, filename)
    try:
        if os.path.isfile(path):
            with open(path, 'r', encoding='utf-8') as fh:
                persisted = fh.read().strip()
            if persisted:
                return persisted
    except OSError:
        pass

    generated = secrets.token_hex(32)
    try:
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(generated)
        os.chmod(path, 0o600)
    except OSError:
        pass
    return generated


def _env_int(name: str, default: int) -> int:
    """Inteiro do ambiente com fallback seguro (vazio/inválido -> default)."""
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(str(raw).strip())
    except ValueError:
        return default


SECRET_KEY = _resolve_secret('SECRET_KEY', '.secret_key')
JWT_SECRET = _resolve_secret('JWT_SECRET', '.jwt_secret')
JWT_EXPIRATION_HOURS = _env_int('JWT_EXPIRATION_HOURS', 24)
JWT_ALGORITHM = 'HS256'

# Cookies Secure: em dev sobre HTTP dá para desligar com SECURE_COOKIES=false
SECURE_COOKIES = (os.environ.get('SECURE_COOKIES', 'true').strip().lower()
                  not in ('0', 'false', 'no', 'off'))

# Origens permitidas para o Socket.IO e checagem de CSRF (separadas por vírgula).
# Vazio → mesma origem (recomendado em produção).
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get('CORS_ALLOWED_ORIGINS', '').split(',')
    if origin.strip()
]

# Reaper: remove salas abandonadas e encerra turnos travados (segundos)
CLEANUP_INTERVAL_SECONDS = _env_int('CLEANUP_INTERVAL_SECONDS', 30)
FINISHED_ROOM_TTL_SECONDS = _env_int('FINISHED_ROOM_TTL_SECONDS', 900)
ABANDONED_LOBBY_TTL_SECONDS = _env_int('ABANDONED_LOBBY_TTL_SECONDS', 3600)
TURN_TIMEOUT_SECONDS = _env_int('TURN_TIMEOUT_SECONDS', 180)
# Limite de tamanho do save do modo história (bytes)
MAX_STORY_SAVE_BYTES = _env_int('MAX_STORY_SAVE_BYTES', 2 * 1024 * 1024)

# Fuso horário da aplicação (São Paulo / GMT-3)
# Pode sobrescrever com TZ= no ambiente / Coolify
TIMEZONE_NAME = os.environ.get('TZ', 'America/Sao_Paulo')
try:
    APP_TZ = ZoneInfo(TIMEZONE_NAME)
except Exception:
    APP_TZ = ZoneInfo('America/Sao_Paulo')
    TIMEZONE_NAME = 'America/Sao_Paulo'

# Garante que libs que leem TZ do ambiente vejam SP
os.environ.setdefault('TZ', TIMEZONE_NAME)

def ensure_data_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(SAVES_DIR, exist_ok=True)

def now_sp() -> datetime:
    """Agora no fuso de São Paulo (GMT-3)."""
    return datetime.now(APP_TZ)

def now_sp_str(fmt: str = '%H:%M:%S') -> str:
    """Horário formatado em São Paulo."""
    return now_sp().strftime(fmt)

def now_sp_iso() -> str:
    """ISO 8601 com offset de São Paulo (ex: ...-03:00)."""
    return now_sp().isoformat()
