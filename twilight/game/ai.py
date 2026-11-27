"""
IA leve do servidor (tutorial / bots da sala).

Não depende do client apps/bot.py — roda no processo Flask e emite ações
como um jogador normal. Dificuldades: fácil, normal e difícil.
"""
from __future__ import annotations

import random
import time
from typing import Any, Optional

from twilight.extensions import socketio
from twilight.game.chat import broadcast_system_message
from twilight.game.lobby import emit_lobby_update, lobby_players, normalize_bot_difficulty


TUTORIAL_BOT_NAME = "mentor"

# Probabilidades por dificuldade. Valores mais altos = jogadas mais eficientes.
_DIFFICULTY_PLAN = {
    'easy': {
        'draw': 0.80, 'attack_card': 0.75, 'trap': 0.40,
        'defense_card': 0.30, 'attack': 0.40,
        'think': (1.0, 1.8), 'gap': (0.65, 1.1), 'smart_target': False,
    },
    'normal': {
        'draw': 0.95, 'attack_card': 0.95, 'trap': 0.70,
        'defense_card': 0.55, 'attack': 0.70,
        'think': (0.8, 1.4), 'gap': (0.5, 0.9), 'smart_target': False,
    },
    'hard': {
        'draw': 1.00, 'attack_card': 1.00, 'trap': 0.90,
        'defense_card': 0.75, 'attack': 0.90,
        'think': (0.6, 1.0), 'gap': (0.45, 0.8), 'smart_target': True,
    },
}

# Dicas enviadas ao client no modo tutorial (progressivas)
TUTORIAL_TIPS = [
    {
        "id": "welcome",
        "title": "Bem-vindo ao treino",
        "body": "Você joga contra o Mentor (fácil). Em cada turno você pode: comprar 1 carta, jogar 1 carta, atacar 1 vez e passar o turno. Explore sem pressa!",
    },
    {
        "id": "draw",
        "title": "Compre cartas",
        "body": "Clique no monte (📚) para comprar. Quanto mais cartas na mão, mais opções — compre cedo no turno quando puder.",
    },
    {
        "id": "play_attack",
        "title": "Bases de ataque",
        "body": "Coloque criaturas nas bases de ATAQUE (⚔️). Só criaturas em ataque somam poder quando você ataca um oponente.",
    },
    {
        "id": "defense_traps",
        "title": "Defesa e armadilhas",
        "body": "Na DEFESA (🛡️) cabem criaturas e armadilhas. Armadilhas aparecem disfarçadas de criatura para o inimigo — ele não sabe se é bluff!",
    },
    {
        "id": "equip",
        "title": "Dois jeitos de equipar",
        "body": "1) Item NA CRIATURA (botão equipar): buffa a criatura e não gasta o play do turno. 2) Item NO JOGADOR (slot arma/capacete/etc.): gasta o play e ativa efeitos de personagem (ex.: botas = troca grátis).",
    },
    {
        "id": "day_night",
        "title": "Dia e noite",
        "body": "Zumbis e vampiros morrem com a luz do dia (sem proteção). À noite ficam fortes. O ciclo muda sozinho (a cada 24 turnos, ou 6 com Crepúsculo Acelerado).",
    },
    {
        "id": "mage_spell",
        "title": "Magos e feitiços",
        "body": "Para lançar feitiço você precisa de um Mago (ou Rei Mago / Mago Negro) em campo. Feitiços de cura e buff mudam o rumo da luta.",
    },
    {
        "id": "attack",
        "title": "Quando atacar",
        "body": "Na 1ª rodada os ataques ficam bloqueados até todos agirem. Depois, ataque quando tiver criaturas no ataque. Cuidado com defesas cheias — pode ser armadilha!",
    },
    {
        "id": "end",
        "title": "Fim de turno",
        "body": "Quando terminar suas ações, passe o turno. O Mentor joga de forma simples (fácil) para você treinar com calma.",
    },
]


def is_bot_player(game, username: str) -> bool:
    pdata = (game.player_data or {}).get(username) or {}
    return bool(pdata.get("is_bot")) or username == TUTORIAL_BOT_NAME


def _is_creature(c: Optional[dict]) -> bool:
    return bool(c and c.get("type") == "creature")


def _is_trap(c: Optional[dict]) -> bool:
    return bool(c and c.get("type") == "trap")


