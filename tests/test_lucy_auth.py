"""Login OIDC com a Lucy e modos de autenticação por ambiente."""
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from twilight import config
from twilight.auth import lucy as lucy_oidc
from twilight.auth.service import load_accounts
from twilight.routes import auth as auth_routes
from twilight.routes import lucy_auth


@pytest.fixture()
def lucy_mode(app, monkeypatch):
    """Habilita o login da Lucy sem depender do env do processo de teste."""
    monkeypatch.setattr(config, 'AUTH_MODE', 'lucy')
    monkeypatch.setattr(config, 'auth_allows_lucy', lambda: True)
    monkeypatch.setattr(auth_routes, 'AUTH_MODE', 'lucy')
    monkeypatch.setattr(auth_routes, 'auth_allows_internal', lambda: False)
    app.jinja_env.globals['auth_allows_lucy'] = lambda: True
    app.jinja_env.globals['auth_allows_internal'] = lambda: False
    return app


def test_pkce_challenge_rfc_vector():
    # Vetor do RFC 7636, apêndice B.
    verifier = 'dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk'
    assert lucy_oidc.pkce_challenge(verifier) == 'E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM'


def test_normalize_username():
    assert lucy_oidc.normalize_username('Fetuber') == 'fetuber'
    assert lucy_oidc.normalize_username('João Silva') == 'joao_silva'
    assert lucy_oidc.normalize_username('ab') == 'ab_'


def test_verify_id_token_rs256(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk['kid'] = 'teste-kid'
    monkeypatch.setattr(config, 'LUCY_CLIENT_ID', 'game')
    monkeypatch.setattr(config, 'LUCY_ISSUER', 'https://chat.opentty.fun')
    monkeypatch.setattr(lucy_oidc, 'jwks', lambda: [public_jwk])

    now = int(time.time())
    token = jwt.encode({
        'iss': 'https://chat.opentty.fun',
        'aud': 'game',
        'sub': 'fetuber',
        'iat': now,
        'exp': now + 300,
        'preferred_username': 'fetuber',
    }, private_key, algorithm='RS256', headers={'kid': 'teste-kid'})

    claims = lucy_oidc.verify_id_token(token)
    assert claims['sub'] == 'fetuber'

    # Outra audiência não pode entrar neste cliente.
    wrong = jwt.encode({
        'iss': 'https://chat.opentty.fun',
        'aud': 'outro-app',
        'sub': 'fetuber',
        'iat': now,
        'exp': now + 300,
    }, private_key, algorithm='RS256', headers={'kid': 'teste-kid'})
    with pytest.raises(lucy_oidc.OidcError):
        lucy_oidc.verify_id_token(wrong)


def test_provision_creates_local_linked_account():
    username = lucy_oidc.provision({
        'sub': 'lucy-sub-criação-1',
        'preferred_username': 'lucynewplayer',
        'name': 'Lucy New Player',
        'email': 'new@chat.opentty.fun',
    })
    account = load_accounts()[username]
    assert username == 'lucynewplayer'
    assert account['auth_provider'] == 'lucy'
    assert account['oidc_sub'] == 'lucy-sub-criação-1'
    assert account['oidc_email'] == 'new@chat.opentty.fun'
    assert account['realname'] == 'Lucy New Player'


def test_provision_links_existing_internal_account_preserving_progress():
    accounts = load_accounts()
    accounts['legacyplayer'] = {
        'password': 'hash-antigo',
        'created_at': '2024-01-01T00:00:00',
        'current_game': None,
        'admin_level': 4,
    }
    from twilight.auth.service import save_accounts
    save_accounts(accounts)

    username = lucy_oidc.provision({
        'sub': 'lucy-sub-legacy-1',
        'preferred_username': 'legacyplayer',
        'name': 'Legacy',
    })
    account = load_accounts()[username]
    assert username == 'legacyplayer'
    assert account['admin_level'] == 4
    assert account['oidc_sub'] == 'lucy-sub-legacy-1'


def test_oidc_callback_issues_local_cookie(client, lucy_mode, monkeypatch):
    monkeypatch.setattr(config, 'LUCY_CLIENT_ID', 'game')
    monkeypatch.setattr(config, 'LUCY_CLIENT_SECRET', 'segredo')
    monkeypatch.setattr(config, 'LUCY_REDIRECT_URI', 'http://localhost/auth/lucy/callback')
    monkeypatch.setattr(lucy_auth.lucy_oidc, 'is_configured', lambda: True)
    monkeypatch.setattr(
        lucy_auth.lucy_oidc,
        'authorization_url',
        lambda state, challenge: f'https://chat.opentty.fun/sso/authorize?state={state}',
    )
    monkeypatch.setattr(
        lucy_auth.lucy_oidc,
        'exchange_code',
        lambda code, verifier: {'id_token': 'id', 'access_token': 'access'},
    )
    monkeypatch.setattr(
        lucy_auth.lucy_oidc,
        'fetch_claims',
        lambda tokens: {
            'sub': 'lucy-sub-callback-1',
            'preferred_username': 'callbackplayer',
            'name': 'Callback Player',
        },
    )

    started = client.get('/auth/lucy/login', query_string={'next': '/settings'})
    assert started.status_code == 302
    assert started.headers['Location'].startswith('https://chat.opentty.fun/sso/authorize')

    with client.session_transaction() as sess:
        state = sess['lucy_oidc']['state']
        assert sess['lucy_oidc']['next'] == '/settings'

    done = client.get('/auth/lucy/callback', query_string={'state': state, 'code': 'codigo'})
    assert done.status_code == 302
    assert done.headers['Location'] == '/settings'
    assert 'auth_token=' in done.headers.get('Set-Cookie', '')

    who = client.get('/api/check-auth').get_json()
    assert who['authenticated'] is True
    assert who['username'] == 'callbackplayer'
    assert who['auth_provider'] == 'lucy'


def test_oidc_callback_rejects_state_mismatch(client, lucy_mode, monkeypatch):
    monkeypatch.setattr(lucy_auth.lucy_oidc, 'is_configured', lambda: True)
    monkeypatch.setattr(
        lucy_auth.lucy_oidc,
        'authorization_url',
        lambda state, challenge: f'https://chat.opentty.fun/sso/authorize?state={state}',
    )
    client.get('/auth/lucy/login')
    response = client.get('/auth/lucy/callback', query_string={'state': 'errado', 'code': 'x'})
    assert response.status_code == 302
    assert 'invalid_state' in response.headers['Location']
    assert client.get('/api/check-auth').get_json()['authenticated'] is False


def test_lucy_only_blocks_internal_api_and_form(client, lucy_mode):
    body = client.get('/login').get_data(as_text=True)
    assert 'lucy-login-btn' in body
    assert 'id="login-btn"' not in body
    assert 'id="register-tab"' not in body

    assert client.post('/api/login', json={'username': 'x', 'password': 'y'}).status_code == 403
    assert client.post('/api/register', json={'username': 'x', 'password': 'y'}).status_code == 403
