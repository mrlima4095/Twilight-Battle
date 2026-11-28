"""Partidas voltam depois de restart/redeploy (snapshot + restore)."""

from collections import deque

from twilight.game.chat import add_chat_message
from twilight.game.engine import Game
from twilight.game.persistence import (
    remove_game_snapshot,
    restore_games,
    snapshot_game,
)
from twilight.game.session import close_game
from twilight.state import chat_messages, games
from twilight.storage.db import load_game_snapshots


def _cleanup(game_id):
    games.pop(game_id, None)
    chat_messages.pop(game_id, None)
    remove_game_snapshot(game_id)


def test_snapshot_restore_preserva_estado_e_chat(monkeypatch):
    game_id = 'PERSIST1'
    _cleanup(game_id)
    try:
        game = Game(game_id, 'host_persist', {'modifiers': ['fast_cycle']})
        games[game_id] = game
        game.add_player('sid-host', 'host_persist')
        game.add_player('sid-bot', 'bot_persist')
        game.player_data['bot_persist']['is_bot'] = True
        game.started = True
        game.current_turn = 1
        game.players_acted.add('host_persist')
        game.player_data['host_persist']['active_effects'].append(
            {'type': 'silence', 'duration': 2}
        )
        game.deck[-1]['durability'] = 17
        next_card = dict(game.deck[-1])
        add_chat_message(game_id, 'host_persist', 'mensagem sobrevivente')
        assert snapshot_game(game_id) is True

        before_deck = list(game.deck)
        before_hand = list(game.player_data['host_persist']['hand'])
        rows = load_game_snapshots()
        row = next(r for r in rows if r['game_id'] == game_id)
        assert row['state']['players_acted'] == ['host_persist']
        assert row['chat'][0]['message'] == 'mensagem sobrevivente'

        # Simula restart: só a linha desta sala existe no banco.
        monkeypatch.setattr(
            'twilight.game.persistence.load_game_snapshots', lambda: [row],
        )
        games.pop(game_id, None)
        chat_messages.pop(game_id, None)
        result = restore_games(schedule_bots=False)
        assert result['restored'] == 1

        restored = games[game_id]
        assert restored.started is True
        assert restored.current_turn == 1
        assert restored.players == ['host_persist', 'bot_persist']
        assert restored.players_acted == {'host_persist'}
        assert restored.deck == before_deck
        assert restored.player_data['host_persist']['hand'] == before_hand
        assert restored.player_data['host_persist']['active_effects'] == [
            {'type': 'silence', 'duration': 2}
        ]
        # Sids antigos não voltam; bot ganha sid determinístico.
        assert restored.player_data['host_persist']['socket_id'] is None
        assert restored.player_data['bot_persist']['socket_id'] == f'bot:bot_persist:{game_id}'
        assert chat_messages[game_id][0]['message'] == 'mensagem sobrevivente'
        assert next_card in restored.deck
    finally:
        _cleanup(game_id)


def test_close_game_apaga_snapshot():
    game_id = 'PERSIST2'
    games[game_id] = Game(game_id, 'host_close_persist')
    assert snapshot_game(game_id) is True
    assert any(r['game_id'] == game_id for r in load_game_snapshots())

    assert close_game(game_id, notify=False) is True
    assert game_id not in games
    assert not any(r['game_id'] == game_id for r in load_game_snapshots())


def test_snapshot_nao_guarda_sids_reais():
    game_id = 'PERSIST3'
    _cleanup(game_id)
    try:
        game = Game(game_id, 'host_sid_persist')
        games[game_id] = game
        game.add_player('real-sid-123', 'host_sid_persist')
        assert snapshot_game(game_id) is True
        row = next(r for r in load_game_snapshots() if r['game_id'] == game_id)
        blob = repr(row)
        assert 'real-sid-123' not in blob
        assert row['state']['player_data']['host_sid_persist']['socket_id'] is None
    finally:
        _cleanup(game_id)
