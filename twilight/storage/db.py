"""Persistência de contas e journal.

Produção (Coolify): PostgreSQL via ``DATABASE_URL``, com pool de conexões.
Dev/testes sem ``DATABASE_URL``: SQLite local, mantido como fallback.
"""
from __future__ import annotations

import atexit
import contextlib
import json
import os
import sqlite3
import threading
from typing import Any, Iterator

from twilight.config import (
    ACCOUNTS_FILE,
    DATA_DIR,
    DATABASE_PATH,
    DATABASE_URL,
    DB_POOL_SIZE,
    JOURNAL_FILE,
)

_USE_POSTGRES = DATABASE_URL.lower().startswith('postgresql://')

if _USE_POSTGRES:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

_lock = threading.RLock()
_init_lock = threading.Lock()
_initialized = False
_sqlite_conn: sqlite3.Connection | None = None
_pool: Any = None

_ACCOUNT_COLUMNS = (
    'SELECT username, password, created_at, current_game, admin_level, meta_json FROM accounts'
)

_SCHEMA_COMMON = """
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
CREATE INDEX IF NOT EXISTS idx_journal_date ON journal_entries(date);
"""

_SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS accounts (
    username TEXT PRIMARY KEY COLLATE NOCASE,
    password TEXT NOT NULL,
    created_at TEXT,
    current_game TEXT,
    admin_level INTEGER NOT NULL DEFAULT 0,
    meta_json TEXT NOT NULL DEFAULT '{}'
);
""" + _SCHEMA_COMMON + """
CREATE INDEX IF NOT EXISTS idx_accounts_current_game ON accounts(current_game);
"""

# PostgreSQL não tem collation NOCASE embutida: o código normaliza usuários para
# minúsculas antes de gravar/consultar e mantém um índice extra para segurança.
_SCHEMA_POSTGRES = (
    """
    CREATE TABLE IF NOT EXISTS accounts (
        username TEXT PRIMARY KEY,
        password TEXT NOT NULL,
        created_at TEXT,
        current_game TEXT,
        admin_level INTEGER NOT NULL DEFAULT 0,
        meta_json TEXT NOT NULL DEFAULT '{}'
    );
    """,
    """
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
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_username_lower ON accounts (lower(username));",
    "CREATE INDEX IF NOT EXISTS idx_accounts_current_game ON accounts(current_game);",
    "CREATE INDEX IF NOT EXISTS idx_journal_date ON journal_entries(date);",
)


def _q(sql: str) -> str:
    """Converte os placeholders ``?`` para o driver PostgreSQL."""
    return sql.replace('?', '%s') if _USE_POSTGRES else sql


def _ensure_pool() -> None:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=DATABASE_URL,
            open=True,
            min_size=1,
            max_size=max(1, DB_POOL_SIZE),
            kwargs={'row_factory': dict_row},
        )


def init_db() -> None:
    """Cria tabelas/índices e migra o JSON legado (somente SQLite)."""
    global _initialized, _sqlite_conn
    with _init_lock:
        if _initialized:
            return
        if _USE_POSTGRES:
            _ensure_pool()
            with _pool.connection() as conn:
                with conn.transaction():
                    with conn.cursor() as cur:
                        for statement in _SCHEMA_POSTGRES:
                            cur.execute(statement)
        else:
            os.makedirs(os.path.dirname(DATABASE_PATH) or DATA_DIR, exist_ok=True)
            _sqlite_conn = sqlite3.connect(
                DATABASE_PATH, check_same_thread=False, timeout=30
            )
            _sqlite_conn.row_factory = sqlite3.Row
            # PRAGMAs uma única vez: conexão persistente (não uma por chamada).
            _sqlite_conn.execute('PRAGMA foreign_keys = ON')
            _sqlite_conn.execute('PRAGMA journal_mode = WAL')
            _sqlite_conn.execute('PRAGMA busy_timeout = 30000')
            with _lock:
                _sqlite_conn.executescript(_SCHEMA_SQLITE)
                _migrate_from_json_if_needed(_sqlite_conn)
                _sqlite_conn.commit()
        _initialized = True


