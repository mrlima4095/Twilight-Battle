"""Testes de persistência: migração JSON e integridade das contas."""
import json

from twilight.storage import db


def _fresh_db(tmp_path, monkeypatch, accounts_json=None):
    """Aponta a camada de storage para um banco temporário isolado."""
    monkeypatch.setattr(db, 'DATABASE_PATH', str(tmp_path / 'test.db'))
    monkeypatch.setattr(db, 'ACCOUNTS_FILE', str(tmp_path / 'accounts.json'))
    monkeypatch.setattr(db, 'JOURNAL_FILE', str(tmp_path / 'journal.json'))
    monkeypatch.setattr(db, '_initialized', False)
    if accounts_json is not None:
        (tmp_path / 'accounts.json').write_text(json.dumps(accounts_json))
    db.init_db()
    return db.load_accounts()


def test_migration_from_legacy_json(tmp_path, monkeypatch):
    """O JSON legado deve ser migrado para o SQLite (o bug era não ser)."""
    acc = _fresh_db(
        tmp_path,
        monkeypatch,
        accounts_json={'loopuser': {'password': 'p$hash', 'created_at': '2024'}},
    )
    assert 'loopuser' in acc
    # o arquivo legado é renomeado após a migração
    assert not (tmp_path / 'accounts.json').exists()
    assert (tmp_path / 'accounts.json.migrated.bak').exists()


def test_save_accounts_no_delete_by_omission(tmp_path, monkeypatch):
    """save_accounts só faz upsert — não apaga contas ausentes do dict."""
    _fresh_db(tmp_path, monkeypatch, accounts_json={'aaa': {'password': 'p'}})
    db.save_accounts({'bbb': {'password': 'p2'}})
    acc = db.load_accounts()
    assert 'aaa' in acc, 'conta aaa foi apagada por omissão!'
    assert 'bbb' in acc


def test_delete_account_only_removes_target(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch, accounts_json={'aaa': {'password': 'p'}})
    db.save_accounts({'bbb': {'password': 'p2'}})
    assert db.delete_account('aaa') is True
    acc = db.load_accounts()
    assert 'aaa' not in acc
    assert 'bbb' in acc


def test_update_account_atomic(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch, accounts_json={'aaa': {'password': 'p'}})
    assert db.update_account('aaa', {'current_game': 'G1'}) is True
    assert db.load_accounts()['aaa']['current_game'] == 'G1'
    # atualizar conta inexistente falha sem criar nada
    assert db.update_account('ghost', {'current_game': 'G1'}) is False
    assert 'ghost' not in db.load_accounts()


def test_journal_delete_only_removes_target(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    db.save_journal([{'id': '1', 'version': '1.0', 'title': 'A'},
                     {'id': '2', 'version': '1.1', 'title': 'B'}])
    assert db.delete_journal_entry('1') is True
    ids = {e['id'] for e in db.load_journal()}
    assert ids == {'2'}