def _empty_slots(bases: list) -> list[int]:
    return [i for i, c in enumerate(bases or []) if c is None]


def _now_ts() -> str:
    try:
        from twilight.config import now_sp_str
        return now_sp_str("%H:%M:%S")
    except Exception:
        return time.strftime("%H:%M:%S")


def _emit_action(game, player: str, action: str, result: dict, log: str = ""):
    display = (game.player_data.get(player) or {}).get('name') or player
    socketio.emit(
        "action_success",
        {
            "player_id": player,
            "player_name": display,
            "action": action,
            "result": result,
            "log_message": log,
            "timestamp": _now_ts(),
            "from_bot": True,
        },
        room=game.game_id,
    )


def plan_bot_actions(game, bot: str, difficulty: str | None = None) -> list[dict[str, Any]]:
    """Plano do turno conforme a dificuldade do bot."""
    p = game.player_data.get(bot) or {}
    if p.get("dead"):
        return [{"action": "end_turn"}]

    diff = normalize_bot_difficulty(difficulty or p.get("bot_difficulty") or "easy")
    cfg = _DIFFICULTY_PLAN[diff]

    hand = list(p.get("hand") or [])
    atk = list(p.get("attack_bases") or [])
    defense = list(p.get("defense_bases") or [])
    actions: list[dict[str, Any]] = []

    # 1) Comprar carta
    if game.deck and random.random() < cfg["draw"]:
        actions.append({"action": "draw"})

    # 2) Jogar criatura no ataque ou armadilha/criatura na defesa
    empty_atk = _empty_slots(atk)
    empty_def = _empty_slots(defense)
    creatures = [c for c in hand if _is_creature(c)]
    traps = [c for c in hand if _is_trap(c)]

    if empty_atk and creatures and random.random() < cfg["attack_card"]:
        c = random.choice(creatures)
        actions.append({
            "action": "play_card",
            "params": {
                "card_id": c["instance_id"],
                "position_type": "attack",
                "position_index": empty_atk[0],
            },
        })
        hand = [x for x in hand if x.get("instance_id") != c.get("instance_id")]
        creatures = [c for c in hand if _is_creature(c)]
    elif empty_def and traps and random.random() < cfg["trap"]:
        t = traps[0]
        actions.append({
            "action": "play_card",
            "params": {
                "card_id": t["instance_id"],
                "position_type": "defense",
                "position_index": empty_def[0],
            },
        })
    elif empty_def and creatures and random.random() < cfg["defense_card"]:
        c = random.choice(creatures)
        actions.append({
            "action": "play_card",
            "params": {
                "card_id": c["instance_id"],
                "position_type": "defense",
                "position_index": empty_def[0],
            },
        })

    # 3) Atacar (respeitando a 1ª rodada)
    enemies = [
        u for u in game.players
        if u != bot
        and not (game.player_data.get(u) or {}).get("dead")
        and not (game.player_data.get(u) or {}).get("observer")
        and not (game.player_data.get(u) or {}).get("spectator")
    ]
    can_atk, _ = game.can_attack(bot)
    has_attacker = any(_is_creature(c) for c in (p.get("attack_bases") or []))
    if any(
        a.get("action") == "play_card"
        and (a.get("params") or {}).get("position_type") == "attack"
        for a in actions
    ):
        has_attacker = True

    if can_atk and has_attacker and enemies and random.random() < cfg["attack"]:
        if cfg["smart_target"]:
            # Difícil: foca quem tem menos vida (aproveita kills).
            target = min(
                enemies,
                key=lambda u: (game.player_data.get(u) or {}).get("life", 0),
            )
        else:
            target = random.choice(enemies)
        actions.append({"action": "attack", "params": {"target_id": target}})

    actions.append({"action": "end_turn"})
    return actions


def plan_easy_actions(game, bot: str) -> list[dict[str, Any]]:
    """Compatibilidade: o Mentor/tutorial continua jogando no fácil."""
    return plan_bot_actions(game, bot, 'easy')


