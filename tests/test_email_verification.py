"""Cadastro local com email confirmado; Lucy entra verificada direto."""
from twilight.auth import email_verification as ev
from twilight.auth import lucy as lucy_oidc
from twilight.auth.service import hash_password
from twilight.routes import auth as auth_routes
from twilight.storage import db


def _enable_verification(monkeypatch):
    monkeypatch.setattr(auth_routes, 'EMAIL_VERIFICATION_REQUIRED', True)

    tokens = []

    def fake_send(username, email):
        raw, _ = ev.mark_unverified(username, email)
        tokens.append(raw)
        return True, raw

    monkeypatch.setattr(auth_routes.email_verification, 'send_verification', fake_send)
    return tokens


def test_register_requires_email_and_confirmation(client, monkeypatch):
    tokens = _enable_verification(monkeypatch)

    no_email = client.post('/api/register', json={
        'username': 'sem_email', 'password': 'pass1234',
    })
    assert no_email.get_json()['success'] is False

    r = client.post('/api/register', json={
        'username': 'verif_player', 'password': 'pass1234',
        'email': 'Verif@Example.COM',
    })
    data = r.get_json()
    assert data['success'] is True
    assert data['requires_verification'] is True
    assert data['email_sent'] is True
    assert 'auth_token' not in r.headers.get('Set-Cookie', '')

    account = db.get_account('verif_player')
    assert account['email'] == 'verif@example.com'
    assert account['email_verified'] is False

    blocked = client.post('/api/login', json={
        'username': 'verif_player', 'password': 'pass1234',
    })
    assert blocked.status_code == 403
    assert blocked.get_json()['requires_verification'] is True

    # Reenvia e usa o segundo token (o primeiro continua válido até expirar).
    resent = client.post('/api/resend-verification', json={'username': 'verif_player'})
    assert resent.get_json()['success'] is True
    assert len(tokens) == 2

    bad = client.get('/verify-email/token-errado')
    assert bad.status_code == 302
    assert 'verify_error=1' in bad.headers['Location']

    good = client.get(f'/verify-email/{tokens[1]}')
    assert good.status_code == 302
    assert 'email_verified=1' in good.headers['Location']
    assert 'auth_token' in good.headers.get('Set-Cookie', '')

    # Link já usado não pode confirmar de novo.
    reused = client.get(f'/verify-email/{tokens[1]}')
    assert reused.status_code == 302
    assert 'verify_error=1' in reused.headers['Location']

    login = client.post('/api/login', json={
        'username': 'verif_player', 'password': 'pass1234',
    })
    assert login.get_json()['success'] is True


def test_email_uniqueness(client, monkeypatch):
    _enable_verification(monkeypatch)

    first = client.post('/api/register', json={
        'username': 'email_unico_1', 'password': 'pass1234',
        'email': 'unico@example.com',
    })
    assert first.get_json()['success'] is True

    second = client.post('/api/register', json={
        'username': 'email_unico_2', 'password': 'pass1234',
        'email': 'UNICO@example.com',
    })
    assert second.get_json()['success'] is False
    assert 'email' in second.get_json()['message'].lower()


def test_legacy_account_without_email_still_logs_in(client, monkeypatch):
    _enable_verification(monkeypatch)

    db.upsert_account('legacy_sem_email', {
        'password': hash_password('pass1234'),
        'created_at': '2020-01-01T00:00:00',
    })
    assert ev.is_verified(db.get_account('legacy_sem_email')) is True

    r = client.post('/api/login', json={
        'username': 'legacy_sem_email', 'password': 'pass1234',
    })
    assert r.get_json()['success'] is True


def test_lucy_account_is_verified_without_local_email(client):
    username = lucy_oidc.provision({
        'sub': 'lucy-verificada-1',
        'preferred_username': 'lucyverificada',
        'name': 'Lucy Verificada',
        'email': 'lucy@example.com',
    })
    account = db.get_account(username)
    assert account['auth_provider'] == 'lucy'
    assert account['email'] == 'lucy@example.com'
    assert account['email_verified'] is True
    assert ev.is_verified(account) is True

    # Não há token local pendente: a Lucy já validou o email.
    assert not account.get('email_verify_token_hash')
