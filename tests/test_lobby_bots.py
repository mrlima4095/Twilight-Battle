"""Bots no lobby: permissão do dono, limites, dificuldade e rematch."""
from twilight.game import ai
from twilight.game.engine import Game
from twilight.game.lobby import normalize_bot_difficulty
from twilight.state import games


def _user(app, username):
    client = app.test_client()
    r = client.post('/api/register', json={
        'username': username, 'password': 'pass1234',
    })
    assert r.get_json()['success'] is True
    return client


def _create_game(client, max_players=4):
    r = client.post('/api/create-game', json={'max_players': max_players})
    assert r.status_code == 200
    return r.get_json()['game_id']


def test_normalize_bot_difficulty_aliases():
    assert normalize_bot_difficulty('facil') == 'easy'
    assert normalize_bot_difficulty('DIFÍCIL') == 'hard'
    assert normalize_bot_difficulty('qualquer') == 'normal'
    assert normalize_bot_difficulty(None) == 'normal'


def test_fill_bots_is_host_only_and_respects_max_players(app):
    host = _user(app, 'host_bots_1')
    other = _user(app, 'outro_bots_1')
    game_id = _create_game(host, max_players=4)
    games[game_id].add_player('sid-host-1', 'host_bots_1')

    denied = other.post(f'/api/games/{game_id}/bots', json={
        'action': 'fill', 'difficulty': 'easy', 'count': 1,
    })
    assert denied.status_code == 401
    assert denied.get_json()['success'] is False

    r = host.post(f'/api/games/{game_id}/bots', json={
        'action': 'fill', 'difficulty': 'hard', 'count': 99,
    })
    data = r.get_json()
    assert r.status_code == 200
    assert data['success'] is True
    assert data['players_count'] == 4
    assert data['bots_count'] == 3  # última vaga reservada para o dono
    assert data['bot_difficulty'] == 'hard'
    assert len(data['added']) == 3

    game = games[game_id]
    bots = [p for p in game.players if game.player_data[p].get('is_bot')]
    assert len(bots) == 3
    assert all(game.player_data[p]['bot_difficulty'] == 'hard' for p in bots)
    # sids dos bots mantêm o prefixo esperado pelo reaper
    assert all(
        sid.startswith('bot:')
        for sid, uname in game.socket_to_username.items()
        if uname in bots
    )


def test_game_page_exposes_host_bot_controls(app):
    host = _user(app, 'host_bots_page')
    game_id = _create_game(host)
    html = host.get(f'/game/{game_id}').get_data(as_text=True)
    for marker in (
        'id="host-bot-controls"',
        'id="bot-difficulty-select"',
        'id="add-bots-btn"',
        'id="remove-bots-btn"',
        'socket.on(\'lobby_updated\'',
    ):
        assert marker in html


def test_fill_reserves_last_slot_for_host(app):
    host = _user(app, 'host_bots_reserva')
    game_id = _create_game(host, max_players=4)

    r = host.post(f'/api/games/{game_id}/bots', json={
        'action': 'fill', 'difficulty': 'easy', 'count': 99,
    })
    data = r.get_json()
    assert data['success'] is True
    assert data['players_count'] == 3
    assert data['bots_count'] == 3
    assert games[game_id].add_player('sid-host-reserva', 'host_bots_reserva') is True


def test_change_difficulty_and_remove_bots(app):
    host = _user(app, 'host_bots_2')
    game_id = _create_game(host, max_players=5)
    games[game_id].add_player('sid-host-2', 'host_bots_2')

    r = host.post(f'/api/games/{game_id}/bots', json={
        'action': 'fill', 'difficulty': 'normal', 'count': 2,
    })
    assert r.get_json()['players_count'] == 3

    r = host.post(f'/api/games/{game_id}/bots', json={
        'action': 'difficulty', 'difficulty': 'difícil',
    })
    data = r.get_json()
    assert data['success'] is True
    assert data['bot_difficulty'] == 'hard'
    assert games[game_id].bot_difficulty == 'hard'
    assert all(
        games[game_id].player_data[p]['bot_difficulty'] == 'hard'
        for p in games[game_id].players
        if games[game_id].player_data[p].get('is_bot')
    )

    r = host.post(f'/api/games/{game_id}/bots', json={'action': 'remove'})
    data = r.get_json()
    assert data['success'] is True
    assert data['players_count'] == 1  # o dono permanece
    assert len(data['removed']) == 2
    assert games[game_id].players == ['host_bots_2']


def test_start_with_bots_and_rematch_preserves_difficulty(app, monkeypatch):
    host = _user(app, 'host_bots_3')
    game_id = _create_game(host, max_players=3)
    games[game_id].add_player('sid-host-3', 'host_bots_3')
    monkeypatch.setattr('twilight.routes.games.schedule_bot_turn', lambda *a, **k: None)

    r = host.post(f'/api/games/{game_id}/bots', json={
        'action': 'fill', 'difficulty': 'easy', 'count': 2,
    })
    assert r.get_json()['success'] is True

    r = host.post(f'/start-game/{game_id}', method='POST')
    assert r.get_json()['success'] is True
    game = games[game_id]
    assert game.started is True

    game.reset_to_lobby(last_winner=game.players[0])
    assert game.started is False
    assert len(game.players) == 3
    for player in game.players:
        if player == 'host_bots_3':
            continue
        assert game.player_data[player]['is_bot'] is True
        assert game.player_data[player]['bot_difficulty'] == 'easy'


def test_bot_management_requires_lobby(app, monkeypatch):
    host = _user(app, 'host_bots_4')
    game_id = _create_game(host)
    monkeypatch.setattr('twilight.routes.games.schedule_bot_turn', lambda *a, **k: None)
    games[game_id].add_player('sid-host', 'host_bots_4')
    ai.add_bot(games[game_id], difficulty='normal')
    started = host.post(f'/start-game/{game_id}')
    assert started.get_json()['success'] is True, started.get_json()

    r = host.post(f'/api/games/{game_id}/bots', json={'action': 'fill', 'count': 1})
    assert r.status_code == 400
    assert 'antes' in r.get_json()['message']


def test_difficulty_changes_plan_quality(monkeypatch):
    game = Game('TPLANBOTS', 'humano')
    game.add_player('sid-human', 'humano')
    assert ai.add_bot(game, difficulty='hard') is not None
    assert ai.add_bot(game, difficulty='easy') is not None
    game.started = True
    game.first_round = False
    game.attacks_blocked = False

    hard = game.players[1]
    easy = game.players[2]
    creature = {
        'instance_id': 'c-atk', 'id': 'dragao', 'name': 'Dragão',
        'type': 'creature', 'attack': 5, 'life': 5,
    }
    game.player_data[hard]['attack_bases'][0] = creature
    game.player_data[easy]['attack_bases'][0] = dict(creature, instance_id='c-atk-2')

    monkeypatch.setattr(ai.random, 'random', lambda: 0.0)
    hard_plan = ai.plan_bot_actions(game, hard, 'hard')
    assert {'action': 'draw'} in hard_plan
    assert any(a['action'] == 'attack' for a in hard_plan)
    assert hard_plan[-1]['action'] == 'end_turn'

    monkeypatch.setattr(ai.random, 'random', lambda: 0.99)
    easy_plan = ai.plan_bot_actions(game, easy, 'easy')
    assert [a['action'] for a in easy_plan] == ['end_turn']
