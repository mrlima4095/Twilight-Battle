"""Fixtures dos testes.

As variáveis de ambiente precisam ser definidas ANTES de qualquer import do
projeto, porque twilight.config lê o ambiente no momento do import.
"""
import os
import tempfile

_data_dir = tempfile.mkdtemp(prefix='twilight-test-')
os.environ['DATA_DIR'] = _data_dir
os.environ['DISABLE_REAPER'] = '1'          # não dispara a task de fundo nos testes
os.environ['TURN_TIMEOUT_SECONDS'] = '0'
os.environ['SECRET_KEY'] = 'test-secret-key'
os.environ['JWT_SECRET'] = 'test-jwt-secret'
os.environ['SECURE_COOKIES'] = 'false'

import pytest  # noqa: E402


@pytest.fixture(scope='session')
def app():
    from twilight import create_app
    return create_app()


@pytest.fixture()
def client(app):
    return app.test_client()
