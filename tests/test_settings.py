"""Página de configurações da conta: senha, preferências e exclusão.

O app (e o banco) é compartilhado entre os testes, por isso cada teste usa um
usuário próprio — o cliente HTTP, porém, é recriado a cada teste.
"""


def _register(client, username, password):
    r = client.post('/api/register', json={'username': username, 'password': password})
    assert r.get_json()['success'] is True, f'falha ao registrar {username}: {r.get_json()}'
    return r


# ---------------------------------------------------------------- página

def test_settings_requires_login(client):
    r = client.get('/settings')
    assert r.status_code == 302
    assert '/login' in r.headers['Location']


def test_settings_page_renders_for_logged_user(client):
    _register(client, 'cfg_page', 'pass1234')
    r = client.get('/settings')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    for needle in ('changePwdBtn', 'savePrefsBtn', 'deleteAccountBtn', 'oldPassword'):
        assert needle in body


# ---------------------------------------------------------------- conta

def test_settings_hides_danger_zone_for_admin(client):
    from twilight.auth.service import update_account

    _register(client, 'cfg_pageadmin', 'pass1234')
    update_account('cfg_pageadmin', {'admin_level': 5})
    body = client.get('/settings').get_data(as_text=True)
    # O painel (e o botão) não são renderizados; a referência no JS pode existir.
    assert 'id="deleteAccountBtn"' not in body
    assert 'Zona de perigo' not in body
    assert 'id="changePwdBtn"' in body


def test_account_requires_auth(client):
    r = client.get('/api/account')
    assert r.status_code == 401
    assert r.get_json()['success'] is False


def test_account_returns_defaults(client):
    _register(client, 'cfg_defaults', 'pass1234')
    data = client.get('/api/account').get_json()
    assert data['success'] is True
    assert data['account']['username'] == 'cfg_defaults'
    assert data['account']['preferences'] == {
        'max_players': 6,
        'private': False,
        'allow_spectators': True,
        'chat_enabled': True,
    }


# ---------------------------------------------------------------- senha

def test_change_password_validations(client):
    _register(client, 'cfg_pwdval', 'oldpass1')

    wrong = client.post('/api/account/change-password',
                        json={'current_password': 'nope', 'new_password': 'newpass1'})
    assert wrong.status_code == 400

    short = client.post('/api/account/change-password',
                        json={'current_password': 'oldpass1', 'new_password': 'ab'})
    assert short.status_code == 400

    same = client.post('/api/account/change-password',
                       json={'current_password': 'oldpass1', 'new_password': 'oldpass1'})
    assert same.status_code == 400


def test_change_password_success_and_login(client):
    _register(client, 'cfg_pwdok', 'oldpass1')
    ok = client.post('/api/account/change-password',
                     json={'current_password': 'oldpass1', 'new_password': 'newpass1'})
    assert ok.status_code == 200
    assert ok.get_json()['success'] is True

    # A senha antiga não funciona mais; a nova sim.
    client.post('/api/logout')
    assert client.post('/api/login', json={'username': 'cfg_pwdok',
                                           'password': 'oldpass1'}).get_json()['success'] is False
    assert client.post('/api/login', json={'username': 'cfg_pwdok',
                                           'password': 'newpass1'}).get_json()['success'] is True


# ---------------------------------------------------------------- preferências

def test_preferences_roundtrip(client):
    _register(client, 'cfg_prefs', 'pass1234')
    payload = {'max_players': 9, 'private': True, 'allow_spectators': False, 'chat_enabled': True}
    r = client.post('/api/account/preferences', json={'preferences': payload})
    assert r.status_code == 200
    assert r.get_json()['preferences'] == payload

    stored = client.get('/api/account').get_json()['account']['preferences']
    assert stored == payload


def test_preferences_reject_invalid_max_players(client):
    _register(client, 'cfg_prefsbad', 'pass1234')
    r = client.post('/api/account/preferences', json={'preferences': {'max_players': 99}})
    assert r.status_code == 400
    r = client.post('/api/account/preferences', json={'preferences': {'max_players': 'abc'}})
    assert r.status_code == 400


def test_preferences_reject_non_dict(client):
    _register(client, 'cfg_prefsnon', 'pass1234')
    r = client.post('/api/account/preferences', json={'preferences': 'nope'})
    assert r.status_code == 400


# ---------------------------------------------------------------- exclusão

def test_delete_account_requires_confirm_and_password(client):
    _register(client, 'cfg_delreq', 'pass1234')
    assert client.post('/api/account/delete',
                       json={'password': 'pass1234', 'confirm': 'nao'}).status_code == 400
    assert client.post('/api/account/delete',
                       json={'password': 'errada', 'confirm': 'APAGAR'}).status_code == 400


def test_delete_account_success(client):
    _register(client, 'cfg_delok', 'pass1234')
    r = client.post('/api/account/delete',
                    json={'password': 'pass1234', 'confirm': 'APAGAR'})
    assert r.status_code == 200
    assert r.get_json()['success'] is True
    # Não dá mais para logar.
    assert client.post('/api/login', json={'username': 'cfg_delok',
                                           'password': 'pass1234'}).get_json()['success'] is False


def test_delete_account_blocked_for_admin(client):
    from twilight.auth.service import update_account

    _register(client, 'cfg_admin', 'adminpass')
    update_account('cfg_admin', {'admin_level': 2})
    r = client.post('/api/account/delete', json={'password': 'adminpass', 'confirm': 'APAGAR'})
    assert r.status_code == 403
    # A conta continua existindo.
    assert client.post('/api/login', json={'username': 'cfg_admin',
                                           'password': 'adminpass'}).get_json()['success'] is True


def test_delete_account_blocked_during_game(client):
    from twilight.auth.service import update_account
    from twilight.state import games

    _register(client, 'cfg_ingame', 'pass1234')
    games['FAKEGAME'] = object()  # basta existir a chave para o guard
    try:
        update_account('cfg_ingame', {'current_game': 'FAKEGAME'})
        r = client.post('/api/account/delete', json={'password': 'pass1234', 'confirm': 'APAGAR'})
        assert r.status_code == 409
    finally:
        games.pop('FAKEGAME', None)
