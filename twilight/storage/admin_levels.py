"""Persistência de níveis de admin (legado; level principal fica em accounts)."""
import json

from twilight.config import ADMIN_LEVEL_FILE


def load_admin_levels():
    try:
        with open(ADMIN_LEVEL_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_admin_levels(levels):
    with open(ADMIN_LEVEL_FILE, 'w') as f:
        json.dump(levels, f, indent=4)
