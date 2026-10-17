"""Testes da API de saves do modo história (story).

O cliente é autoritativo (monta o save no localStorage), então o servidor
valida e normaliza tudo que vem do navegador. Estes testes cobrem:

  * autenticação obrigatória nos endpoints;
  * round-trip salvar/carregar;
  * rejeição de saves malformados (sem personagem, sem nome);
  * clamping de valores absurdos (ouro negativo, nível gigante, vida > vida máx.);
  * coerência de morte (isDead == vida <= 0);
  * limite de tamanho do payload.
"""


def _register(client, username, password='pass1234'):
    r = client.post('/api/register', json={'username': username, 'password': password})
    assert r.get_json()['success'] is True, f'falha ao registrar {username}: {r.get_json()}'
    return r


def _valid_save(**overrides):
    save = {
        'character': {
            'name': 'Herói',
            'race': 'elf',
            'level': 3,
            'exp': 120,
            'gold': 500,
            'life': 400,
            'maxLife': 512,
            'mana': 80,
            'maxMana': 80,
        },
        'inventory': [None, {'id': 'wood', 'quantity': 5}],
        'equipment': {'helmet': None},
        'location': 'home',
        'isDead': False,
        'activeQuest': None,
    }
    save.update(overrides)
    return save


# ---------------------------------------------------------------- auth

def test_save_requires_login(client):
    r = client.post('/api/save-game', json={'save_data': _valid_save()})
    assert r.status_code in (301, 302, 401)
    assert '/login' in r.headers.get('Location', '')


def test_load_requires_login(client):
    r = client.get('/api/load-game')
    assert r.status_code in (301, 302, 401)
    assert '/login' in r.headers.get('Location', '')


# ---------------------------------------------------------------- round-trip

def test_save_and_load_roundtrip(client):
    _register(client, 'story_roundtrip')
    save = _valid_save()

    r = client.post('/api/save-game', json={'save_data': save})
    body = r.get_json()
    assert r.status_code == 200
    assert body['success'] is True
    assert body['character_name'] == 'Herói'

    r = client.get('/api/load-game')
    body = r.get_json()
    assert r.status_code == 200
    assert body['success'] is True
    assert body['character_name'] == 'Herói'
    assert body['save_data']['character']['gold'] == 500
    assert body['save_data']['inventory'][1]['id'] == 'wood'


def test_load_without_save_returns_404(client):
    _register(client, 'story_nosave')
    r = client.get('/api/load-game')
    assert r.status_code == 404


# ---------------------------------------------------------------- validação

def test_save_rejects_empty_payload(client):
    _register(client, 'story_empty')
    assert client.post('/api/save-game', json={}).get_json()['success'] is False


def test_save_rejects_non_dict(client):
    _register(client, 'story_nondict')
    r = client.post('/api/save-game', json={'save_data': [1, 2, 3]})
    assert r.status_code == 400


def test_save_rejects_missing_character(client):
    _register(client, 'story_nochar')
    r = client.post('/api/save-game', json={'save_data': {'inventory': []}})
    assert r.status_code == 400
    assert r.get_json()['success'] is False


def test_save_rejects_blank_name(client):
    _register(client, 'story_blankname')
    save = _valid_save()
    save['character']['name'] = '   '
    r = client.post('/api/save-game', json={'save_data': save})
    assert r.status_code == 400


# ---------------------------------------------------------------- normalização

def test_save_clamps_absurd_values(client):
    _register(client, 'story_clamp')
    save = _valid_save()
    save['character'].update({
        'gold': -5000,
        'level': 99999,
        'exp': -10,
        'life': 999999,      # acima de maxLife
        'maxLife': -5,       # absurdo → volta para 1
        'mana': 999999,
    })
    save['inventory'] = 'não é lista'

    r = client.post('/api/save-game', json={'save_data': save})
    assert r.status_code == 200
    assert r.get_json()['success'] is True

    loaded = client.get('/api/load-game').get_json()['save_data']
    c = loaded['character']
    assert c['gold'] == 0            # não negativo
    assert c['level'] <= 200
    assert c['exp'] == 0
    assert c['maxLife'] >= 1
    assert 0 <= c['life'] <= c['maxLife']
    assert c['mana'] <= c['maxMana']
    assert loaded['inventory'] == []  # tipo corrigido
    assert loaded['isDead'] is False


def test_save_normalizes_survival(client):
    """Fome/sede ficam presos em 0..100 e usam o padrão 'cheio' quando ausentes."""
    _register(client, 'story_survival')
    save = _valid_save()
    save['survival'] = {'hunger': 9999, 'thirst': -20}

    r = client.post('/api/save-game', json={'save_data': save})
    assert r.status_code == 200
    assert r.get_json()['success'] is True

    loaded = client.get('/api/load-game').get_json()['save_data']
    assert loaded['survival']['hunger'] == 100
    assert loaded['survival']['thirst'] == 0

    # Save antigo, sem o campo → servidor injeta o padrão cheio.
    from twilight.routes.story import validate_and_normalize_save
    ok, err = validate_and_normalize_save(_valid_save())
    assert err is None
    assert ok['survival'] == {'hunger': 100, 'thirst': 100}


def test_save_normalizes_death_consistency(client):
    _register(client, 'story_death')
    # Vida zero mas marcado como vivo → servidor força morte.
    save = _valid_save()
    save['character']['life'] = 0
    save['isDead'] = False

    r = client.post('/api/save-game', json={'save_data': save})
    assert r.status_code == 200

    loaded = client.get('/api/load-game').get_json()
    assert loaded['success'] is False
    assert loaded['is_dead'] is True


def test_load_dead_save_returns_410(client):
    _register(client, 'story_dead410')
    save = _valid_save()
    save['character']['life'] = 0
    save['isDead'] = True
    client.post('/api/save-game', json={'save_data': save})

    r = client.get('/api/load-game')
    assert r.status_code == 410
    assert r.get_json()['is_dead'] is True


# ---------------------------------------------------------------- limite de tamanho

def test_save_rejects_oversized_payload(client, monkeypatch):
    import twilight.routes.story as story_routes
    monkeypatch.setattr(story_routes, 'MAX_STORY_SAVE_BYTES', 1024)

    _register(client, 'story_big')
    save = _valid_save(location='x' * 4096)

    r = client.post('/api/save-game', json={'save_data': save})
    assert r.status_code == 413


# ---------------------------------------------------------------- sanitize unitário

def test_validate_and_normalize_save_unit():
    from twilight.routes.story import validate_and_normalize_save

    ok, err = validate_and_normalize_save(_valid_save())
    assert err is None
    assert ok['character']['name'] == 'Herói'

    bad, err = validate_and_normalize_save({'character': {}})
    assert bad is None
    assert err

    bad, err = validate_and_normalize_save('nope')
    assert bad is None
    assert err

    # Nome longo é truncado
    long_name, err = validate_and_normalize_save(_valid_save())
    long_name['character']['name'] = 'A' * 500
    ok, err = validate_and_normalize_save(long_name)
    assert err is None
    assert len(ok['character']['name']) <= 60
