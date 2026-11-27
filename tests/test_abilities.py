"""Testes das habilidades de cartas aplicadas no motor."""

from apps.bot import card_score
from twilight.cards.definitions import ABILITIES, CARDS
from twilight.game.engine import Game


def _game():
    g = Game('TABIL', 'alice')
    g.add_player('s1', 'alice')
    g.add_player('s2', 'bob')
    g.started = True
    g.current_turn = 0
    g.first_round = False
    g.attacks_blocked = False
    g.time_of_day = 'night'
    g.time_cycle = 1
    g.turn_actions_used = {'alice': {}, 'bob': {}}
    # Mão aleatória pode conter Talismã do Guerreiro (+1024) e mudar o resultado
    # dos testes de dano; aqui queremos só as cartas montadas explicitamente.
    g.player_data['alice']['hand'] = []
    g.player_data['bob']['hand'] = []
    g.player_data['bob']['life'] = 5000
    return g


def _card(instance_id, card_id, attack=0, life=1, **extra):
    card = {
        'instance_id': instance_id,
        'id': card_id,
        'name': card_id,
        'type': 'creature',
        'attack': attack,
        'life': life,
    }
    card.update(extra)
    return card


def _reset_turn(g, username, turn_index):
    g.current_turn = turn_index
    g.turn_actions_used[username] = {}


def test_zumbi_morto_por_ataque_volta_para_mao_e_por_sol_vai_ao_cemiterio():
    g = _game()
    g.player_data['alice']['attack_bases'][0] = _card('atk', 'orc', attack=1000, life=512)
    zumbi = _card('z1', 'zumbi', attack=25, life=1, dies_daylight=True)
    g.player_data['bob']['defense_bases'][0] = zumbi

    result = g.attack('alice', 'bob')

    assert result['success'] is True
    assert zumbi in g.player_data['bob']['hand']
    assert zumbi not in g.graveyard
    assert g.player_data['bob']['defense_bases'][0] is None

    # Luz do sol: vai para o cemitério, não para a mão
    novo_zumbi = _card('z2', 'zumbi', attack=25, life=100, dies_daylight=True)
    g.player_data['bob']['attack_bases'][0] = novo_zumbi
    g.time_of_day = 'day'
    g.apply_day_effects(force=True)

    assert novo_zumbi in g.graveyard
    assert novo_zumbi not in g.player_data['bob']['hand']
    assert g.player_data['bob']['attack_bases'][0] is None


def test_ninfa_converte_dano_excedente_em_cura_ate_vida_padrao():
    g = _game()
    g.player_data['alice']['attack_bases'][0] = _card('atk', 'orc', attack=1000, life=512)

    ninfa = _card('n1', 'ninfa', attack=30, life=100)
    defesa = _card('d1', 'centauro', attack=70, life=200)
    ataque = _card('a1', 'centauro', attack=70, life=300)
    g.player_data['bob']['defense_bases'][0] = ninfa
    g.player_data['bob']['defense_bases'][1] = defesa
    g.player_data['bob']['attack_bases'][0] = ataque

    result = g.attack('alice', 'bob')

    assert result['success'] is True
    assert ninfa not in g.player_data['bob']['defense_bases']
    assert defesa['life'] == 512
    assert ataque['life'] == 512
    assert result['damage_to_player'] == 0
    assert len(result['cards_healed']) == 2


def test_dragao_queima_todas_as_cartas_por_dois_turnos():
    g = _game()
    g.player_data['alice']['attack_bases'][0] = _card('dr', 'dragao', attack=100, life=1500)
    defesa = _card('d1', 'centauro', attack=70, life=512)
    ataque = _card('a1', 'orc', attack=60, life=512)
    g.player_data['bob']['defense_bases'][0] = defesa
    g.player_data['bob']['attack_bases'][0] = ataque

    result = g.attack('alice', 'bob')

    assert result['success'] is True
    assert any(e.get('type') == 'dragon_burn' for e in result['creature_effects'])
    for card in (defesa, ataque):
        burn = next(e for e in card['effects'] if e['type'] == 'burn')
        assert burn['turns_remaining'] == 2
        assert burn['damage'] == 50

    g.next_turn()
    assert defesa['life'] == 362
    assert ataque['life'] == 462

    g.next_turn()
    assert defesa['life'] == 312
    assert ataque['life'] == 412
    assert not any(e['type'] == 'burn' for e in defesa['effects'])
    assert not any(e['type'] == 'burn' for e in ataque['effects'])


