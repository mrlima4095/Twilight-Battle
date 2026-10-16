"""Testes de segurança: validação de username, CSRF/Origin e rotas protegidas."""


def test_register_rejects_bad_usernames(client):
    """Só nomes no padrão [a-z0-9_]{3,20} são aceitos (bloqueia XSS via nome)."""
    bad_usernames = [
        'ab',                 # curto demais
        'x' * 21,             # longo demais
        'has space',          # espaço
        '<svg onload=alert>',  # HTML
        'café',               # acento
        "quote'name",         # aspa simples
        'UPPER',              # não normalizado (é .lower()'d para 'upper' -> ok? 'UPPER'.lower()=='upper' válido)
    ]
    for username in bad_usernames:
        r = client.post('/api/register', json={'username': username, 'password': 'pass1234'})
        data = r.get_json()
        # 'UPPER' vira 'upper' e é válido; ignoramos esse caso
        if username == 'UPPER':
            continue
        assert data['success'] is False, f'username {username!r} deveria ser rejeitado'


def test_register_and_login_flow(client):
    r = client.post('/api/register', json={'username': 'tester_sec', 'password': 'pass1234'})
    assert r.get_json()['success'] is True

    # senha errada
    r = client.post('/api/login', json={'username': 'tester_sec', 'password': 'wrong'})
    assert r.get_json()['success'] is False

    # senha certa
    r = client.post('/api/login', json={'username': 'tester_sec', 'password': 'pass1234'})
    assert r.get_json()['success'] is True
    assert 'auth_token' in r.headers.get('Set-Cookie', '')


def test_register_rejects_short_password(client):
    r = client.post('/api/register', json={'username': 'tester_pw', 'password': 'abc'})
    assert r.get_json()['success'] is False


def test_csrf_origin_guard(client):
    """POST com Origin de outro host é recusado (mitigação de CSRF)."""
    r = client.post(
        '/api/login',
        json={'username': 'anyone', 'password': 'anything'},
        headers={'Origin': 'http://evil.example'},
    )
    assert r.status_code == 403


def test_csrf_same_origin_allowed(client):
    r = client.post(
        '/api/login',
        json={'username': 'anyone', 'password': 'anything'},
        headers={'Origin': 'http://localhost'},
    )
    assert r.status_code != 403


def test_cleanup_requires_login(client):
    """/api/cleanup-games não é mais um endpoint público/aberto."""
    r = client.post('/api/cleanup-games')
    assert r.status_code != 200


def test_webhook_disabled_without_secret(client):
    """Sem WEBHOOK_SECRET, o webhook não aceita nada (nem executou antes)."""
    r = client.post('/api/webhook/github', json={'ref': 'refs/heads/main'})
    assert r.status_code == 404


def test_webhook_rejects_bad_signature(client, monkeypatch):
    """Com segredo configurado, assinatura errada -> 403."""
    import twilight.routes.webhook as wh
    monkeypatch.setattr(wh, '_WEBHOOK_SECRET', 'sekret')
    r = client.post(
        '/api/webhook/github',
        json={'ref': 'refs/heads/main', 'repository': {'full_name': 'a/b'}},
        headers={'X-Hub-Signature-256': 'sha256=' + '0' * 64},
    )
    assert r.status_code == 403
