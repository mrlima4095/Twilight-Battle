"""Persistência do journal (lore / diário)."""
import json

from twilight.config import JOURNAL_FILE


def load_journal():
    try:
        with open(JOURNAL_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_journal(entries):
    with open(JOURNAL_FILE, 'w', encoding='utf-8') as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