def _run_one_action(game, bot: str, step: dict) -> tuple[bool, Optional[dict], str]:
    """Executa uma ação do bot. Retorna (ok, result, log)."""
    action = step.get("action")
    params = step.get("params") or {}
    result = None
    log = ""

    if action == "draw":
        result = game.draw_card(bot)
        if result and result.get("success"):
            log = f"📥 {bot} comprou uma carta"
    elif action == "play_card":
        result = game.play_card(
            bot,
            params.get("card_id"),
            params.get("position_type"),
            params.get("position_index"),
        )
        if result and result.get("success"):
            name = (result.get("card") or {}).get("name", "uma carta")
            if getattr(game, "has_fog", lambda: False)():
                pos = params.get("position_type") or "campo"
                where = {"attack": "no ataque", "defense": "na defesa", "equipment": "no equipamento"}.get(pos, "no campo")
                log = f"🎴 {bot} jogou uma carta {where} (névoa)"
            else:
                log = f"🎴 {bot} jogou {name}"
    elif action == "attack":
        result = game.attack(bot, params.get("target_id"))
        if result and result.get("success"):
            tname = result.get("target_name", "oponente")
            dmg = result.get("damage_to_player", 0)
            if getattr(game, "has_fog", lambda: False)():
                log = f"⚔️ {bot} atacou {tname} sob a névoa"
            else:
                log = f"⚔️ {bot} atacou {tname} (dano {dmg})"
            broadcast_system_message(game.game_id, log)
    elif action == "end_turn":
        game.next_turn()
        nxt = game.players[game.current_turn]
        result = {"success": True, "next_turn": nxt}
        log = f"➡️ {bot} passou o turno → {nxt}"
    else:
        return False, {"success": False, "message": f"ação desconhecida: {action}"}, ""

    ok = bool(result and result.get("success"))
    return ok, result, log


def run_bot_turn(game_id: str) -> None:
    """Executa o turno completo do bot atual (se for bot)."""
    from twilight.state import games

    game = games.get(game_id)
    if not game or not game.started or getattr(game, "finished", False):
        return

    if not game.players:
        return

    bot = game.players[game.current_turn]
    if not is_bot_player(game, bot):
        return

    diff = normalize_bot_difficulty(
        (game.player_data.get(bot) or {}).get('bot_difficulty') or 'easy'
    )
    cfg = _DIFFICULTY_PLAN[diff]
    display = (game.player_data.get(bot) or {}).get('name') or bot

    if (game.player_data.get(bot) or {}).get("dead"):
        game.next_turn()
        _emit_action(game, bot, "end_turn", {"success": True}, f"{display} (morto) passa")
        schedule_bot_turn(game_id)
        return

    # pausa “humana” (socketio.sleep cede ao hub gevent)
    socketio.sleep(random.uniform(*cfg['think']))

    plan = plan_bot_actions(game, bot, diff)
    for step in plan:
        game = games.get(game_id)
        if not game or getattr(game, "finished", False):
            return
        if game.players[game.current_turn] != bot:
            return

        ok, result, log = _run_one_action(game, bot, step)
        if ok and result:
            if step.get("action") != "end_turn":
                ended = game.register_action(bot, step["action"])
                if ended:
                    socketio.emit(
                        "first_round_ended",
                        {
                            "message": "🎉 PRIMEIRA RODADA CONCLUÍDA! Todos já jogaram, ataques liberados!"
                        },
                        room=game_id,
                    )
            _emit_action(game, bot, step["action"], result, log)
            if log and step.get("action") != "attack":
                # attack já broadcastou
                pass
        socketio.sleep(random.uniform(*cfg['gap']))

        if step.get("action") == "end_turn":
            break

    # vitória?
    game = games.get(game_id)
    if not game:
        return
    winner = game.check_winner() if hasattr(game, "check_winner") else None
    if winner and getattr(game, "finished", False) and not getattr(game, "_game_over_emitted", False):
        try:
            game._game_over_emitted = True
            wname = game.player_data[winner]["name"]
            # evita import circular: emite direto
            broadcast_system_message(game_id, f"🏆 {wname} VENCEU O JOGO! 🏆")
            socketio.emit(
                "game_over",
                {
                    "winner": winner,
                    "winner_name": wname,
                    "message": f"🏆 {wname} VENCEU O JOGO!",
                    "rematch": True,
                    "same_room": True,
                    "game_id": game_id,
                    "tutorial": bool(getattr(game, "tutorial", False)),
                },
                room=game_id,
            )
            lobby = game.reset_to_lobby(last_winner=winner)
            socketio.emit(
                "lobby_reset",
                {
                    "game_id": game_id,
                    "last_winner": winner,
                    "last_winner_name": wname,
                    "players": lobby_players(game),
                    "modifiers": lobby.get("modifiers", []),
                    "creator": game.creator,
                    "tutorial": bool(getattr(game, "tutorial", False)),
                    "message": "Sala pronta para jogar de novo.",
                },
                room=game_id,
            )
            emit_lobby_update(game, "Sala pronta para jogar de novo.")
        except Exception as e:
            print(f"[ai] game_over emit failed: {e}")
        return

    # se o próximo também for bot (raro), continua
    schedule_bot_turn(game_id)


