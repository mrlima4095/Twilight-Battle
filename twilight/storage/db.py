"""SQLite: data/database.db — contas e journal."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from typing import Any

from twilight.config import (
    ACCOUNTS_FILE,
    DATA_DIR,
    DATABASE_PATH,
    JOURNAL_FILE,
)

_lock = threading.RLock()
_initialized = False


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DATABASE_PATH) or DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA journal_mode = WAL')
    conn.execute('PRAGMA busy_timeout = 30000')
    return conn


def init_db() -> None:
    """Cria tabelas e migra JSON legado se o DB estiver vazio."""
    global _initialized
    with _lock:
        conn = _connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    username TEXT PRIMARY KEY COLLATE NOCASE,
                    password TEXT NOT NULL,
                    created_at TEXT,
                    current_game TEXT,
                    admin_level INTEGER NOT NULL DEFAULT 0,
                    meta_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS journal_entries (
                    id TEXT PRIMARY KEY,
                    version TEXT,
                    title TEXT,
                    description TEXT,
                    date TEXT,
                    type TEXT DEFAULT 'minor',
                    features_json TEXT NOT NULL DEFAULT '[]',
                    improvements_json TEXT NOT NULL DEFAULT '[]',
                    bugfixes_json TEXT NOT NULL DEFAULT '[]',
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    extra_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_accounts_current_game
                    ON accounts(current_game);
                CREATE INDEX IF NOT EXISTS idx_journal_date
                    ON journal_entries(date);
                """
            )
            # Migra contas/journal do JSON legado (uma vez, se as tabelas vazias)
            _migrate_from_json_if_needed(conn)
            conn.commit()
        finally:
            conn.close()
        _initialized = True


def _ensure_init() -> None:
    if not _initialized:
        init_db()


def _account_known_keys():
    return {'password', 'created_at', 'current_game', 'admin_level', 'level'}


def _row_to_account(row: sqlite3.Row) -> dict:
    data: dict[str, Any] = {
        'password': row['password'],
        'created_at': row['created_at'],
        'current_game': row['current_game'],
        'admin_level': int(row['admin_level'] or 0),
    }
    try:
        meta = json.loads(row['meta_json'] or '{}')
        if isinstance(meta, dict):
            for k, v in meta.items():
                if k not in data or data[k] is None:
                    data[k] = v
    except (json.JSONDecodeError, TypeError):
        pass
    # compat: journal usava "level" em alguns lugares
    if 'level' not in data:
        data['level'] = data.get('admin_level', 0)
    return data


def _account_to_row(username: str, data: dict) -> tuple:
    meta = {
        k: v
        for k, v in (data or {}).items()
        if k not in _account_known_keys()
    }
    # se existir "level" e admin_level, prioriza admin_level; guarda level no meta se diferente
    admin_level = data.get('admin_level')
    if admin_level is None:
        admin_level = data.get('level', 0)
    try:
        admin_level = int(admin_level or 0)
    except (TypeError, ValueError):
        admin_level = 0
    if 'level' in data and data.get('level') != admin_level:
        meta['level'] = data.get('level')
    return (
        username,
        data.get('password') or '',
        data.get('created_at'),
        data.get('current_game'),
        admin_level,
        json.dumps(meta, ensure_ascii=False),
    )


def load_accounts() -> dict:
    """Retorna {username: {password, created_at, current_game, ...}}."""
    _ensure_init()
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                'SELECT username, password, created_at, current_game, admin_level, meta_json FROM accounts'
            ).fetchall()
            return {row['username']: _row_to_account(row) for row in rows}
        finally:
            conn.close()


def upsert_account(username: str, data: dict) -> None:
    """Insere/atualiza UMA conta (sem tocar nas demais)."""
    _ensure_init()
    with _lock:
        conn = _connect()
        try:
            row = _account_to_row(username, data or {})
            conn.execute(
                """
                INSERT INTO accounts (username, password, created_at, current_game, admin_level, meta_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    password = excluded.password,
                    created_at = excluded.created_at,
                    current_game = excluded.current_game,
                    admin_level = excluded.admin_level,
                    meta_json = excluded.meta_json
                """,
                row,
            )
            conn.commit()
        finally:
            conn.close()


def update_account(username: str, updates: dict) -> bool:
    """
    Aplica `updates` numa única conta de forma atômica.

    O read-modify-write acontece inteiro sob o mesmo lock, então chamadas
    concorrentes (check-auth, update_user_game, story save, admin...) não se
    sobrescrevem nem apagam outras contas.
    """
    _ensure_init()
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                'SELECT username, password, created_at, current_game, admin_level, meta_json '
                'FROM accounts WHERE username = ?',
                (username,),
            ).fetchone()
            if row is None:
                return False
            data = _row_to_account(row)
            data.update(updates or {})
            new_row = _account_to_row(row['username'], data)
            conn.execute(
                'UPDATE accounts SET password = ?, created_at = ?, current_game = ?, '
                'admin_level = ?, meta_json = ? WHERE username = ?',
                new_row[1:] + (row['username'],),
            )
            conn.commit()
            return True
        finally:
            conn.close()


