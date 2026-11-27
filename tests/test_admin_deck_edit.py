"""Edição administrativa das próximas cartas do deck."""

from types import SimpleNamespace

from twilight.auth.service import update_account
from twilight.cards.definitions import CARDS
from twilight.state import games


def _register(client, username, password='pass1234'):
    r = client.post('/api/register', json={'username': username, 'password': password})
    assert r.get_json()['success'] is True, r.get_json()


def _card(card_id, instance_id):
    card = CARDS[card_id].copy()
    card['instance_id'] = instance_id
    return card


def _setup(client, username, game_id, card_ids=('orc', 'elfo', 'mago')):
    _register(client, username)
    update_account(username, {'admin_level': 1})
    game = SimpleNamespace(deck=[_card(cid, f'i{i}') for i, cid in enumerate(card_ids)])
    games[game_id] = game
    return game


def _edit(client, game_id, body):
    return client.post(f'/api/admin/game/{game_id}/deck/edit', json=body)


def test_admin_troca_proxima_carta_sem_mudar_tamanho_do_deck(client):
    game = _setup(client, 'deck_admin_replace', 'DECKREP')

    r = _edit(client, 'DECKREP', {
        'action': 'replace', 'position': 1, 'card_id': 'fenix'
    })
    assert r.status_code == 200
    data = r.get_json()
    assert data['success'] is True
    assert data['deck_count'] == 3
    assert data['card']['name'] == CARDS['fenix']['name']

    # draw_card usa pop(): a próxima é o último elemento da lista.
    assert [c['id'] for c in game.deck] == ['orc', 'elfo', 'fenix']
    assert game.deck[-1]['instance_id'] != 'i2'


def test_admin_insere_carta_como_proxima(client):
    game = _setup(client, 'deck_admin_insert', 'DECKINS')

    r = _edit(client, 'DECKINS', {
        'action': 'insert', 'position': 1, 'card_id': 'medusa'
    })
    assert r.status_code == 200
    assert r.get_json()['deck_count'] == 4
    assert game.deck[-1]['id'] == 'medusa'


def test_admin_reordena_e_remove_proximas_cartas(client):
    game = _setup(client, 'deck_admin_move', 'DECKMOV')

    r = _edit(client, 'DECKMOV', {'action': 'move', 'from': 1, 'to': 2})
    assert r.status_code == 200
    assert [c['id'] for c in game.deck] == ['orc', 'mago', 'elfo']

    r = _edit(client, 'DECKMOV', {'action': 'remove', 'position': 1})
    assert r.status_code == 200
    assert [c['id'] for c in game.deck] == ['orc', 'mago']


def test_edicao_do_deck_exige_admin(client):
    game = _setup(client, 'deck_regular_move', 'DECKAUTH')
    update_account('deck_regular_move', {'admin_level': 0})

    r = _edit(client, 'DECKAUTH', {
        'action': 'replace', 'position': 1, 'card_id': 'fenix'
    })
    assert r.status_code == 403
    assert r.get_json()['success'] is False
    assert [c['id'] for c in game.deck] == ['orc', 'elfo', 'mago']


def test_edicao_do_deck_rejeita_posicao_invalida(client):
    _setup(client, 'deck_admin_invalid', 'DECKBAD')

    r = _edit(client, 'DECKBAD', {
        'action': 'replace', 'position': 99, 'card_id': 'orc'
    })
    assert r.status_code == 400
    assert r.get_json()['success'] is False
