"""Admin mostra contas Lucy/email, envia email como admin@ e desativa contas."""

from twilight.auth.service import update_account
from twilight.storage.db import get_account


def _register(client, username, level):
    r = client.post('/api/register', json={'username': username, 'password': 'pass1234'})
    assert r.get_json()['success'] is True, r.get_json()
    update_account(username, {'admin_level': level})


def test_users_expõe_email_e_vinculo_lucy(client, app):
    _register(client, 'admin_users_view', 1)
    _register(app.test_client(), 'lucy_linked_view', 0)
    update_account('lucy_linked_view', {
        'auth_provider': 'lucy',
        'oidc_sub': 'lucy-sub-123',
        'oidc_issuer': 'https://chat.opentty.fun',
        'email': 'linked@opentty.fun',
        'oidc_email': 'linked@opentty.fun',
        'email_verified': True,
        'admin_level': 0,
    })

    r = client.get('/api/admin/users')
    assert r.status_code == 200
    users = {u['username']: u for u in r.get_json()['users']}

    lucy = users['lucy_linked_view']
    assert lucy['auth_provider'] == 'lucy'
    assert lucy['oidc_sub'] == 'lucy-sub-123'
    assert lucy['email'] == 'linked@opentty.fun'
    assert lucy['email_verified'] is True
    assert lucy['active'] is True
    assert 'password' not in lucy

    r = client.get('/api/admin/user/lucy_linked_view')
    assert r.get_json()['user']['oidc_issuer'] == 'https://chat.opentty.fun'


def test_desativar_conta_bloqueia_login_e_jwt(client, app):
    _register(client, 'admin_disable_owner', 4)
    target = app.test_client()
    _register(target, 'disabled_target', 0)
    assert target.get('/api/check-auth').get_json()['authenticated'] is True

    r = client.put(
        '/api/admin/user/disabled_target/status',
        json={'active': False},
    )
    assert r.status_code == 200
    assert get_account('disabled_target')['active'] is False

    # Login novo é negado e um JWT já emitido deixa de autenticar.
    other = app.test_client()
    r = other.post('/api/login', json={
        'username': 'disabled_target', 'password': 'pass1234',
    })
    assert r.status_code == 403
    assert 'desativada' in r.get_json()['message']
    assert target.get('/api/check-auth').get_json()['authenticated'] is False

    r = client.put(
        '/api/admin/user/disabled_target/status', json={'status': 'active'},
    )
    assert r.status_code == 200
    assert get_account('disabled_target')['active'] is True


def test_admin_email_usa_remetente_admin(client, app, monkeypatch):
    _register(client, 'admin_email_owner', 1)
    _register(app.test_client(), 'email_target_admin', 0)
    update_account('email_target_admin', {
        'email': 'target@opentty.fun', 'email_verified': True, 'admin_level': 0,
    })
    captured = []
    monkeypatch.setattr(
        'twilight.routes.admin.send_admin_email',
        lambda to, subject, body: captured.append((to, subject, body)) or True,
    )

    r = client.post('/api/admin/user/email_target_admin/email', json={
        'subject': 'Aviso', 'body': 'Olá, jogador!',
    })
    assert r.status_code == 200
    assert captured == [('target@opentty.fun', 'Aviso', 'Olá, jogador!')]


def test_mailer_admin_from_sem_mexer_no_noreply(monkeypatch):
    import twilight.mailer as mailer

    captured = []
    monkeypatch.setattr(mailer, 'MAIL_ENABLED', True)
    monkeypatch.setattr(mailer, 'run_offloop', lambda fn, msg: captured.append(msg))

    assert mailer.send_email('a@b.com', 'Auto', 'corpo') is True
    assert captured[-1]['From'] == mailer.MAIL_FROM

    assert mailer.send_admin_email('a@b.com', 'Admin', 'corpo') is True
    assert captured[-1]['From'] == mailer.MAIL_ADMIN_FROM
    assert mailer.MAIL_ADMIN_FROM == 'admin@game.opentty.fun'