def delete_account(username: str) -> bool:
    """Remove UMA conta (não mexe nas demais)."""
    _ensure_init()
    with _lock:
        conn = _connect()
        try:
            cur = conn.execute('DELETE FROM accounts WHERE username = ?', (username,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def save_accounts(accounts: dict) -> None:
    """
    Upsert em lote (compatível com a antiga API de JSON).

    Só grava/atualiza o que recebeu — NÃO remove contas ausentes do dict, para
    não apagar dados quando duas requisições concorrentes fazem
    load → modify → save. Para remover use delete_account().
    """
    _ensure_init()
    accounts = accounts or {}
    with _lock:
        conn = _connect()
        try:
            for uname, data in accounts.items():
                row = _account_to_row(uname, data or {})
                conn.execute(
                    """
                    INSERT INTO accounts (username, password, created_at, current_game, admin_level, meta_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(username) DO UPDATE SET
                        password = excluded.password,
                        created_at = excluded.created_at,
                        current_game = excluded.current_game,
                        admin_level = excluded.admin_level,
                        meta_json = excluded.meta_json
                    """,
                    row,
                )
            conn.commit()
        finally:
            conn.close()



def _entry_to_dict(row: sqlite3.Row) -> dict:
    def _loads(s, default):
        try:
            return json.loads(s or json.dumps(default))
        except (json.JSONDecodeError, TypeError):
            return default

    entry = {
        'id': row['id'],
        'version': row['version'],
        'title': row['title'],
        'description': row['description'] or '',
        'date': row['date'],
        'type': row['type'] or 'minor',
        'features': _loads(row['features_json'], []),
        'improvements': _loads(row['improvements_json'], []),
        'bugfixes': _loads(row['bugfixes_json'], []),
        'tags': _loads(row['tags_json'], []),
    }
    try:
        extra = json.loads(row['extra_json'] or '{}')
        if isinstance(extra, dict):
            for k, v in extra.items():
                if k not in entry:
                    entry[k] = v
    except (json.JSONDecodeError, TypeError):
        pass
    return entry


def _entry_to_row(entry: dict) -> tuple:
    known = {
        'id',
        'version',
        'title',
        'description',
        'date',
        'type',
        'features',
        'improvements',
        'bugfixes',
        'tags',
    }
    extra = {k: v for k, v in (entry or {}).items() if k not in known}
    return (
        str(entry.get('id') or ''),
        entry.get('version'),
        entry.get('title'),
        entry.get('description', ''),
        entry.get('date'),
        entry.get('type', 'minor'),
        json.dumps(entry.get('features') or [], ensure_ascii=False),
        json.dumps(entry.get('improvements') or [], ensure_ascii=False),
        json.dumps(entry.get('bugfixes') or [], ensure_ascii=False),
        json.dumps(entry.get('tags') or [], ensure_ascii=False),
        json.dumps(extra, ensure_ascii=False),
    )


def load_journal() -> list:
    _ensure_init()
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                """
                SELECT id, version, title, description, date, type,
                       features_json, improvements_json, bugfixes_json, tags_json, extra_json
                FROM journal_entries
                ORDER BY date DESC
                """
            ).fetchall()
            return [_entry_to_dict(r) for r in rows]
        finally:
            conn.close()


def save_journal(entries: list) -> None:
    """Upsert em lote do journal (NÃO remove entradas ausentes)."""
    _ensure_init()
    entries = entries or []
    with _lock:
        conn = _connect()
        try:
            for entry in entries:
                if not entry or entry.get('id') is None:
                    continue
                row = _entry_to_row(entry)
                conn.execute(
                    """
                    INSERT INTO journal_entries (
                        id, version, title, description, date, type,
                        features_json, improvements_json, bugfixes_json, tags_json, extra_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        version = excluded.version,
                        title = excluded.title,
                        description = excluded.description,
                        date = excluded.date,
                        type = excluded.type,
                        features_json = excluded.features_json,
                        improvements_json = excluded.improvements_json,
                        bugfixes_json = excluded.bugfixes_json,
                        tags_json = excluded.tags_json,
                        extra_json = excluded.extra_json
                    """,
                    row,
                )
            conn.commit()
        finally:
            conn.close()


def delete_journal_entry(entry_id: str) -> bool:
    """Remove UMA entrada do journal."""
    _ensure_init()
    with _lock:
        conn = _connect()
        try:
            cur = conn.execute('DELETE FROM journal_entries WHERE id = ?', (str(entry_id),))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def _migrate_from_json_if_needed(conn: sqlite3.Connection) -> None:
    """Importa accounts.json / journal.json uma vez se as tabelas estiverem vazias."""
    acc_count = conn.execute('SELECT COUNT(*) FROM accounts').fetchone()[0]
    if acc_count == 0 and os.path.isfile(ACCOUNTS_FILE):
        try:
            with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
                accounts = json.load(f)
            if isinstance(accounts, dict):
                for uname, data in accounts.items():
                    row = _account_to_row(str(uname).lower(), data or {})
                    # preserve original username casing? auth uses .lower()
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO accounts
                        (username, password, created_at, current_game, admin_level, meta_json)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (str(uname).lower(),) + row[1:],
                    )
                # rename legacy file after success
                _backup_legacy(ACCOUNTS_FILE)
        except (OSError, json.JSONDecodeError, TypeError):
            pass

    j_count = conn.execute('SELECT COUNT(*) FROM journal_entries').fetchone()[0]
    if j_count == 0 and os.path.isfile(JOURNAL_FILE):
        try:
            with open(JOURNAL_FILE, 'r', encoding='utf-8') as f:
                entries = json.load(f)
            if isinstance(entries, list):
                for entry in entries:
                    if not entry or entry.get('id') is None:
                        continue
                    row = _entry_to_row(entry)
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO journal_entries (
                            id, version, title, description, date, type,
                            features_json, improvements_json, bugfixes_json, tags_json, extra_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        row,
                    )
                _backup_legacy(JOURNAL_FILE)
        except (OSError, json.JSONDecodeError, TypeError):
            pass


def _backup_legacy(path: str) -> None:
    try:
        bak = path + '.migrated.bak'
        if not os.path.exists(bak):
            os.rename(path, bak)
    except OSError:
        pass
