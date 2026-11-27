#!/usr/bin/env python3
"""Copia contas e journal de um SQLite antigo para o PostgreSQL.

Uso:
    DATABASE_URL='postgresql://user:pass@host:5432/twilight_battle' \
        python scripts/migrate_sqlite_to_postgres.py /var/lib/game/database.db

A migração é idempotente (INSERT ... ON CONFLICT DO UPDATE). O SQLite de origem
é aberto somente leitura; nada é apagado dele.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

if not os.environ.get('DATABASE_URL'):
    raise SystemExit('Defina DATABASE_URL antes de rodar a migração.')

from twilight.storage import db  # noqa: E402  (precisa ler DATABASE_URL do env)


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f'PRAGMA table_info({table})')]


def _rows(conn: sqlite3.Connection, table: str):
    cols = _columns(conn, table)
    for row in conn.execute(f'SELECT {", ".join(cols)} FROM {table}'):
        yield dict(zip(cols, row))


def _loads(value, default):
    if not isinstance(value, str):
        return value if value is not None else default
    try:
        parsed = json.loads(value or json.dumps(default))
        return parsed if isinstance(parsed, type(default)) else default
    except json.JSONDecodeError:
        return default


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit('Uso: python scripts/migrate_sqlite_to_postgres.py <arquivo.sqlite>')
    source = Path(sys.argv[1]).expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f'SQLite não encontrado: {source}')

    db.init_db()
    conn = sqlite3.connect(f'file:{source}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    accounts = 0
    if 'accounts' in tables:
        for raw in _rows(conn, 'accounts'):
            username = str(raw.pop('username') or '').strip().lower()
            if not username:
                continue
            account = {
                'password': raw.get('password') or '',
                'created_at': raw.get('created_at'),
                'current_game': raw.get('current_game'),
                'admin_level': int(raw.get('admin_level') or 0),
            }
            meta = _loads(raw.get('meta_json'), {})
            if isinstance(meta, dict):
                for key, value in meta.items():
                    account.setdefault(key, value)
            account.setdefault('level', account.get('admin_level', 0))
            db.upsert_account(username, account)
            accounts += 1

    entries = 0
    if 'journal_entries' in tables:
        for raw in _rows(conn, 'journal_entries'):
            if not raw.get('id'):
                continue
            extra = _loads(raw.get('extra_json'), {})
            entry = {
                'id': raw.get('id'),
                'version': raw.get('version'),
                'title': raw.get('title'),
                'description': raw.get('description') or '',
                'date': raw.get('date'),
                'type': raw.get('type') or 'minor',
                'features': _loads(raw.get('features_json'), []),
                'improvements': _loads(raw.get('improvements_json'), []),
                'bugfixes': _loads(raw.get('bugfixes_json'), []),
                'tags': _loads(raw.get('tags_json'), []),
            }
            if isinstance(extra, dict):
                for key, value in extra.items():
                    entry.setdefault(key, value)
            db.upsert_journal_entry(entry)
            entries += 1

    conn.close()
    db.close_db()
    print(f'OK: {accounts} contas e {entries} entradas de journal migradas.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
