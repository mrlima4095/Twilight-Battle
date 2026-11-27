"""Testes para desequipar itens das cartas em campo."""

from twilight.cards.definitions import CARDS
from twilight.game.engine import Game


def _game():
    g = Game('TUNEQ', 'alice')
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


def _creature(instance_id='c1'):
    return {
        'instance_id': instance_id,
        'id': 'elfo',
        'name': 'Elfo',
        'type': 'creature',
        'attack': 50,
        'life': 512,
        'equipped_items': [],
    }


def _item(definition_id, instance_id):
    item = dict(CARDS[definition_id])
    item['instance_id'] = instance_id
    return item


def test_desequipar_arma_devolve_item_e_remove_bonus():
    g = _game()
    creature = _creature()
    sword = _item('espada_ferro', 'w1')
    atk_bonus = int(sword['attack'])
    g.player_data['alice']['attack_bases'][0] = creature
    g.player_data['alice']['hand'] = [sword]

    assert g.equip_item_to_creature('alice', 'w1', 'c1')['success'] is True
    assert creature['attack'] == 50 + atk_bonus

    result = g.unequip_item_from_creature('alice', 'w1', 'c1')

    assert result['success'] is True
    assert creature['attack'] == 50
    assert creature.get('equipped_items') is None
    assert sword in g.player_data['alice']['hand']


def test_desequipar_armadura_intacta_devolve_item_e_remove_vida():
    g = _game()
    creature = _creature()
    armor = _item('peitoral_ferro', 'a1')
    protection = int(armor['protection'])
    g.player_data['alice']['defense_bases'][0] = creature
    g.player_data['alice']['hand'] = [armor]

    assert g.equip_item_to_creature('alice', 'a1', 'c1')['success'] is True
    assert creature['life'] == 512 + protection
    assert armor['durability'] == protection

    result = g.unequip_item_from_creature('alice', 'a1', 'c1')

    assert result['success'] is True
    assert creature['life'] == 512
    assert armor in g.player_data['alice']['hand']
    assert armor['durability'] == armor['max_durability']


def test_armadura_que_absorveu_dano_nao_pode_ser_desequipada():
    g = _game()
    creature = _creature()
    armor = _item('peitoral_ferro', 'a1')
    protection = int(armor['protection'])
    g.player_data['alice']['attack_bases'][0] = {
        'instance_id': 'atk',
        'id': 'orc',
        'name': 'Orc',
        'type': 'creature',
        'attack': 60,
        'life': 512,
    }
    creature['life'] = 100 + protection
    g.player_data['bob']['defense_bases'][0] = creature
    g.player_data['bob']['hand'] = [armor]
    assert g.equip_item_to_creature('bob', 'a1', 'c1')['success'] is True

    attack = g.attack('alice', 'bob')

    assert attack['success'] is True
    assert armor['durability'] == protection - 60

    result = g.unequip_item_from_creature('bob', 'a1', 'c1')

    assert result['success'] is False
    assert 'absorveu dano' in result['message']
    assert creature['equipped_items'] == [armor]
    assert armor not in g.player_data['bob']['hand']
