"""Testes das regras de equipamento em criaturas."""

from apps.bot import Strategy
from twilight.cards.definitions import CARDS
from twilight.game.engine import Game


def _game():
    g = Game('TEQ', 'alice')
    g.add_player('s1', 'alice')
    g.add_player('s2', 'bob')
    g.started = True
    g.first_round = False
    g.attacks_blocked = False
    g.time_of_day = 'night'
    g.time_cycle = 1
    g.turn_actions_used = {'alice': {}, 'bob': {}}
    g.player_data['alice']['hand'] = []
    return g


def _card(definition_id, instance_id):
    card = dict(CARDS[definition_id])
    card['instance_id'] = instance_id
    card.setdefault('equipped_items', [])
    return card


def _creature(definition_id='elfo', instance_id='c1'):
    return _card(definition_id, instance_id)


def _equip(g, item_id, creature, definition_id):
    item = _card(definition_id, item_id)
    g.player_data['alice']['hand'].append(item)
    g.player_data['alice']['attack_bases'][0] = creature
    return g.equip_item_to_creature('alice', item_id, creature['instance_id'])


def test_nao_permite_dois_capacetes():
    g = _game()
    creature = _creature()
    assert _equip(g, 'h1', creature, 'capacete_trevas')['success'] is True

    result = _equip(g, 'h2', creature, 'capacete_sentinela')

    assert result['success'] is False
    assert 'capacete' in result['message'].lower()
    assert len(creature['equipped_items']) == 1


def test_nao_permite_duplicar_armaduras_no_mesmo_slot_mas_aceita_slots_diferentes():
    g = _game()
    creature = _creature()
    assert _equip(g, 'a1', creature, 'peitoral_ferro')['success'] is True

    duplicate = _equip(g, 'a2', creature, 'manto_eclipse')

    assert duplicate['success'] is False
    assert 'peitoral' in duplicate['message'].lower()
    assert _equip(g, 'b1', creature, 'botas_guerra')['success'] is True
    assert _equip(g, 'p1', creature, 'calcas_marcha')['success'] is True
    assert len(creature['equipped_items']) == 3


def test_nao_permite_duplicar_armas():
    g = _game()
    creature = _creature()
    assert _equip(g, 'w1', creature, 'espada_ferro')['success'] is True

    result = _equip(g, 'w2', creature, 'katana')

    assert result['success'] is False
    assert 'arma' in result['message'].lower()


def test_bestas_nao_equipam_itens():
    for card_id in ('dragao', 'fenix', 'leviatan', 'apofis', 'medusa'):
        g = _game()
        beast = _creature(card_id)
        result = _equip(g, 'w1', beast, 'espada_ferro')

        assert result['success'] is False, card_id
        assert 'bestial' in result['message'].lower()
        assert beast.get('equipped_items') == []


def test_lobisomem_pode_usar_apenas_a_adaga_do_crepusculo():
    g = _game()
    werewolf = _creature('lobisomem_crepusculo')

    assert _equip(g, 'a1', werewolf, 'peitoral_ferro')['success'] is False
    assert _equip(g, 'd1', werewolf, 'adaga_crepusculo')['success'] is True


def test_bot_respeita_as_mesmas_restricoes():
    bot = Strategy('hard')
    elfo = _creature()
    beast = _creature('dragao')
    sword = _card('espada_ferro', 'w1')

    assert bot._can_equip(sword, beast) is False
    assert bot._can_equip(sword, elfo) is True
    assert bot._can_equip(sword, {**elfo, 'equipped_items': [sword]}) is False

    helmet = _card('capacete_trevas', 'h1')
    helmet2 = _card('capacete_sentinela', 'h2')
    assert bot._can_equip(helmet2, {**elfo, 'equipped_items': [helmet]}) is False