def schedule_bot_turn(game_id: str, delay: float = 0.4) -> None:
    """Agenda turno do bot se for a vez dele."""
    from twilight.state import games

    game = games.get(game_id)
    if not game or not game.started or getattr(game, "finished", False):
        return
    if not game.players:
        return
    current = game.players[game.current_turn]
    if not is_bot_player(game, current):
        return

    def _job():
        if delay:
            socketio.sleep(delay)
        try:
            run_bot_turn(game_id)
        except Exception as e:
            print(f"[ai] erro no turno do bot: {e}")
            import traceback

            traceback.print_exc()

    socketio.start_background_task(_job)


def add_bot(game, name: str | None = None, difficulty: str = 'normal',
            display_name: str | None = None) -> dict | None:
    """Adiciona um bot servidor à sala (sem conta real). Só no lobby."""
    if getattr(game, 'started', False) or getattr(game, 'finished', False):
        return None
    if len(game.players) >= int(getattr(game, 'max_players', 6) or 6):
        return None

    diff = normalize_bot_difficulty(difficulty)

    if name:
        key = str(name).strip().lower()
    else:
        n = 1
        key = f'bot_{n}'
        while key in game.players or key in game.player_data:
            n += 1
            key = f'bot_{n}'
    if key in game.players or key in game.player_data:
        return None

    label = display_name or (
        'Mentor' if key == TUTORIAL_BOT_NAME else key.replace('bot_', 'Bot ').replace('_', ' ').title()
    )
    sid = f'bot:{key}:{game.game_id}'
    game.players.append(key)
    game.socket_to_username[sid] = key
    game.player_data[key] = game._make_player_state(key, sid, deal_hand=True)
    game.player_data[key].update({
        'is_bot': True,
        'bot_difficulty': diff,
        'name': label,
    })
    return {'username': key, 'name': label, 'is_bot': True, 'bot_difficulty': diff}


def remove_bot(game, username: str) -> bool:
    """Remove apenas um bot do lobby, sem fechar a sala."""
    if getattr(game, 'started', False) or not is_bot_player(game, username):
        return False
    if username in game.players:
        game.players.remove(username)
    game.player_data.pop(username, None)
    for sid, uname in list(game.socket_to_username.items()):
        if uname == username:
            del game.socket_to_username[sid]
    if not game.players:
        game.current_turn = 0
    elif game.current_turn >= len(game.players):
        game.current_turn = 0
    return True


def remove_all_bots(game) -> list[str]:
    """Remove todos os bots do lobby. Devolve os usernames removidos."""
    bots = [p for p in list(game.players) if is_bot_player(game, p)]
    for bot in bots:
        remove_bot(game, bot)
    return bots


def fill_bots(game, count: int | None = None, difficulty: str = 'normal',
              reserve_creator_slot: bool = False) -> list[dict]:
    """Preenche vagas da sala com bots (padrão: todas as vagas livres)."""
    reserved = 1 if reserve_creator_slot and game.creator not in game.players else 0
    slots = int(getattr(game, 'max_players', 6) or 6) - len(game.players) - reserved
    if slots <= 0:
        return []
    wanted = slots if count is None else max(0, min(int(count), slots))
    diff = normalize_bot_difficulty(difficulty)
    game.bot_difficulty = diff
    added = []
    for _ in range(wanted):
        bot = add_bot(game, difficulty=diff)
        if not bot:
            break
        added.append(bot)
    return added


def add_tutorial_bot(game, name: str = TUTORIAL_BOT_NAME) -> bool:
    """Adiciona o Mentor (bot fácil) ao tutorial."""
    return add_bot(game, name=name, difficulty='easy', display_name='Mentor') is not None
