"""Testes das armadilhas que interagem com as bases de ataque."""

from twilight.cards.definitions import CARDS
from twilight.game.engine import Game


def _game():
    g = Game('TTRAP', 'alice')
    g.add_player('s1', 'alice')
    g.add_player('s2', 'bob')
    g.started = True
    g.first_round = False
    g.attacks_blocked = False
    g.time_of_day = 'night'
    g.time_cycle = 1
    g.turn_actions_used = {'alice': {}, 'bob': {}}
    g.player_data['alice']['hand'] = []
    g.player_data['bob']['hand'] = []
    g.player_data['bob']['life'] = 5000
    return g


def _creature(instance_id, attack):
    card = dict(CARDS['orc'])
    card.update(instance_id=instance_id, attack=attack, life=512)
    return card


def _trap():
    return {
        'instance_id': 'trap1',
        'id': 'armadilha_171',
        'name': 'Armadilha 171',
        'type': 'trap',
        'original_trap_id': 'armadilha_171',
        'original_trap_name': 'Armadilha 171',
    }


def test_armadilha_171_rouba_carta_sem_reduzir_slots_de_ataque():
    g = _game()
    weak = _creature('weak', 10)
    strongest = _creature('strong', 500)
    middle = _creature('middle', 100)
    g.player_data['alice']['attack_bases'] = [weak, strongest, middle]
    g.player_data['bob']['defense_bases'][0] = _trap()

    result = g.attack('alice', 'bob')

    assert result['success'] is True
    assert any(e.get('type') == 'steal_card' for e in result['trap_effects'])

    # O slot da carta roubada fica vazio, mas a base continua com 3 posições.
    assert len(g.player_data['alice']['attack_bases']) == 3
    assert g.player_data['alice']['attack_bases'][0] is weak
    assert g.player_data['alice']['attack_bases'][1] is None
    assert g.player_data['alice']['attack_bases'][2] is middle

    assert strongest in g.player_data['bob']['hand']
    assert strongest not in g.player_data['alice']['attack_bases']