@contextlib.contextmanager
def _cursor() -> Iterator[Any]:
    """Transação curta reaproveitando pool (PG) ou conexão única (SQLite)."""
    init_db()
    if _USE_POSTGRES:
        with _pool.connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    yield cur
    else:
        assert _sqlite_conn is not None
        with _lock:
            cur = _sqlite_conn.cursor()
            try:
                yield cur
                _sqlite_conn.commit()
            except Exception:
                _sqlite_conn.rollback()
                raise
            finally:
                cur.close()


def close_db() -> None:
    """Fecha pool/conexão ao sair (evita threads órfãs no shutdown)."""
    global _pool, _sqlite_conn, _initialized
    if _pool is not None:
        try:
            _pool.close()
        except Exception:
            pass
        _pool = None
    if _sqlite_conn is not None:
        try:
            _sqlite_conn.close()
        except Exception:
            pass
        _sqlite_conn = None
    _initialized = False


atexit.register(close_db)


def _ensure_init() -> None:
    init_db()


def _norm_username(username: Any) -> str:
    return str(username or '').strip().lower()


def _account_known_keys():
    return {'password', 'created_at', 'current_game', 'admin_level', 'level'}


def _row_to_account(row: Any) -> dict:
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
        _norm_username(username),
        data.get('password') or '',
        data.get('created_at'),
        data.get('current_game'),
        admin_level,
        json.dumps(meta, ensure_ascii=False),
    )


def load_accounts() -> dict:
    """Retorna todas as contas (apenas para listagens/admin)."""
    with _cursor() as cur:
        rows = cur.execute(_q(_ACCOUNT_COLUMNS)).fetchall()
        return {row['username']: _row_to_account(row) for row in rows}


def get_account(username: str) -> dict | None:
    """Lê UMA conta — use no lugar de ``load_accounts().get(username)``."""
    with _cursor() as cur:
        row = cur.execute(
            _q(_ACCOUNT_COLUMNS + ' WHERE username = ?'), (_norm_username(username),)
        ).fetchone()
    return _row_to_account(row) if row else None


def account_exists(username: str) -> bool:
    with _cursor() as cur:
        row = cur.execute(
            _q('SELECT 1 FROM accounts WHERE username = ?'), (_norm_username(username),)
        ).fetchone()
    return row is not None


def find_linked_account(sub: str, issuer: str) -> tuple[str, dict] | None:
    """Conta vinculada a um ``oidc_sub`` guardado em ``meta_json``."""
    if _USE_POSTGRES:
        where = (
            "meta_json::jsonb->>'oidc_sub' = %s "
            "AND (coalesce(meta_json::jsonb->>'oidc_issuer', '') IN ('', %s))"
        )
    else:
        where = (
            "json_extract(meta_json, '$.oidc_sub') = ? "
            "AND (coalesce(json_extract(meta_json, '$.oidc_issuer'), '') IN ('', ?))"
        )
    with _cursor() as cur:
        row = cur.execute(_q(_ACCOUNT_COLUMNS + ' WHERE ' + where), (sub, issuer)).fetchone()
    if not row:
        return None
    return row['username'], _row_to_account(row)


def upsert_account(username: str, data: dict) -> None:
    """Insere/atualiza UMA conta (sem tocar nas demais)."""
    row = _account_to_row(username, data or {})
    with _cursor() as cur:
        cur.execute(
            _q(
                """
                INSERT INTO accounts (username, password, created_at, current_game, admin_level, meta_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    password = excluded.password,
                    created_at = excluded.created_at,
                    current_game = excluded.current_game,
                    admin_level = excluded.admin_level,
                    meta_json = excluded.meta_json
                """
            ),
            row,
        )


def update_account(username: str, updates: dict) -> bool:
    """Atualiza UMA conta de forma atômica (read-modify-write no mesmo lock)."""
    uname = _norm_username(username)
    with _cursor() as cur:
        row = cur.execute(
            _q(_ACCOUNT_COLUMNS + ' WHERE username = ?'), (uname,)
        ).fetchone()
        if row is None:
            return False
        data = _row_to_account(row)
        data.update(updates or {})
        new_row = _account_to_row(row['username'], data)
        cur.execute(
            _q(
                'UPDATE accounts SET password = ?, created_at = ?, current_game = ?, '
                'admin_level = ?, meta_json = ? WHERE username = ?'
            ),
            new_row[1:] + (row['username'],),
        )
    return True


