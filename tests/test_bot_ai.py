"""IA dos bots: ataques, equipamentos e habilidades ativas das criaturas."""
from apps.bot import Strategy
from twilight.game import ai
from twilight.game.engine import Game
from twilight.state import games


def _game(game_id, difficulties=('hard', 'hard')):
    game = Game(game_id, 'humano')
    game.add_player('sid-human', 'humano')
    for index, difficulty in enumerate(difficulties, 1):
        assert ai.add_bot(game, name=f'bot_{index}', difficulty=difficulty)
    game.started = True
    game.first_round = False
    game.attacks_blocked = False
    return game


def _creature(instance_id, card_id='elfo', attack=100):
    return {
        'instance_id': instance_id,
        'id': card_id,
        'name': 'Elfo',
        'type': 'creature',
        'attack': attack,
        'life': 100,
    }


def _arm_all(game):
    for username in game.players:
        game.player_data[username]['attack_bases'][0] = _creature(f'atk-{username}')


def _attack_step(plan):
    return next(step for step in plan if step['action'] == 'attack')


def test_hard_bot_ataca_outro_bot_quando_empatado(monkeypatch):
    game = _game('BOTAI-RIVAL')
    _arm_all(game)
    monkeypatch.setattr(ai.random, 'random', lambda: 0.0)

    plan = ai.plan_bot_actions(game, 'bot_1', 'hard')

    assert _attack_step(plan)['params']['target_id'] == 'bot_2'


def test_hard_bot_ainda_foca_humano_quase_morto(monkeypatch):
    game = _game('BOTAI-FOCUS')
    _arm_all(game)
    game.player_data['humano']['life'] = 100
    monkeypatch.setattr(ai.random, 'random', lambda: 0.0)

    plan = ai.plan_bot_actions(game, 'bot_1', 'hard')

    assert _attack_step(plan)['params']['target_id'] == 'humano'


def test_hard_bot_equipa_arma_e_aumenta_ataque(monkeypatch):
    game = _game('BOTAI-EQUIP')
    bot = 'bot_1'
    player = game.player_data[bot]
    player['attack_bases'][0] = _creature('atk-equip')
    player['hand'] = [{
        'instance_id': 'item-sword',
        'id': 'espada_ferro',
        'name': 'Espada de Ferro',
        'type': 'weapon',
        'attack': 256,
    }]
    monkeypatch.setattr(ai.random, 'random', lambda: 0.0)

    plan = ai.plan_bot_actions(game, bot, 'hard')
    equip_steps = [step for step in plan if step['action'] == 'equip_item']
    assert len(equip_steps) == 1

    ok, result, _ = ai._run_one_action(game, bot, equip_steps[0])
    assert ok is True, result
    assert player['attack_bases'][0]['attack'] == 356
    assert player['hand'] == []


def test_turno_do_bot_executa_ataque_contra_outro_bot(monkeypatch):
    game = _game('BOTAI-TURN')
    _arm_all(game)
    games[game.game_id] = game

    monkeypatch.setattr(ai.socketio, 'sleep', lambda *args, **kwargs: None)
    monkeypatch.setattr(ai.socketio, 'emit', lambda *args, **kwargs: None)
    monkeypatch.setattr(ai, 'schedule_bot_turn', lambda *args, **kwargs: None)
    monkeypatch.setattr(ai, '_persist_turn', lambda *args, **kwargs: None)
    monkeypatch.setattr(ai.random, 'random', lambda: 0.0)

    original_attack = Game.attack
    attacks = []

    def spy_attack(self, username, target_username):
        result = original_attack(self, username, target_username)
        attacks.append((username, target_username, result.get('success')))
        return result

    monkeypatch.setattr(Game, 'attack', spy_attack)
    game.current_turn = game.players.index('bot_1')

    try:
        ai.run_bot_turn(game.game_id)
    finally:
        games.pop(game.game_id, None)

    assert ('bot_1', 'bot_2', True) in attacks


def test_bot_cliente_dificil_tambem_mira_outros_bots(monkeypatch):
    strategy = Strategy('hard')
    players = {
        'humano': {'life': 1200, 'attack_bases': [], 'defense_bases': []},
        'bot_2': {
            'life': 1200, 'is_bot': True,
            'attack_bases': [], 'defense_bases': [],
        },
    }
    monkeypatch.setattr('apps.bot.random.random', lambda: 0.0)

    assert strategy._pick_attack_target(
        list(players.items()), 100, set(), 'bot_1'
    ) == 'bot_2'

    players['humano']['life'] = 100
    assert strategy._pick_attack_target(
        list(players.items()), 100, set(), 'bot_1'
    ) == 'humano'


