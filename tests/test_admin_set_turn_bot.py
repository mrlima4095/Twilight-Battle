"""Turno forçado pelo admin precisa acionar bots e liberar suas ações."""

from twilight.auth.service import update_account
from twilight.game import ai
from twilight.game.engine import Game
from twilight.state import games


def _register_admin(client, username):
    r = client.post('/api/register', json={'username': username, 'password': 'pass1234'})
    assert r.get_json()['success'] is True, r.get_json()
    update_account(username, {'admin_level': 1})


def _game(game_id, host, bot_name='bot_1'):
    game = Game(game_id, host)
    game.add_player(f'sid-{host}', host)
    assert ai.add_bot(game, name=bot_name, difficulty='normal') is not None
    game.started = True
    games[game_id] = game
    return game


def test_set_turn_para_bot_agenda_jogada_e_reseta_acoes(client, monkeypatch):
    _register_admin(client, 'setturn_admin_bot')
    game = _game('SETBOT', 'setturn_human_bot')
    bot = 'bot_1'

    # Simula um bot que já gastou as ações do turno anterior.
    game.turn_actions_used[bot] = {'draw': 1, 'play': 1, 'attack': 1}
    game.player_data[bot]['attacked_this_turn'] = True
    game.player_data[bot]['free_swap_used'] = True
    game.last_action_at = 0

    calls = []
    monkeypatch.setattr(
        'twilight.game.ai.schedule_bot_turn',
        lambda game_id, delay=None: calls.append((game_id, delay)),
    )

    r = client.post(
        f'/api/admin/game/SETBOT/set-turn',
        json={'target_username': bot},
    )
    assert r.status_code == 200
    assert r.get_json()['current_turn'] == bot

    assert game.current_turn == 1
    assert calls == [('SETBOT', 0.8)]
    assert game.turn_actions_used[bot] == {}
    assert game.turn_extra_actions[bot] == {}
    assert game.player_data[bot]['attacked_this_turn'] is False
    assert game.player_data[bot]['free_swap_used'] is False
    assert game.last_action_at > 0


def test_set_turn_para_humano_nao_agenda_bot(client, monkeypatch):
    _register_admin(client, 'setturn_admin_human')
    game = _game('SETHUMAN', 'setturn_human_plain')

    calls = []
    monkeypatch.setattr(
        'twilight.game.ai.schedule_bot_turn',
        lambda game_id, delay=None: calls.append((game_id, delay)),
    )

    r = client.post(
        '/api/admin/game/SETHUMAN/set-turn',
        json={'target_username': 'setturn_human_plain'},
    )
    assert r.status_code == 200
    assert game.current_turn == 0
    assert calls == []


def test_set_turn_rejeita_jogador_morto(client, monkeypatch):
    _register_admin(client, 'setturn_admin_dead')
    game = _game('SETDEAD', 'setturn_human_dead')
    game.player_data['bot_1']['dead'] = True

    calls = []
    monkeypatch.setattr(
        'twilight.game.ai.schedule_bot_turn',
        lambda game_id, delay=None: calls.append((game_id, delay)),
    )

    r = client.post(
        '/api/admin/game/SETDEAD/set-turn',
        json={'target_username': 'bot_1'},
    )
    assert r.status_code == 400
    assert r.get_json()['success'] is False
    assert game.current_turn == 0
    assert calls == []