def clear_account_game(username: str, game_id: str | None = None) -> bool:
    """Limpa ``current_game`` de uma conta, opcionalmente só se bater com game_id."""
    with _cursor() as cur:
        cur.execute(
            _q(
                'UPDATE accounts SET current_game = NULL '
                'WHERE username = ? AND (CAST(? AS TEXT) IS NULL OR current_game = ?)'
            ),
            (_norm_username(username), game_id, game_id),
        )
        return cur.rowcount > 0


def clear_accounts_current_game(game_id: str, usernames: list | None = None) -> int:
    """Limpa ``current_game`` de todas (ou algumas) contas da sala, em UMA query."""
    if not game_id:
        return 0
    sql = 'UPDATE accounts SET current_game = NULL WHERE current_game = ?'
    params: list[Any] = [game_id]
    if usernames:
        names = [_norm_username(u) for u in usernames]
        if _USE_POSTGRES:
            sql += ' AND username = ANY(%s)'
            params.append(names)
        else:
            sql += ' AND username IN (' + ','.join('?' for _ in names) + ')'
            params.extend(names)
    with _cursor() as cur:
        cur.execute(_q(sql), params)
        return cur.rowcount or 0


def delete_account(username: str) -> bool:
    with _cursor() as cur:
        cur.execute(
            _q('DELETE FROM accounts WHERE username = ?'), (_norm_username(username),)
        )
        return cur.rowcount > 0


def save_accounts(accounts: dict) -> None:
    """Upsert em lote em uma única transação (compatibilidade legada)."""
    with _cursor() as cur:
        for uname, data in (accounts or {}).items():
            row = _account_to_row(uname, data or {})
            cur.execute(
                _q(
                    """
                    INSERT INTO accounts (username, password, created_at, current_game, admin_level, meta_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(username) DO UPDATE SET
                        password = excluded.password,
                        created_at = excluded.created_at,
                        current_game = excluded.current_game,
                        admin_level = excluded.admin_level,
                        meta_json = excluded.meta_json
                    """
                ),
                row,
            )


def _entry_to_dict(row: Any) -> dict:
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
        'id', 'version', 'title', 'description', 'date', 'type',
        'features', 'improvements', 'bugfixes', 'tags',
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
    with _cursor() as cur:
        rows = cur.execute(
            """
            SELECT id, version, title, description, date, type,
                   features_json, improvements_json, bugfixes_json, tags_json, extra_json
            FROM journal_entries ORDER BY date DESC
            """
        ).fetchall()
        return [_entry_to_dict(r) for r in rows]


def save_journal(entries: list) -> None:
    """Upsert em lote do journal (NÃO remove entradas ausentes)."""
    with _cursor() as cur:
        for entry in entries or []:
            if not entry or entry.get('id') is None:
                continue
            cur.execute(
                _q(
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
                    """
                ),
                _entry_to_row(entry),
            )


def upsert_journal_entry(entry: dict) -> None:
    """Grava UMA entrada do journal, sem reescrever as demais."""
    save_journal([entry])


def delete_journal_entry(entry_id: str) -> bool:
    with _cursor() as cur:
        cur.execute(_q('DELETE FROM journal_entries WHERE id = ?'), (str(entry_id),))
        return cur.rowcount > 0


def _migrate_from_json_if_needed(conn: sqlite3.Connection) -> None:
    """Importa accounts.json / journal.json uma vez se as tabelas estiverem vazias."""
    acc_count = conn.execute('SELECT COUNT(*) FROM accounts').fetchone()[0]
    if acc_count == 0 and os.path.isfile(ACCOUNTS_FILE):
        try:
            with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
                accounts = json.load(f)
            if isinstance(accounts, dict):
                for uname, data in accounts.items():
                    row = _account_to_row(uname, data or {})
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO accounts
                        (username, password, created_at, current_game, admin_level, meta_json)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        row,
                    )
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
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO journal_entries (
                            id, version, title, description, date, type,
                            features_json, improvements_json, bugfixes_json, tags_json, extra_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        _entry_to_row(entry),
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