def test_bot_dificil_troca_criatura_para_o_ataque(monkeypatch):
    game = _game('BOTAI-SWAP', ('hard',))
    bot = 'bot_1'
    game.current_turn = game.players.index(bot)
    player = game.player_data[bot]
    player['attack_bases'][0] = _creature('atk-fraco', attack=10)
    player['defense_bases'][0] = _creature('def-forte', attack=300)
    monkeypatch.setattr(ai.random, 'random', lambda: 0.0)

    plan = ai.plan_bot_actions(game, bot, 'hard')
    swap = next(step for step in plan if step['action'] == 'swap_positions')
    assert swap['params']['pos1_type'] == 'defense'
    assert swap['params']['pos1_index'] == 0
    assert swap['params']['pos2_type'] == 'attack'

    target_index = swap['params']['pos2_index']
    ok, _, _ = ai._run_one_action(game, bot, swap)
    assert ok is True
    assert player['attack_bases'][target_index]['instance_id'] == 'def-forte'


def test_bot_dificil_usa_fenix_quando_a_noite_ajuda(monkeypatch):
    game = _game('BOTAI-FENIX', ('hard',))
    bot = 'bot_1'
    game.current_turn = game.players.index(bot)
    game.time_of_day = 'day'
    player = game.player_data[bot]
    player['attack_bases'][0] = _creature('fenix', card_id='fenix')
    lobo = _creature('lobo', card_id='lobisomem_crepusculo')
    lobo.update({'werewolf': True, 'day_attack': 100, 'night_attack': 600})
    player['attack_bases'][1] = lobo
    human = game.player_data['humano']
    human['attack_bases'][0] = {
        **_creature('vampiro', card_id='vampiro_tayler'),
        'dies_daylight': True,
    }
    monkeypatch.setattr(ai.random, 'random', lambda: 0.0)

    plan = ai.plan_bot_actions(game, bot, 'hard')
    toggle = next(step for step in plan if step['action'] == 'toggle_time')

    ok, _, _ = ai._run_one_action(game, bot, toggle)
    assert ok is True
    assert game.time_of_day == 'night'


def test_bot_dificil_usa_feitico_de_cura_com_mago(monkeypatch):
    game = _game('BOTAI-SPELL', ('hard',))
    bot = 'bot_1'
    game.current_turn = game.players.index(bot)
    player = game.player_data[bot]
    player['attack_bases'][0] = _creature('mago-campo', card_id='mago')
    player['life'] = 200
    player['hand'] = [{
        'instance_id': 'sp-cura', 'id': 'feitico_cura',
        'name': 'Cura', 'type': 'spell',
    }]
    monkeypatch.setattr(ai.random, 'random', lambda: 0.0)

    plan = ai.plan_bot_actions(game, bot, 'hard')
    spell = next(step for step in plan if step['action'] == 'cast_spell')
    assert spell['params']['spell_id'] == 'sp-cura'

    ok, _, _ = ai._run_one_action(game, bot, spell)
    assert ok is True
    assert player['life'] > 200


def test_bot_cliente_tambem_sabe_usar_fenix():
    strategy = Strategy('hard')
    me_data = {
        'attack_bases': [
            _creature('fenix', card_id='fenix'),
            {**_creature('lobo', card_id='lobisomem_crepusculo'),
             'werewolf': True, 'day_attack': 100, 'night_attack': 600},
        ],
        'defense_bases': [],
        'equipment': {},
    }
    enemies = {
        'humano': {
            'attack_bases': [{**_creature('vampiro'), 'dies_daylight': True}],
            'defense_bases': [],
            'equipment': {},
        }
    }
    state = {'time_of_day': 'day', 'modifiers': []}

    step = strategy._pick_toggle_time(state, 'bot', me_data, list(enemies.items()))
    assert step == {'action': 'toggle_time', 'params': {}, 'reason': 'fenix-toggle'}


def _rune(index):
    return {'instance_id': f'runa-{index}', 'id': 'runa', 'name': 'Runa', 'type': 'rune'}


def _talisman(card_id='talisma_imortalidade'):
    return {'instance_id': f'tal-{card_id}', 'id': card_id, 'name': 'Talismã', 'type': 'talisman'}


