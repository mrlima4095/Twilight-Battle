"""
IA leve do servidor (tutorial / bot fácil).

Não depende do client apps/bot.py — roda no processo Flask e emite ações
como um jogador normal.
"""
from __future__ import annotations

import random
import time
from typing import Any, Optional

from twilight.extensions import socketio
from twilight.game.chat import broadcast_system_message


TUTORIAL_BOT_NAME = "mentor"

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


def _emit_action(game_id: str, player: str, action: str, result: dict, log: str = ""):
    socketio.emit(
        "action_success",
        {
            "player_id": player,
            "player_name": player,
            "action": action,
            "result": result,
            "log_message": log,
            "timestamp": _now_ts(),
            "from_bot": True,
        },
        room=game_id,
    )


def plan_easy_actions(game, bot: str) -> list[dict[str, Any]]:
    """Plano simples e legível (dificuldade fácil)."""
    p = game.player_data.get(bot) or {}
    if p.get("dead"):
        return [{"action": "end_turn"}]

    hand = list(p.get("hand") or [])
    atk = list(p.get("attack_bases") or [])
    defense = list(p.get("defense_bases") or [])
    actions: list[dict[str, Any]] = []

    # 1) Draw quase sempre
    if game.deck:
        actions.append({"action": "draw"})

    # 2) Jogar criatura no ataque ou trap/defesa
    empty_atk = _empty_slots(atk)
    empty_def = _empty_slots(defense)
    creatures = [c for c in hand if _is_creature(c)]
    traps = [c for c in hand if _is_trap(c)]

    played = False
    if empty_atk and creatures and random.random() < 0.85:
        c = random.choice(creatures)
        actions.append(
            {
                "action": "play_card",
                "params": {
                    "card_id": c["instance_id"],
                    "position_type": "attack",
                    "position_index": empty_atk[0],
                },
            }
        )
        played = True
        hand = [x for x in hand if x.get("instance_id") != c.get("instance_id")]
        creatures = [c for c in hand if _is_creature(c)]
    elif empty_def and traps and random.random() < 0.5:
        t = traps[0]
        actions.append(
            {
                "action": "play_card",
                "params": {
                    "card_id": t["instance_id"],
                    "position_type": "defense",
                    "position_index": empty_def[0],
                },
            }
        )
        played = True
    elif empty_def and creatures and random.random() < 0.4:
        c = random.choice(creatures)
        actions.append(
            {
                "action": "play_card",
                "params": {
                    "card_id": c["instance_id"],
                    "position_type": "defense",
                    "position_index": empty_def[0],
                },
            }
        )
        played = True

    # 3) Atacar às vezes (se permitido)
    enemies = [
        u
        for u in game.players
        if u != bot
        and not (game.player_data.get(u) or {}).get("dead")
        and not (game.player_data.get(u) or {}).get("observer")
    ]
    can_atk, _ = game.can_attack(bot)
    has_attacker = any(_is_creature(c) for c in (game.player_data[bot].get("attack_bases") or []))
    # se acabamos de planejar play em atk, contar como attacker futuro
    if any(a.get("action") == "play_card" and (a.get("params") or {}).get("position_type") == "attack" for a in actions):
        has_attacker = True

    if can_atk and has_attacker and enemies and random.random() < 0.45:
        target = random.choice(enemies)
        actions.append({"action": "attack", "params": {"target_id": target}})

    actions.append({"action": "end_turn"})
    return actions


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
            log = f"🎴 {bot} jogou {name}"
    elif action == "attack":
        result = game.attack(bot, params.get("target_id"))
        if result and result.get("success"):
            tname = result.get("target_name", "oponente")
            dmg = result.get("damage_to_player", 0)
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

    if (game.player_data.get(bot) or {}).get("dead"):
        game.next_turn()
        _emit_action(game_id, bot, "end_turn", {"success": True}, f"{bot} (morto) passa")
        schedule_bot_turn(game_id)
        return

    # pequena pausa “humana”
    time.sleep(random.uniform(0.9, 1.6))

    plan = plan_easy_actions(game, bot)
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
            _emit_action(game_id, bot, step["action"], result, log)
            if log and step.get("action") != "attack":
                # attack já broadcastou
                pass
        time.sleep(random.uniform(0.55, 1.1))

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
            players_list = [
                {
                    "username": p,
                    "name": game.player_data[p]["name"],
                    "is_bot": bool(game.player_data[p].get("is_bot")),
                }
                for p in game.players
                if p in game.player_data
            ]
            socketio.emit(
                "lobby_reset",
                {
                    "game_id": game_id,
                    "last_winner": winner,
                    "last_winner_name": wname,
                    "players": players_list,
                    "modifiers": lobby.get("modifiers", []),
                    "creator": game.creator,
                    "tutorial": bool(getattr(game, "tutorial", False)),
                    "message": "Sala pronta para jogar de novo.",
                },
                room=game_id,
            )
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
            time.sleep(delay)
        try:
            run_bot_turn(game_id)
        except Exception as e:
            print(f"[ai] erro no turno do bot: {e}")
            import traceback

            traceback.print_exc()

    socketio.start_background_task(_job)


def add_tutorial_bot(game, name: str = TUTORIAL_BOT_NAME) -> bool:
    """Adiciona bot de treino à sala (sem conta real)."""
    if name in game.players:
        return False
    if len(game.players) >= game.max_players:
        return False

    sid = f"bot:{name}:{game.game_id}"
    game.players.append(name)
    game.socket_to_username[sid] = name
    game.player_data[name] = game._make_player_state(name, sid, deal_hand=True)
    game.player_data[name]["is_bot"] = True
    game.player_data[name]["name"] = "Mentor"
    return True
