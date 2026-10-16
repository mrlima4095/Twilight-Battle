"""Landing pública e rota de login."""

LANDING_MARKER = 'Pronto para erguer sua legião?'   # só existe na landing
HUB_MARKER = 'Criar Nova Sala'                        # só existe no hub (index)


def test_anonymous_root_shows_landing(client):
    body = client.get('/').get_data(as_text=True)
    assert LANDING_MARKER in body
    assert HUB_MARKER not in body


def test_login_page_renders_form(client):
    r = client.get('/login')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'login-btn' in body and 'register-btn' in body


def test_landing_links_to_login(client):
    body = client.get('/').get_data(as_text=True)
    assert '/login' in body


def test_logged_in_root_shows_hub(client):
    client.post('/api/register', json={'username': 'landinguser', 'password': 'pass1234'})
    body = client.get('/').get_data(as_text=True)
    assert HUB_MARKER in body
    assert LANDING_MARKER not in body


def test_logged_in_login_redirects_home(client):
    client.post('/api/register', json={'username': 'landinguser2', 'password': 'pass1234'})
    r = client.get('/login')
    assert r.status_code == 302
    assert r.headers['Location'] == '/'


def test_protected_page_redirects_to_login(client):
    r = client.get('/tutorial')
    assert r.status_code == 302
    assert '/login' in r.headers['Location']