def test_bot_dificil_revive_carta_com_quatro_runas():
    game = _game('BOTAI-REVIVE', ('hard',))
    bot = 'bot_1'
    game.current_turn = game.players.index(bot)
    player = game.player_data[bot]
    player['hand'] = [_rune(i) for i in range(4)]
    game.graveyard = [_creature('mago-volta', card_id='mago', attack=500)]

    step = ai._plan_revive(game, bot, player, player['hand'])
    assert step == {'action': 'revive', 'params': {'card_id': 'mago-volta'}}

    ok, _, _ = ai._run_one_action(game, bot, step)
    assert ok is True
    assert player['hand'][0]['instance_id'] == 'mago-volta'
    assert all(card.get('id') == 'runa' for card in game.graveyard)


def test_bot_dificil_realiza_ritual_157_e_rouba_talismas():
    game = _game('BOTAI-RITUAL', ('hard',))
    bot = 'bot_1'
    game.current_turn = game.players.index(bot)
    player = game.player_data[bot]
    player['attack_bases'] = [
        _creature('apofis', card_id='apofis'),
        _creature('mago-negro', card_id='mago_negro'),
    ] + [_creature(f'zumbi-{i}', card_id='zumbi') for i in range(1)]
    player['defense_bases'] = [
        _creature(f'zumbi-{i}', card_id='zumbi') for i in range(1, 6)
    ] + [_creature(f'elfo-{i}') for i in range(2)]
    game.player_data['humano']['talismans'] = [_talisman()]

    step = ai._plan_ritual(game, bot, player, player['hand'])
    assert step == {
        'action': 'ritual',
        'params': {'ritual_id': 'ritual_157', 'target_player_id': 'humano'},
    }

    ok, _, _ = ai._run_one_action(game, bot, step)
    assert ok is True
    assert game.player_data['humano']['talismans'] == []
    assert len(player['talismans']) == 1


def test_bot_dificil_usa_oraculo_contra_talisman_alvo():
    game = _game('BOTAI-ORACLE', ('hard',))
    bot = 'bot_1'
    game.current_turn = game.players.index(bot)
    player = game.player_data[bot]
    player['defense_bases'][0] = _creature('elfo-defesa')
    player['hand'] = [{
        'instance_id': 'oraculo', 'id': 'oraculo_imortalidade',
        'name': 'Oráculo', 'type': 'oracle',
    }]
    talisman = _talisman()
    game.player_data['humano']['hand'] = [talisman]

    step = ai._plan_oracle(game, bot, player, player['hand'])
    assert step == {'action': 'oracle', 'params': {'target_id': 'humano'}}

    ok, _, _ = ai._run_one_action(game, bot, step)
    assert ok is True
    assert talisman['oracle_blocked'] is True
    assert player['hand'] == []


def test_bot_dificil_revela_armadilha_disfarcada():
    game = _game('BOTAI-FLIP', ('hard',))
    bot = 'bot_1'
    game.current_turn = game.players.index(bot)
    player = game.player_data[bot]
    trap = {
        'instance_id': 'poco', 'id': 'armadilha_poco', 'name': 'Poço',
        'type': 'trap', 'is_disguised': True,
        'disguise': {'name': 'Elfo', 'id': 'elfo'},
    }
    player['defense_bases'][0] = trap

    step = ai._plan_flip(game, bot, player)
    assert step == {
        'action': 'flip_card',
        'params': {'position_type': 'defense', 'position_index': 0},
    }

    ok, _, _ = ai._run_one_action(game, bot, step)
    assert ok is True
    assert trap.get('is_disguised') is None
    assert trap.get('disguise') is None


def test_bot_cliente_tambem_planeja_ritual_oraculo_e_revive():
    strategy = Strategy('hard')
    me_data = {
        'attack_bases': [
            _creature('apofis', card_id='apofis'),
            _creature('mago-negro', card_id='mago_negro'),
        ] + [_creature(f'zumbi-{i}', card_id='zumbi') for i in range(1)],
        'defense_bases': [
            _creature(f'zumbi-{i}', card_id='zumbi') for i in range(1, 6)
        ] + [_creature(f'elfo-{i}') for i in range(2)],
    }
    enemies = [('humano', {'talisman_count': 2, 'life': 500})]
    hand = [_rune(i) for i in range(4)] + [{
        'instance_id': 'oraculo', 'id': 'oraculo_imortalidade',
        'name': 'Oráculo', 'type': 'oracle',
    }]

    assert strategy._pick_ritual(me_data, hand, enemies)['params'] == {
        'ritual_id': 'ritual_157', 'target_player_id': 'humano'
    }
    assert strategy._pick_oracle(me_data, hand, enemies)['params'] == {
        'target_id': 'humano'
    }
    assert strategy._pick_revive(
        {'modifiers': [], 'graveyard': [_creature('volta', attack=900)]}, hand
    )['params'] == {'card_id': 'volta'}
