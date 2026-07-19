"""Configuração e caminhos de persistência."""
import os
from datetime import datetime
from zoneinfo import ZoneInfo

SECRET_KEY = os.environ.get('SECRET_KEY', 'twilight-battle-secret')
JWT_SECRET = os.environ.get('JWT_SECRET', 'twilight-battle-jwt-secret-key-change-in-production')
JWT_EXPIRATION_HOURS = int(os.environ.get('JWT_EXPIRATION_HOURS', '24'))
JWT_ALGORITHM = 'HS256'

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

# Persistência: monte o volume do Coolify em /app/data
DATA_DIR = os.environ.get('DATA_DIR', 'data')
SAVES_DIR = os.path.join(DATA_DIR, 'saves')
# SQLite principal (contas + journal)
DATABASE_PATH = os.environ.get('DATABASE_PATH', os.path.join(DATA_DIR, 'database.db'))
# JSON legado — só usados na migração automática para o SQLite
ACCOUNTS_FILE = os.path.join(DATA_DIR, 'accounts.json')
JOURNAL_FILE = os.path.join(DATA_DIR, 'journal.json')
ADMIN_LEVEL_FILE = os.path.join(DATA_DIR, 'admin_levels.json')

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