def test_medusa_petrifica_ataque_por_um_turno_com_cota_de_dois_usos():
    g = _game()
    medusa = _card('m1', 'medusa', attack=10, life=1024)
    g.player_data['alice']['attack_bases'][0] = medusa
    orc = _card('o1', 'orc', attack=60, life=512)
    centauro = _card('c1', 'centauro', attack=70, life=512)
    g.player_data['bob']['attack_bases'][0] = orc
    g.player_data['bob']['attack_bases'][1] = centauro

    result = g.attack('alice', 'bob')

    assert result['success'] is True
    assert orc['petrified'] is True
    assert centauro['petrified'] is True
    assert medusa['medusa_petrify_uses'] == 1

    _reset_turn(g, 'bob', 1)
    blocked = g.attack('bob', 'alice')
    assert blocked['success'] is False
    assert 'criaturas em posição de ataque' in blocked['message']

    g.next_turn()  # fim do turno do bob: limpa a petrificação
    assert 'petrified' not in orc
    assert 'petrified' not in centauro

    # Terceiro ataque da Medusa não consome mais do que os 2 usos
    medusa['medusa_petrify_uses'] = 0
    _reset_turn(g, 'alice', 0)
    result = g.attack('alice', 'bob')
    assert result['success'] is True
    assert medusa['medusa_petrify_uses'] == 0
    assert 'petrified' not in orc


def test_reviver_medusa_reseta_cota():
    g = _game()
    medusa = _card('m2', 'medusa', attack=512, life=1024, medusa_petrify_uses=0)
    g.graveyard.append(medusa)
    g.player_data['bob']['hand'] = [
        _card(f'r{i}', 'runa', attack=0, life=0) | {'type': 'rune'}
        for i in range(4)
    ]

    result = g.revive_from_graveyard('bob', 'm2')

    assert result['success'] is True
    assert medusa in g.player_data['bob']['hand']
    assert medusa['medusa_petrify_uses'] == 2


def test_fenix_morta_deixa_ovo_e_renasce_em_dez_turnos_com_metade_da_vida():
    g = _game()
    g.player_data['alice']['attack_bases'][0] = _card('atk', 'orc', attack=1000, life=512)
    fenix = _card('f1', 'fenix', attack=1500, life=1)
    g.player_data['bob']['defense_bases'][0] = fenix

    result = g.attack('alice', 'bob')

    assert result['success'] is True
    assert fenix in g.graveyard
    assert len(g.player_data['bob']['inventory']) == 1
    egg = g.player_data['bob']['inventory'][0]
    assert egg['id'] == 'ovo_fenix'
    assert egg['turns_remaining'] == 10
    assert fenix['phoenix_rebirth_used'] is True

    for _ in range(10):
        g.next_turn()

    assert fenix not in g.graveyard
    assert fenix in g.player_data['bob']['hand']
    assert fenix['life'] == 2500
    assert fenix['phoenix_reborn'] is True
    assert g.player_data['bob']['inventory'] == []


def test_feitico_comunista_destri_ovo_e_fenix_nao_volta():
    g = _game()
    fenix = _card('f2', 'fenix', attack=1500, life=1, phoenix_rebirth_used=True)
    g.graveyard.append(fenix)
    g.player_data['bob']['inventory'].append({
        'id': 'ovo_fenix',
        'name': '🥚 Ovo de Fênix',
        'turns_remaining': 10,
        'phoenix_instance_id': 'f2',
    })

    result = g.apply_spell_effect(
        {'id': 'feitico_comunista', 'type': 'spell', 'name': 'Comunismo'},
        'alice',
    )

    assert result['type'] == 'reset_hands'
    assert result['phoenix_eggs_lost'] == ['bob']
    assert g.player_data['bob']['inventory'] == []
    assert fenix['phoenix_egg_lost'] is True

    for _ in range(12):
        g.next_turn()

    assert fenix in g.graveyard
    assert fenix not in g.player_data['bob']['hand']


def test_definitions_e_bots_conhecem_as_habilidades():
    esperado = {
        'zumbi': 'undead_return',
        'ninfa': 'ninfa_sacrifice',
        'dragao': 'dragon_burn',
        'medusa': 'medusa_petrify',
        'fenix': 'phoenix_rebirth',
    }
    for card_id, ability in esperado.items():
        carta = CARDS[card_id]
        assert carta['ability'] == ability
        assert carta['ability_name'] == ABILITIES[ability]['name']
        assert carta['trigger'] == ABILITIES[ability]['trigger']
        assert carta['ability_text'] == ABILITIES[ability]['text']

    generica = card_score({
        'id': 'generica', 'type': 'creature', 'attack': 512, 'life': 1024,
    })
    assert card_score(CARDS['medusa']) > generica
    assert card_score(CARDS['dragao']) > generica
