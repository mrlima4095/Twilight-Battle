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
from twilight.game.rituals import RitualManager


TUTORIAL_BOT_NAME = "mentor"

# Itens que o motor aceita equipar mesmo não sendo 'weapon'/'armor'.
_SPECIAL_EQUIP_IDS = frozenset({
    'lamina_almas', 'blade_vampires', 'blade_dragons',
    'capacete_trevas', 'adaga_crepusculo', 'clava_orc',
})

# Criaturas que habilitam feitiços e os feitiços que o bot sabe usar.
_MAGE_IDS = frozenset({'mago', 'mago_negro', 'rei_mago'})
_SELF_SPELLS = frozenset({'feitico_cura', 'feitico_duro_matar'})
_CREATURE_BUFF_SPELLS = frozenset({'feitico_cortes'})
_TRAP_SILENCE_SPELLS = frozenset({'feitico_silencio', 'feitico_selo_silencio'})
_ORACLE_ID = 'oraculo_imortalidade'
_IMMORTALITY_ID = 'talisma_imortalidade'
_RITUAL_IDS = frozenset({'ritual_157', 'ritual_amor'})
_DETERRENT_TRAPS = frozenset({'armadilha_poco', 'armadilha_espelho'})

# Probabilidades por dificuldade. Valores mais altos = jogadas mais eficientes.
_DIFFICULTY_PLAN = {
    'easy': {
        'draw': 0.80, 'attack_card': 0.75, 'trap': 0.40,
        'defense_card': 0.30, 'attack': 0.40, 'equip': 0.25,
        'ability': 0.25, 'bot_rivalry': 0.0,
        'think': (1.0, 1.8), 'gap': (0.65, 1.1), 'smart_target': False,
    },
    'normal': {
        'draw': 0.95, 'attack_card': 0.95, 'trap': 0.70,
        'defense_card': 0.55, 'attack': 0.70, 'equip': 0.65,
        'ability': 0.70, 'bot_rivalry': 0.25,
        'think': (0.8, 1.4), 'gap': (0.5, 0.9), 'smart_target': False,
    },
    'hard': {
        'draw': 1.00, 'attack_card': 1.00, 'trap': 0.90,
        'defense_card': 0.75, 'attack': 1.00, 'equip': 1.0,
        'ability': 1.0, 'bot_rivalry': 0.55,
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


def _living_enemies(game, bot: str) -> list[str]:
    """Oponentes válidos para ataque (bots incluídos, vivos e não-espectadores)."""
    return [
        u for u in (game.players or [])
        if u != bot
        and not (game.player_data.get(u) or {}).get("dead")
        and not (game.player_data.get(u) or {}).get("observer")
        and not (game.player_data.get(u) or {}).get("spectator")
    ]


def _has_attackers(attack_bases: list) -> bool:
    """Só criaturas não-petrificadas em ataque realmente somam poder."""
    return any(
        _is_creature(c) and not c.get("petrified")
        for c in (attack_bases or [])
    )


def _defense_weight(game, username: str) -> int:
    """Defesa aproximada do alvo, usada como desempate na escolha de alvo."""
    pdata = game.player_data.get(username) or {}
    cards = [c for c in (pdata.get("defense_bases") or []) if c]
    creature_life = sum(
        int(c.get("life") or 0) for c in cards if c.get("type") == "creature"
    )
    traps = sum(1 for c in cards if c.get("type") == "trap")
    return creature_life // 10 + traps * 20


def _choose_target(game, bot: str, enemies: list[str], cfg: dict) -> str:
    """Escolhe o alvo do ataque. Bots também são alvos legítimos."""
    bot_rivals = [u for u in enemies if is_bot_player(game, u)]
    prefer_bot = bool(bot_rivals) and random.random() < cfg.get("bot_rivalry", 0)

    if cfg.get("smart_target"):
        # Difícil: ataca o alvo mais frágil (vida + defesa). A rivalidade entre
        # bots funciona como um desconto virtual, não como regra absoluta: um
        # humano quase morto continua sendo o melhor alvo.
        def score(username: str) -> int:
            life = int((game.player_data.get(username) or {}).get("life") or 0)
            bonus = 450 if prefer_bot and is_bot_player(game, username) else 0
            return life + _defense_weight(game, username) - bonus

        return min(enemies, key=score)

    if prefer_bot:
        return random.choice(bot_rivals)
    return random.choice(enemies)


def _equippable_item(game, item: Optional[dict]) -> bool:
    return bool(
        item
        and (
            item.get("type") in ("weapon", "armor")
            or item.get("id") in _SPECIAL_EQUIP_IDS
        )
        and game._item_slot(item)
    )


def _item_fits_creature(game, item: dict, creature: dict) -> bool:
    """Espelha as restrições de equipamento do motor para não gerar ações inválidas."""
    item_id = item.get("id")
    creature_id = creature.get("id")

    if item_id == "blade_vampires" and creature_id not in ("vampiro_tayler", "vampiro_wers"):
        return False
    if item_id == "blade_dragons" and creature_id not in (
        "elfo", "vampiro_tayler", "vampiro_wers", "mago", "mago_negro", "rei_mago"
    ):
        return False
    if item_id == "lamina_almas" and creature_id not in (
        "elfo", "mago", "mago_negro", "rei_mago", "vampiro_tayler", "vampiro_wers"
    ):
        return False
    if (item_id == "adaga_crepusculo" or item.get("werewolf_only")) and not (
        creature.get("werewolf") or creature_id == "lobisomem_crepusculo"
    ):
        return False
    if item_id == "cajado_mago_negro" and creature_id not in (
        item.get("equip_races") or ["mago", "mago_negro", "rei_mago"]
    ):
        return False

    # Bestas não equipam nada; a adaga do lobisomem é a única exceção.
    if game._is_beast_creature(creature) and not (
        item.get("werewolf_only") and creature.get("werewolf")
    ):
        return False

    slot = game._item_slot(item)
    return bool(slot) and not any(
        game._item_slot(equipped) == slot
        for equipped in (creature.get("equipped_items") or [])
    )


def _plan_equip(game, hand: list, attack: list, defense: list, smart: bool) -> Optional[dict]:
    """Equipa um item da mão em uma criatura em campo (não gasta o 'play')."""
    creatures = [
        c
        for base in (attack, defense)
        for c in (base or [])
        if _is_creature(c) and not c.get("petrified")
    ]
    pairs = [
        (item, creature)
        for item in hand if _equippable_item(game, item)
        for creature in creatures if _item_fits_creature(game, item, creature)
    ]
    if not pairs:
        return None

    if smart:
        attack_ids = {
            c.get("instance_id") for c in (attack or []) if c
        }

        def value(pair) -> int:
            item, creature = pair
            bonus = (
                int(item.get("attack") or 0)
                + int(item.get("attack_bonus") or 0)
                + int(item.get("protection") or 0) // 4
            )
            return bonus + (50 if creature.get("instance_id") in attack_ids else 0)

        item, creature = max(pairs, key=value)
    else:
        item, creature = random.choice(pairs)

    return {
        "action": "equip_item",
        "params": {
            "item_card_id": item.get("instance_id"),
            "creature_card_id": creature.get("instance_id"),
        },
    }


def _field_creatures(pdata: dict) -> list[tuple[str, int, dict]]:
    return [
        (base, i, card)
        for base in ("attack_bases", "defense_bases")
        for i, card in enumerate(pdata.get(base) or [])
        if _is_creature(card)
    ]


def _plan_swap(game, bot: str, pdata: dict, attack: list, defense: list) -> Optional[dict]:
    """Coloca a melhor criatura em ataque e protege mago ferido."""
    boots = (pdata.get("equipment") or {}).get("boots")
    free_swap = bool(
        boots and boots.get("ability") == "free_swap" and not pdata.get("free_swap_used")
    )
    if not free_swap and not game.can_act(bot, "swap"):
        return None

    def step(src_type, src_i, dst_type, dst_i):
        return {
            "action": "swap_positions",
            "params": {
                "pos1_type": src_type, "pos1_index": src_i,
                "pos2_type": dst_type, "pos2_index": dst_i,
            },
        }

    empty_atk = _empty_slots(attack)
    empty_def = _empty_slots(defense)
    atk_creatures = [(i, c) for i, c in enumerate(attack) if _is_creature(c)]
    def_creatures = [(i, c) for i, c in enumerate(defense) if _is_creature(c)]

    if def_creatures:
        best_i, best = max(def_creatures, key=lambda x: int(x[1].get("attack") or 0))
        best_power = int(best.get("attack") or 0)
        if empty_atk and best_power >= 60:
            attack[empty_atk[0]], defense[best_i] = defense[best_i], attack[empty_atk[0]]
            return step("defense", best_i, "attack", empty_atk[0])
        if atk_creatures:
            weak_i, weak = min(atk_creatures, key=lambda x: int(x[1].get("attack") or 0))
            if best_power > int(weak.get("attack") or 0) + 20:
                attack[weak_i], defense[best_i] = defense[best_i], attack[weak_i]
                return step("defense", best_i, "attack", weak_i)

    for i, card in atk_creatures:
        if card.get("id") in _MAGE_IDS and int(card.get("life") or 0) < 300 and empty_def:
            attack[i], defense[empty_def[0]] = defense[empty_def[0]], attack[i]
            return step("attack", i, "defense", empty_def[0])

    return None


def _plan_toggle_time(game, bot: str, pdata: dict) -> Optional[dict]:
    """Fênix: só muda dia/noite quando isso favorece o próprio campo."""
    if "disable_daycicle" in (game.modifiers or []) or not game.can_act(bot, "toggle_time"):
        return None
    if not any(c.get("id") == "fenix" for _, _, c in _field_creatures(pdata)):
        return None

    def counts(username: str) -> tuple[int, int]:
        player = game.player_data.get(username) or {}
        vulnerable = wolves = 0
        for _, _, card in _field_creatures(player):
            if not game.has_daylight_protection(player, card) and (
                card.get("dies_daylight") or card.get("night_creature")
            ):
                vulnerable += 1
            if card.get("werewolf"):
                wolves += 1
        return vulnerable, wolves

    own_v, own_w = counts(bot)
    opp_v = opp_w = 0
    for enemy in _living_enemies(game, bot):
        v, w = counts(enemy)
        opp_v += v
        opp_w += w

    if game.time_of_day == "day":  # vai virar noite
        benefit = (own_v - opp_v) + 2 * (own_w - opp_w)
    else:  # vai virar dia
        benefit = (opp_v - own_v) + 2 * (opp_w - own_w)

    if benefit > 0:
        return {"action": "toggle_time", "params": {}}
    return None


def _plan_call_centaurs(game, bot: str, pdata: dict) -> Optional[dict]:
    """Super Centauro: puxa todos os centauros do campo para a mão."""
    if not game.can_act(bot, "call_centaurs"):
        return None
    if not any(
        c.get("id") == "super_centauro" and not c.get("call_centaurs_used")
        for _, _, c in _field_creatures(pdata)
    ):
        return None

    for username in game.players:
        player = game.player_data.get(username) or {}
        if player.get("dead"):
            continue
        for base in ("attack_bases", "defense_bases"):
            if any(c and c.get("id") == "centauro" for c in (player.get(base) or [])):
                return {"action": "call_centaurs", "params": {}}
    return None


def _plan_prophet_curse(game, bot: str, pdata: dict) -> Optional[dict]:
    """Profeta: amaldiçoa a criatura mais forte visível do oponente."""
    if "no_prophet" in (game.modifiers or []) or not game.can_act(bot, "prophet_curse"):
        return None
    if not any(
        c.get("id") == "profeta" and int(c.get("prophet_uses") or 0) < 2
        for _, _, c in _field_creatures(pdata)
    ):
        return None

    best = None
    for enemy in _living_enemies(game, bot):
        for _, _, card in _field_creatures(game.player_data.get(enemy) or {}):
            if card.get("is_disguised"):
                continue
            score = int(card.get("attack") or 0) + int(card.get("life") or 0) // 4
            if best is None or score > best[0]:
                best = (score, enemy, card.get("instance_id"))

    if best:
        return {
            "action": "prophet_curse",
            "params": {"target_player_id": best[1], "target_card_id": best[2]},
        }
    return None


def _plan_spell(game, bot: str, pdata: dict, hand: list, attack: list) -> Optional[dict]:
    """Mago: cura/buff próprio ou silencia armadilhas antes do ataque."""
    if "no_spells" in (game.modifiers or []) or not game.can_act(bot, "spell"):
        return None
    if not any(
        c.get("id") in _MAGE_IDS and not c.get("blocked")
        for _, _, c in _field_creatures(pdata)
    ):
        return None

    life = int(pdata.get("life") or 0)
    best_attack = None
    for card in attack:
        if _is_creature(card) and not card.get("petrified"):
            if best_attack is None or int(card.get("attack") or 0) > int(best_attack.get("attack") or 0):
                best_attack = card

    for spell in hand:
        if spell.get("type") != "spell":
            continue
        sid = spell.get("id")
        params = {"spell_id": spell.get("instance_id") or sid}
        if sid in _SELF_SPELLS:
            threshold = 900 if sid == "feitico_cura" else 700
            if life >= threshold:
                continue
            params["target_player_id"] = bot
        elif sid in _CREATURE_BUFF_SPELLS and best_attack:
            params["target_player_id"] = bot
            params["target_card_id"] = best_attack.get("instance_id")
        elif sid in _TRAP_SILENCE_SPELLS:
            params["target_player_id"] = bot
        else:
            continue
        return {"action": "cast_spell", "params": params}
    return None


def _plan_revive(game, bot: str, pdata: dict, hand: list) -> Optional[dict]:
    """Revive a melhor carta do cemitério quando há 4 runas na mão."""
    if "no_runes" in (game.modifiers or []):
        return None
    runes = [
        c for c in hand
        if c and (c.get("type") == "rune" or c.get("id") == "runa")
    ]
    if len(runes) < 4:
        return None

    def value(card: dict) -> int:
        score = int(card.get("attack") or 0) + int(card.get("life") or 0) // 4
        if card.get("type") == "creature":
            score += 500
        elif card.get("type") == "talisman":
            score += 100
        return score

    candidates = [
        c for c in (game.graveyard or [])
        if c and c.get("type") != "rune" and c.get("id") != "runa"
    ]
    if not candidates:
        return None
    best = max(candidates, key=value)
    return {
        "action": "revive",
        "params": {"card_id": best.get("instance_id") or best.get("name")},
    }


def _plan_ritual(game, bot: str, pdata: dict, hand: list) -> Optional[dict]:
    """Rituais disponíveis: rouba talismãs (157) ou limpa profecia (Amor)."""
    if not game.can_act(bot, "ritual"):
        return None

    field_ids = {
        c.get("id") for _, _, c in _field_creatures(pdata)
    }
    has_mago_negro = "mago_negro" in field_ids
    rituals_in_hand = {
        c.get("id") for c in hand if c and c.get("type") == "ritual"
    }

    def unlocked(ritual_id: str) -> bool:
        return has_mago_negro or ritual_id in rituals_in_hand

    enemies = _living_enemies(game, bot)
    if unlocked("ritual_157"):
        can_cast, _ = RitualManager.check_ritual_157(game, bot)
        if can_cast:
            target = max(
                enemies,
                key=lambda u: len(game.player_data.get(u, {}).get("talismans") or []),
                default=None,
            )
            if target and (game.player_data.get(target, {}).get("talismans") or []):
                return {
                    "action": "ritual",
                    "params": {
                        "ritual_id": "ritual_157",
                        "target_player_id": target,
                    },
                }

    if unlocked("ritual_amor"):
        can_cast, _ = RitualManager.check_ritual_amor(game, bot)
        if can_cast:
            for enemy in enemies:
                pdata_enemy = game.player_data.get(enemy) or {}
                cursed = bool(pdata_enemy.get("profecia_alvo")) or any(
                    (effect or {}).get("type") == "profecia_morte"
                    for effect in (pdata_enemy.get("active_effects") or [])
                )
                if cursed:
                    return {
                        "action": "ritual",
                        "params": {
                            "ritual_id": "ritual_amor",
                            "target_player_id": enemy,
                        },
                    }
    return None


def _plan_oracle(game, bot: str, pdata: dict, hand: list) -> Optional[dict]:
    """Marca o Talismã da Imortalidade de um oponente prestes a morrer."""
    if not game.can_act(bot, "oracle"):
        return None
    if not any(c.get("id") == _ORACLE_ID for c in hand if c):
        return None
    if not any(
        c and c.get("id") == "elfo" for c in (pdata.get("defense_bases") or [])
    ):
        return None

    candidates = []
    for enemy in _living_enemies(game, bot):
        enemy_data = game.player_data.get(enemy) or {}
        cards = list(enemy_data.get("hand") or []) + list(enemy_data.get("talismans") or [])
        if any(
            c and c.get("id") == _IMMORTALITY_ID and not c.get("oracle_blocked")
            for c in cards
        ):
            candidates.append((int(enemy_data.get("life") or 0), enemy))
    if not candidates:
        return None
    _, target = min(candidates)
    return {"action": "oracle", "params": {"target_id": target}}


def _plan_flip(game, bot: str, pdata: dict) -> Optional[dict]:
    """Revela uma armadilha letal já disfarçada para intimidar atacantes."""
    for base in ("attack_bases", "defense_bases"):
        for i, card in enumerate(pdata.get(base) or []):
            if (
                card
                and card.get("is_disguised")
                and card.get("type") == "trap"
                and card.get("id") in _DETERRENT_TRAPS
            ):
                return {
                    "action": "flip_card",
                    "params": {
                        "position_type": base.replace("_bases", ""),
                        "position_index": i,
                    },
                }
    return None


def _now_ts() -> str:
    try:
        from twilight.config import now_sp_str
        return now_sp_str("%H:%M:%S")
    except Exception:
        return time.strftime("%H:%M:%S")


def _emit_action(game, player: str, action: str, result: dict, log: str = ""):
    display = (game.player_data.get(player) or {}).get('name') or player
    payload = {
        "player_id": player,
        "player_name": display,
        "action": action,
        "log_message": log,
        "timestamp": _now_ts(),
        "from_bot": True,
    }

    # Um ataque de bot não pode vazar poder/dano/vida da vítima sob névoa.
    if action == "attack" and isinstance(result, dict) and getattr(game, "has_fog", lambda: False)():
        sensitive = (
            "total_attack", "damage_to_player", "damage_absorbed", "target_life",
            "cards_destroyed", "cards_damaged", "cards_healed",
            "creature_effects", "trap_effects", "reflected_damage",
        )
        stripped = {k: v for k, v in result.items() if k not in sensitive}
        stripped["fog"] = True
        socketio.emit("action_success", dict(payload, result=stripped), room=game.game_id)

        target = (
            result.get("target") or result.get("target_name") or result.get("original_target")
        )
        target_sid = game.get_socket_id(target) if target else None
        if target_sid:
            socketio.emit(
                "action_success", dict(payload, result=result), to=target_sid
            )
        return

    # Habilidades raras também não podem revelar cartas/alvos sob névoa.
    if (
        action in ("revive", "ritual", "oracle", "flip_card", "prophet_curse")
        and isinstance(result, dict)
        and getattr(game, "has_fog", lambda: False)()
    ):
        sensitive = ("card", "target", "target_name", "stolen_count", "message")
        stripped = {k: v for k, v in result.items() if k not in sensitive}
        stripped["fog"] = True
        socketio.emit("action_success", dict(payload, result=stripped), room=game.game_id)
        return

    socketio.emit("action_success", dict(payload, result=result), room=game.game_id)


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

    # 2) Troca tática antes de jogar, para os slots já ficarem atualizados.
    if random.random() < cfg.get("ability", 0):
        swap_step = _plan_swap(game, bot, p, atk, defense)
        if swap_step:
            actions.append(swap_step)

    # 3) Jogar criatura no ataque ou armadilha/criatura na defesa
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
        atk[empty_atk[0]] = c
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
        defense[empty_def[0]] = t
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
        defense[empty_def[0]] = c

    # 4) Equipar itens nas criaturas: não gasta o 'play' e aumenta o ataque.
    if random.random() < cfg.get("equip", 0):
        equip_step = _plan_equip(game, hand, atk, defense, cfg.get("smart_target", False))
        if equip_step:
            actions.append(equip_step)

    # 5) Habilidades ativas das criaturas (Fênix, Centauro, Profeta e Mago).
    if random.random() < cfg.get("ability", 0):
        for planner in (_plan_toggle_time, _plan_call_centaurs, _plan_prophet_curse):
            ability_step = planner(game, bot, p)
            if ability_step:
                actions.append(ability_step)
        spell_step = _plan_spell(game, bot, p, hand, atk)
        if spell_step:
            actions.append(spell_step)

    # 6) Reviver, rituais, Oráculo e revelar armadilhas (habilidades raras).
    if random.random() < cfg.get("ability", 0):
        for planner in (
            lambda: _plan_revive(game, bot, p, hand),
            lambda: _plan_ritual(game, bot, p, hand),
            lambda: _plan_oracle(game, bot, p, hand),
            lambda: _plan_flip(game, bot, p),
        ):
            step = planner()
            if step:
                actions.append(step)

    # 7) Atacar (respeitando a 1ª rodada)
    enemies = _living_enemies(game, bot)
    can_atk, _ = game.can_attack(bot)
    has_attacker = _has_attackers(atk)
    if any(
        a.get("action") == "play_card"
        and (a.get("params") or {}).get("position_type") == "attack"
        for a in actions
    ):
        has_attacker = True

    if can_atk and has_attacker and enemies and random.random() < cfg["attack"]:
        target = _choose_target(game, bot, enemies, cfg)
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
    elif action == "equip_item":
        result = game.equip_item_to_creature(
            bot,
            params.get("item_card_id"),
            params.get("creature_card_id"),
        )
        if result and result.get("success"):
            if getattr(game, "has_fog", lambda: False)():
                log = f"🔰 {bot} equipou um item (névoa)"
            else:
                log = (
                    f"🔰 {bot} equipou {result.get('item', 'um item')} "
                    f"em {result.get('creature', 'uma criatura')}"
                )
    elif action == "swap_positions":
        result = game.swap_positions(
            bot,
            params.get("pos1_type"), params.get("pos1_index"),
            params.get("pos2_type"), params.get("pos2_index"),
        )
        if result and result.get("success"):
            log = f"🔄 {bot} trocou posições de cartas"
    elif action == "toggle_time":
        result = game.toggle_time_of_day(bot)
        if result and result.get("success"):
            log = f"🔥 {bot} usou a Fênix (ciclo → {result.get('new_time', '?')})"
    elif action == "call_centaurs":
        result = game.call_centaurs(bot)
        if result and result.get("success"):
            log = f"🐎 {bot} chamou centauros ({result.get('centaurs_collected', 0)})"
    elif action == "prophet_curse":
        result = game.prophet_curse(
            bot, params.get("target_player_id"), params.get("target_card_id")
        )
        if result and result.get("success"):
            log = "🔮 " + bot + " usou a Maldição do Profeta"
    elif action == "cast_spell":
        result = game.cast_spell(
            bot,
            params.get("spell_id"),
            params.get("target_player_id"),
            params.get("target_card_id"),
        )
        if result and result.get("success"):
            spell = (result.get("spell") or {}).get("name", "um feitiço")
            log = f"✨ {bot} usou {spell}"
    elif action == "revive":
        result = game.revive_from_graveyard(bot, params.get("card_id"))
        if result and result.get("success"):
            log = f"🔄 {bot} reviveu uma carta do cemitério"
    elif action == "ritual":
        result = game.perform_ritual(
            bot, params.get("ritual_id"), params.get("target_player_id")
        )
        if result and result.get("success"):
            log = f"🕯️ {bot} realizou um ritual"
    elif action == "oracle":
        result = game.perform_oracle(bot, params.get("target_id"))
        if result and result.get("success"):
            log = f"👁️ {bot} usou o Oráculo"
    elif action == "flip_card":
        result = game.flip_card(
            bot, params.get("position_type"), params.get("position_index")
        )
        if result and result.get("success"):
            log = f"🔄 {bot} revelou uma carta"
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


def _persist_turn(game_id: str) -> None:
    """Salva o estado após a jogada do bot (restart não perde o turno)."""
    try:
        from twilight.game.persistence import snapshot_game
        snapshot_game(game_id)
    except Exception:
        pass


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
        _persist_turn(game_id)
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

    _persist_turn(game_id)

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
        _persist_turn(game_id)
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
