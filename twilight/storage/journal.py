"""Persistência do journal (lore / diário) via banco de dados."""

from twilight.storage.db import (
    delete_journal_entry,
    load_journal,
    save_journal,
    upsert_journal_entry,
)

__all__ = [
    'delete_journal_entry',
    'load_journal',
    'save_journal',
    'upsert_journal_entry',
]
