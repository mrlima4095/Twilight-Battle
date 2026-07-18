"""Configuração e caminhos de persistência."""
import os

SECRET_KEY = os.environ.get('SECRET_KEY', 'twilight-battle-secret')
JWT_SECRET = os.environ.get('JWT_SECRET', 'twilight-battle-jwt-secret-key-change-in-production')
JWT_EXPIRATION_HOURS = int(os.environ.get('JWT_EXPIRATION_HOURS', '24'))
JWT_ALGORITHM = 'HS256'

# Persistência: monte o volume do Coolify em /app/data
DATA_DIR = os.environ.get('DATA_DIR', 'data')
SAVES_DIR = os.path.join(DATA_DIR, 'saves')
ACCOUNTS_FILE = os.path.join(DATA_DIR, 'accounts.json')
JOURNAL_FILE = os.path.join(DATA_DIR, 'journal.json')
ADMIN_LEVEL_FILE = os.path.join(DATA_DIR, 'admin_levels.json')

def ensure_data_dirs():
    os.makedirs(SAVES_DIR, exist_ok=True)
