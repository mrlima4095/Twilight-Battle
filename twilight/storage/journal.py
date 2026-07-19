"""Persistência do journal (lore / diário) via SQLite."""

from twilight.storage.db import load_journal, save_journal

__all__ = ['load_journal', 'save_journal']
