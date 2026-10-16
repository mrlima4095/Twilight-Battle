"""Testes do motor: jogadas inválidas não podem consumir cartas."""
import time

from twilight.game.engine import Game
from twilight.game import session as session_mod
from twilight.state import games


def _game():
    g = Game('TGAME1', 'alice')
    g.add_player('s1', 'alice')
    g.add_player('s2', 'bob')
    g.started = True
    g.current_turn = 0
    return g


def _creature(instance_id):
    return {
        'instance_id': instance_id,
        'id': 'dragao',
        'name': 'Dragão',
        'type': 'creature',
        'attack': 5,
        'life': 5,
    }


def test_play_card_occupied_position_keeps_card():
    """Jogada para posição ocupada falha SEM perder a carta da mão."""
    g = _game()
    alice = g.player_data['alice']
    alice['attack_bases'][0] = {'instance_id': 'x', 'id': 'x', 'type': 'creature', 'name': 'Ocupante'}
    alice['hand'] = [_creature('c1')]

    res = g.play_card('alice', 'c1', 'attack', 0)
    assert res['success'] is False
    assert any(c['instance_id'] == 'c1' for c in alice['hand']), 'carta foi perdida!'

    # Agora a posição está livre: jogada válida consome a carta
    alice['attack_bases'][0] = None
    res = g.play_card('alice', 'c1', 'attack', 0)
    assert res['success'] is True
    assert not any(c['instance_id'] == 'c1' for c in alice['hand'])
    assert alice['attack_bases'][0] is not None


def test_play_card_out_of_bounds_keeps_card():
    g = _game()
    alice = g.player_data['alice']
    alice['hand'] = [_creature('c1')]
    res = g.play_card('alice', 'c1', 'attack', 99)
    assert res['success'] is False
    assert any(c['instance_id'] == 'c1' for c in alice['hand'])


def test_perform_ritual_failed_keeps_card():
    """Ritual que falha as condições não pode consumir a carta."""
    g = _game()
    alice = g.player_data['alice']
    # sem Apofis/Mago Negro -> Ritual 157 sempre falha
    alice['hand'] = [{'instance_id': 'r1', 'id': 'ritual_157', 'type': 'ritual', 'name': 'Ritual 157'}]

    res = g.perform_ritual('alice', 'ritual_157', target_username='bob')
    assert res['success'] is False
    assert any(c['instance_id'] == 'r1' for c in alice['hand']), 'ritual foi perdido!'


def test_get_available_rituals_returns_list_not_none():
    """O bug era retornar None (sem `return`), derrubando o handler."""
    g = _game()
    result = g.get_available_rituals('alice')
    assert isinstance(result, list)


def test_reaper_closes_abandoned_lobby(monkeypatch):
    """Lobby sem nenhum socket humano há muito tempo deve ser removido."""
    monkeypatch.setattr(session_mod, 'ABANDONED_LOBBY_TTL_SECONDS', 3600)
    monkeypatch.setattr(session_mod, 'FINISHED_ROOM_TTL_SECONDS', 900)
    g = Game('ABAND-TEST', 'alice')
    g.created_at = time.time() - 999999
    g.empty_since = time.time() - 999999
    games['ABAND-TEST'] = g
    try:
        session_mod.cleanup_stale_games()
        assert 'ABAND-TEST' not in games
    finally:
        games.pop('ABAND-TEST', None)


def test_reaper_times_out_stuck_turn(monkeypatch):
    """Turno humano parado além do limite avança automaticamente."""
    monkeypatch.setattr(session_mod, 'TURN_TIMEOUT_SECONDS', 60)
    g = _game()
    g.last_action_at = time.time() - 999999
    games['TGAME1'] = g
    try:
        acted = session_mod.enforce_turn_timeout()
        assert any(a['player'] == 'alice' for a in acted)
        assert g.current_turn == 1
    finally:
        games.pop('TGAME1', None)
