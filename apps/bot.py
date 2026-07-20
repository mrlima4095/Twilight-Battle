#!/usr/bin/env python3
"""
Twilight Battle — Bot multiplayer com chat e dificuldades.

Uso:
  python apps/bot.py --user grok --room VTI5Z2
  # URL padrão: https://game.opentty.fun
  # Senha pedida no terminal se omitir --password

  python apps/bot.py --user grok --password *** --room VTI5Z2 --difficulty hard

No terminal, digite mensagens e Enter para enviar no chat da sala.
Comandos locais:
  /quit     sair
  /state    mostrar resumo do estado
  /draw     forçar compra (se for seu turno)
  /end      forçar fim de turno
  /help     ajuda
"""

from __future__ import annotations

import argparse
import getpass
import random
import sys
import threading
import time
from typing import Any, Optional

DEFAULT_URL = "https://game.opentty.fun"

try:
    import requests
    import socketio
except ImportError:
    print(
        "Dependências faltando. Instale com:\n"
        "  pip install \"python-socketio[client]\" requests websocket-client\n"
        "ou use o venv do projeto:\n"
        "  python3 -m venv .venv && .venv/bin/pip install \"python-socketio[client]\" requests websocket-client"
    )
    sys.exit(1)

# websocket-client é obrigatório atrás de reverse-proxy (Coolify/nginx);
# sem ele o client só tenta polling e costuma falhar com
# "One or more namespaces failed to connect".
try:
    import websocket  # noqa: F401  # package: websocket-client
except ImportError:
    print(
        "[aviso] pacote websocket-client NÃO instalado.\n"
        "  Sem ele o Socket.IO só usa polling e a conexão costuma falhar.\n"
        "  Instale:  pip install websocket-client\n"
    )


# ---------------------------------------------------------------------------
# Valores de prioridade de criaturas (quanto maior, melhor)
# ---------------------------------------------------------------------------
CREATURE_VALUE = {
    "rei_mago": 1000,
    "mago_negro": 980,
    "apofis": 950,
    "vampiro_wers": 900,
    "vampiro_tayler": 850,
    "dragao": 800,
    "lobisomem": 720,
    "ninfa_lorem": 700,
    "vampiro": 650,
    "centauro": 600,
    "orc": 450,
    "mago": 500,
    "elfo": 420,
    "ninfa": 400,
    "zumbi": 200,
}

SPELL_PRIORITY = {
    # id -> base score (modulado em runtime)
    "feitico_cura": 80,
    "feitico_duro_matar": 70,
    "feitico_cortes": 90,
    "feitico_silencio": 75,
    "feitico_selo_silencio": 85,
    "feitico_julgamento_aurora": 88,
    "feitico_clareira_lua": 55,
    "feitico_troca": 60,
    "feitico_comunista": 40,
    "feitico_capitalista": 30,
    "feitico_para_sempre": 35,
    "feitico_eco_grimorio": 50,
}

NIGHT_CREATURE_IDS = {
    "zumbi",
    "vampiro",
    "vampiro_wers",
    "vampiro_tayler",
    "lobisomem",
}


def card_score(card: Optional[dict]) -> float:
    if not card:
        return 0.0
    cid = card.get("id") or ""
    base = CREATURE_VALUE.get(cid, 0)
    if not base:
        base = float(card.get("attack") or 0) + float(card.get("life") or 0) * 0.05
    # bônus de itens equipados
    for eq in card.get("equipped_items") or []:
        base += float(eq.get("attack") or 0) * 0.5
        base += float(eq.get("protection") or 0) * 0.3
    base += float(card.get("attack") or 0) * 0.15
    return base


def is_creature(card: Optional[dict]) -> bool:
    return bool(card and card.get("type") == "creature")


def is_trap(card: Optional[dict]) -> bool:
    return bool(card and card.get("type") == "trap")


def is_spell(card: Optional[dict]) -> bool:
    return bool(card and card.get("type") == "spell")


def is_weapon(card: Optional[dict]) -> bool:
    return bool(card and card.get("type") == "weapon")


def is_armor(card: Optional[dict]) -> bool:
    return bool(card and card.get("type") == "armor")


def empty_slots(bases: list) -> list[int]:
    return [i for i, c in enumerate(bases or []) if c is None]


def filled_creatures(bases: list) -> list[tuple[int, dict]]:
    out = []
    for i, c in enumerate(bases or []):
        if is_creature(c):
            out.append((i, c))
    return out


# ---------------------------------------------------------------------------
# Estratégia (estrategista: replan por ação, draw sempre, swap, hold noturno)
# ---------------------------------------------------------------------------
MAGE_IDS = frozenset({"mago", "rei_mago", "mago_negro"})
WEAPON_IDS = frozenset({"lamina_almas", "blade_vampires", "blade_dragons"})
TRAP_VALUE = {
    "armadilha_poco": 100,
    "armadilha_espelho": 90,
    "armadilha_171": 70,
    "armadilha_cheat": 60,
}
# Ações do motor → contador interno de limite
ACTION_BUCKET = {
    "draw": "draw",
    "play_card": "play",
    "attack": "attack",
    "swap_positions": "swap",
    "cast_spell": "spell",
    "call_centaurs": "call_centaurs",
    "prophet_curse": "prophet_curse",
    "equip_item": "equip_item",  # grátis no motor (sem limite de turno)
    "end_turn": "end_turn",
}


def is_night_creature(card: Optional[dict]) -> bool:
    if not card:
        return False
    cid = card.get("id") or ""
    return bool(
        card.get("dies_daylight")
        or card.get("night_creature")
        or card.get("werewolf")
        or cid in NIGHT_CREATURE_IDS
        or cid == "lobisomem_crepusculo"
        or "lobisomem" in cid
    )


def is_hidden_card(card: Optional[dict]) -> bool:
    if not card:
        return False
    return bool(
        card.get("hidden")
        or card.get("name") in ("???", "Silhueta")
    )


def has_sabedoria(me_data: dict, hand: list) -> bool:
    for c in hand + (me_data.get("talismans") or []):
        if c and c.get("id") == "talisma_sabedoria":
            return True
    return False


def attack_power(atk: list, equipment: dict, hand: list) -> float:
    power = 0.0
    has = False
    for c in atk:
        if not c:
            continue
        if is_creature(c) or c.get("_placeholder"):
            has = True
            power += float(c.get("attack") or 50)
    if not has:
        return 0.0
    w = equipment.get("weapon") if equipment else None
    if w:
        # adaga crepúsculo: valor efetivo aproximado no state
        power += float(w.get("attack") or w.get("night_attack") or w.get("day_attack") or 0)
    for t in hand or []:
        if t and t.get("id") == "talisma_guerreiro":
            power += 1024
    return power


def enemy_list(players: dict, me: str) -> list[tuple[str, dict]]:
    return [
        (uname, pdata)
        for uname, pdata in (players or {}).items()
        if uname != me and not pdata.get("dead") and not pdata.get("observer") and not pdata.get("spectator")
    ]


class Strategy:
    """Decide a próxima ação com base no estado fresco (closed-loop)."""

    def __init__(self, difficulty: str = "normal"):
        self.difficulty = (difficulty or "normal").lower().strip()
        if self.difficulty not in ("easy", "facil", "normal", "hard", "dificil", "difícil"):
            self.difficulty = "normal"
        if self.difficulty in ("facil",):
            self.difficulty = "easy"
        if self.difficulty in ("dificil", "difícil"):
            self.difficulty = "hard"

    @property
    def mistake_chance(self) -> float:
        return {"easy": 0.45, "normal": 0.12, "hard": 0.02}.get(self.difficulty, 0.12)

    @property
    def think_delay(self) -> tuple[float, float]:
        """Pausa ANTES de cada ação (parece humano, evita spam de alert no front)."""
        return {
            "easy": (1.0, 2.2),
            "normal": (0.7, 1.4),
            "hard": (0.55, 1.0),
        }.get(self.difficulty, (0.7, 1.4))

    @property
    def action_gap(self) -> float:
        """Pausa mínima DEPOIS de cada ação (>= 500ms)."""
        return {
            "easy": 0.9,
            "normal": 0.7,
            "hard": 0.55,
        }.get(self.difficulty, 0.7)

    def maybe_blunder(self) -> bool:
        return random.random() < self.mistake_chance

    def max_for(self, bucket: str, me_data: dict, hand: list) -> int:
        if bucket == "play":
            return 2 if has_sabedoria(me_data, hand) else 1
        if bucket == "equip_item":
            return 8  # motor não limita; cap anti-loop
        if bucket == "end_turn":
            return 1
        return 1

    def can_use(self, used: dict, bucket: str, me_data: dict, hand: list) -> bool:
        return int(used.get(bucket, 0)) < self.max_for(bucket, me_data, hand)

    def next_action(
        self,
        state: dict,
        me: str,
        used: Optional[dict] = None,
        attacks_blocked: bool = False,
        failed: Optional[set] = None,
    ) -> Optional[dict]:
        """
        Uma ação por chamada (closed-loop). Sempre tenta draw se ainda não usou.
        Retorna None se deve encerrar o loop (emite end_turn ou nada a fazer).
        """
        used = used if used is not None else {}
        failed = failed if failed is not None else set()

        if not state or not state.get("started") or state.get("finished"):
            return {"action": "end_turn", "params": {}, "reason": "not-playing"}

        players = state.get("players") or {}
        me_data = players.get(me)
        if not me_data or me_data.get("dead"):
            return None

        if state.get("current_turn") != me:
            return None

        hand = list(me_data.get("hand") or [])
        atk = list(me_data.get("attack_bases") or [])
        defense = list(me_data.get("defense_bases") or [])
        equipment = dict(me_data.get("equipment") or {})
        my_life = float(me_data.get("life") or 0)
        modifiers = set(state.get("modifiers") or [])
        time_of_day = state.get("time_of_day") or "day"
        atk_slots = int(state.get("attack_slot_count") or len(atk) or 3)
        def_slots = int(state.get("defense_slot_count") or len(defense) or 6)
        deck_count = int(state.get("deck_count") or 0)
        cycle_len = 6 if "fast_cycle" in modifiers else 24
        time_cycle = int(state.get("time_cycle") or 0)
        turns_to_flip = cycle_len - (time_cycle % cycle_len) if cycle_len else 99

        while len(atk) < atk_slots:
            atk.append(None)
        while len(defense) < def_slots:
            defense.append(None)

        enemies = enemy_list(players, me)
        force_attack = "bleed_out" in modifiers
        phase = self._phase(
            my_life, atk, defense, enemies, attack_power(atk, equipment, hand),
            attacks_blocked, force_attack,
        )

        # --- Easy: decisões ruidosas ---
        if self.difficulty == "easy" and self.maybe_blunder() and "easy-blunder" not in failed:
            # ainda assim draw se puder
            if self.can_use(used, "draw", me_data, hand) and deck_count > 0:
                return {"action": "draw", "params": {}, "reason": "easy-draw-first"}
            if hand and self.can_use(used, "play", me_data, hand) and random.random() < 0.55:
                c = random.choice([x for x in hand if is_creature(x) or is_trap(x)] or hand)
                if is_creature(c):
                    slots_a, slots_d = empty_slots(atk), empty_slots(defense)
                    if slots_a or slots_d:
                        ptype = "attack" if slots_a else "defense"
                        idx = (slots_a or slots_d)[0]
                        return {
                            "action": "play_card",
                            "params": {
                                "card_id": c["instance_id"],
                                "position_type": ptype,
                                "position_index": idx,
                            },
                            "reason": "easy-random-play",
                        }
                elif is_trap(c) and empty_slots(defense):
                    return {
                        "action": "play_card",
                        "params": {
                            "card_id": c["instance_id"],
                            "position_type": "defense",
                            "position_index": empty_slots(defense)[0],
                        },
                        "reason": "easy-trap",
                    }
            if (
                not attacks_blocked
                and self.can_use(used, "attack", me_data, hand)
                and any(is_creature(c) for c in atk)
                and enemies
                and random.random() < 0.4
            ):
                return {
                    "action": "attack",
                    "params": {"target_id": random.choice(enemies)[0]},
                    "reason": "easy-attack",
                }
            return {"action": "end_turn", "params": {}, "reason": "easy-end"}

        # ========== 1) DRAW SEMPRE que puder (mais opções no futuro) ==========
        if (
            self.can_use(used, "draw", me_data, hand)
            and deck_count > 0
            and "draw" not in failed
        ):
            return {"action": "draw", "params": {}, "reason": "draw-always"}

        # ========== 2) Equip em criaturas (não gasta play) ==========
        if self.can_use(used, "equip_item", me_data, hand) and "equip_item" not in failed:
            eq = self._pick_equip_creature(hand, atk, defense, equipment)
            if eq:
                return eq

        # ========== 3) Swap tático (alinhar board) ==========
        if (
            self.difficulty != "easy"
            and self.can_use(used, "swap", me_data, hand)
            and "swap_positions" not in failed
        ):
            sw = self._pick_swap(atk, defense, equipment, phase)
            if sw:
                return sw

        # ========== 4) Jogar carta ==========
        if self.can_use(used, "play", me_data, hand) and "play_card" not in failed:
            play = self._pick_play(
                hand, atk, defense, equipment, time_of_day, modifiers,
                turns_to_flip, phase, my_life,
            )
            if play:
                return play

        # ========== 5) Feitiço ==========
        if (
            self.can_use(used, "spell", me_data, hand)
            and "no_spells" not in modifiers
            and "cast_spell" not in failed
        ):
            has_mage = any(
                is_creature(c) and (c.get("id") in MAGE_IDS)
                for c in atk + defense
            )
            spells = [c for c in hand if is_spell(c)]
            if has_mage and spells:
                spell_action = self._pick_spell(
                    spells, me, me_data, enemies, atk, defense, my_life, time_of_day, modifiers
                )
                if spell_action:
                    return spell_action

        # ========== 6) Call centauros ==========
        if (
            self.difficulty == "hard"
            and self.can_use(used, "call_centaurs", me_data, hand)
            and "call_centaurs" not in failed
        ):
            centaur_count = sum(
                1 for c in atk + defense + hand if c and c.get("id") == "centauro"
            )
            if centaur_count >= 2:
                return {"action": "call_centaurs", "params": {}, "reason": "call-centaurs"}

        # ========== 7) Profecia (critério, não random) ==========
        if (
            self.difficulty == "hard"
            and "no_prophet" not in modifiers
            and self.can_use(used, "prophet_curse", me_data, hand)
            and "prophet_curse" not in failed
            and enemies
        ):
            curse = self._pick_prophet_curse(enemies)
            if curse:
                return curse

        # ========== 8) Ataque ==========
        if (
            not attacks_blocked
            and self.can_use(used, "attack", me_data, hand)
            and "attack" not in failed
            and enemies
        ):
            pwr = attack_power(atk, equipment, hand)
            has_attacker = any(is_creature(c) for c in atk)
            if has_attacker and (pwr > 0 or force_attack):
                want = force_attack or phase in ("lethal", "pressure") or pwr >= 80
                if phase == "setup":
                    want = force_attack
                if phase == "stabilize" and not force_attack:
                    # ataca se puder matar alguém
                    want = any(float(e[1].get("life") or 0) <= pwr for e in enemies)
                if self.difficulty == "easy" and self.maybe_blunder():
                    want = force_attack
                if want:
                    target = self._pick_attack_target(enemies, pwr, modifiers, me)
                    if target:
                        return {
                            "action": "attack",
                            "params": {"target_id": target},
                            "reason": f"attack-{target}-pwr{int(pwr)}-{phase}",
                        }

        # ========== 9) Fim de turno ==========
        return {"action": "end_turn", "params": {}, "reason": f"end-{phase}"}

    def plan_turn(
        self,
        state: dict,
        me: str,
        attacks_blocked: bool = False,
    ) -> list[dict]:
        """Compat: gera plano open-loop (pouco usado; preferir next_action)."""
        used: dict[str, int] = {}
        failed: set = set()
        actions: list[dict] = []
        for _ in range(16):
            step = self.next_action(state, me, used, attacks_blocked, failed)
            if not step:
                break
            actions.append(step)
            bucket = ACTION_BUCKET.get(step["action"], step["action"])
            used[bucket] = int(used.get(bucket, 0)) + 1
            if step["action"] == "end_turn":
                break
        return actions

    def _phase(
        self,
        my_life: float,
        atk: list,
        defense: list,
        enemies: list,
        my_power: float,
        attacks_blocked: bool,
        force_attack: bool,
    ) -> str:
        if attacks_blocked:
            return "setup"
        if enemies and any(float(e[1].get("life") or 0) <= my_power for e in enemies):
            return "lethal"
        if my_life < 350:
            return "stabilize"
        atk_n = len(filled_creatures(atk))
        if atk_n == 0:
            return "develop"
        if my_power >= 200 or force_attack:
            return "pressure"
        if atk_n < 2:
            return "develop"
        return "pressure"

    def _can_equip(self, item: dict, creature: dict) -> bool:
        iid = item.get("id") or ""
        cid = creature.get("id") or ""
        if iid == "blade_vampires" and cid not in ("vampiro_tayler", "vampiro_wers"):
            return False
        if iid == "blade_dragons" and cid not in (
            "elfo", "vampiro_tayler", "vampiro_wers", "mago", "mago_negro", "rei_mago",
        ):
            return False
        if iid == "lamina_almas" and cid not in (
            "elfo", "mago", "mago_negro", "rei_mago", "vampiro_tayler", "vampiro_wers",
        ):
            return False
        if iid == "adaga_crepusculo" or item.get("werewolf_only"):
            if not creature.get("werewolf") and cid not in ("lobisomem_crepusculo", "lobisomem"):
                return False
        if iid == "cajado_mago_negro":
            races = item.get("equip_races") or list(MAGE_IDS)
            if cid not in races:
                return False
        eqs = creature.get("equipped_items") or []
        if item.get("type") == "weapon" or iid in WEAPON_IDS:
            if any(e.get("type") == "weapon" or e.get("id") in WEAPON_IDS for e in eqs):
                return False
        if item.get("type") == "armor" or iid == "capacete_trevas":
            armor_n = sum(
                1 for e in eqs if e.get("type") == "armor" or e.get("id") == "capacete_trevas"
            )
            if armor_n >= 4:
                return False
        return True

    def _pick_equip_creature(
        self, hand: list, atk: list, defense: list, equipment: Optional[dict] = None
    ) -> Optional[dict]:
        creatures = filled_creatures(atk) + filled_creatures(defense)
        if not creatures:
            return None
        equipment = equipment or {}
        # itens com habilidade forte no slot do JOGADOR: não gastar em criatura
        # se o slot correspondente ainda está livre
        player_prefer = {
            "botas_andarilho": "boots",
            "calcas_marcha": "pants",
            "capacete_sentinela": "helmet",
            "manto_eclipse": "armor",
        }
        items = []
        for c in hand:
            if not (is_weapon(c) or is_armor(c)):
                continue
            cid = c.get("id") or ""
            slot = player_prefer.get(cid)
            if slot and not equipment.get(slot):
                continue  # reservar para play_card no slot do jogador
            items.append(c)
        if not items:
            return None
        creatures.sort(key=lambda x: card_score(x[1]), reverse=True)
        items_sorted = sorted(
            items,
            key=lambda c: float(c.get("attack") or 0) + float(c.get("protection") or 0),
            reverse=True,
        )
        for item in items_sorted:
            for _, creature in creatures:
                if self._can_equip(item, creature):
                    return {
                        "action": "equip_item",
                        "params": {
                            "item_card_id": item["instance_id"],
                            "creature_card_id": creature["instance_id"],
                        },
                        "reason": f"equip-{item.get('name')}-on-{creature.get('name')}",
                    }
        return None

    def _pick_swap(
        self, atk: list, defense: list, equipment: dict, phase: str
    ) -> Optional[dict]:
        """Troca para maximizar ATK no ataque e proteger mago/tank em defesa."""
        atk_filled = filled_creatures(atk)
        def_filled = filled_creatures(defense)
        empty_atk = empty_slots(atk)
        empty_def = empty_slots(defense)

        # 1) Melhor criatura de defesa → ataque se ataque fraco / lethal
        if atk_filled or empty_atk:
            if def_filled and (empty_atk or atk_filled):
                best_def = max(def_filled, key=lambda x: float(x[1].get("attack") or 0))
                def_atk = float(best_def[1].get("attack") or 0)
                if empty_atk and def_atk >= 60 and phase in ("pressure", "lethal", "develop"):
                    return {
                        "action": "swap_positions",
                        "params": {
                            "pos1_type": "defense",
                            "pos1_index": best_def[0],
                            "pos2_type": "attack",
                            "pos2_index": empty_atk[0],
                        },
                        "reason": f"swap-def-to-atk-{best_def[1].get('name')}",
                    }
                if atk_filled:
                    worst_atk = min(atk_filled, key=lambda x: float(x[1].get("attack") or 0))
                    if def_atk > float(worst_atk[1].get("attack") or 0) + 20:
                        return {
                            "action": "swap_positions",
                            "params": {
                                "pos1_type": "defense",
                                "pos1_index": best_def[0],
                                "pos2_type": "attack",
                                "pos2_index": worst_atk[0],
                            },
                            "reason": f"swap-upgrade-atk-{best_def[1].get('name')}",
                        }

        # 2) Mago em ataque com vida baixa → defesa (proteger caster)
        for i, c in atk_filled:
            if (c.get("id") in MAGE_IDS) and float(c.get("life") or 0) < 300 and empty_def:
                return {
                    "action": "swap_positions",
                    "params": {
                        "pos1_type": "attack",
                        "pos1_index": i,
                        "pos2_type": "defense",
                        "pos2_index": empty_def[0],
                    },
                    "reason": f"swap-protect-mage-{c.get('name')}",
                }

        # 3) Criatura fraca em ataque e tank em defesa
        if phase == "stabilize" and atk_filled and empty_def:
            weak = min(atk_filled, key=lambda x: float(x[1].get("life") or 0))
            if float(weak[1].get("life") or 0) < 200:
                return {
                    "action": "swap_positions",
                    "params": {
                        "pos1_type": "attack",
                        "pos1_index": weak[0],
                        "pos2_type": "defense",
                        "pos2_index": empty_def[0],
                    },
                    "reason": f"swap-shelter-{weak[1].get('name')}",
                }
        return None

    def _should_hold_night(
        self, c: dict, time_of_day: str, turns_to_flip: int
    ) -> bool:
        if not is_night_creature(c):
            return False
        if time_of_day == "night":
            return False
        if self.difficulty == "easy":
            return False
        # hard: segura a menos que a noite esteja muito perto (1 turno)
        if self.difficulty == "hard":
            return turns_to_flip > 1
        # normal: segura se faltar mais de 3 turnos
        return turns_to_flip > 3

    def _creature_priority(
        self, c: dict, time_of_day: str, turns_to_flip: int, hand: list, atk: list, defense: list
    ) -> float:
        s = card_score(c)
        cid = c.get("id") or ""
        if self._should_hold_night(c, time_of_day, turns_to_flip):
            s -= 800
        elif time_of_day == "night" and is_night_creature(c):
            s += 220
        if cid in MAGE_IDS:
            # mago ainda mais se tem spell na mão e nenhum mago em campo
            has_mage = any(
                is_creature(x) and x.get("id") in MAGE_IDS for x in atk + defense
            )
            has_spell = any(is_spell(x) for x in hand)
            s += 280 if (has_spell and not has_mage) else 160
        if cid == "centauro":
            s += 80
        return s

    def _pick_player_equipment(
        self, hand: list, equipment: dict, atk: list, defense: list, phase: str
    ) -> Optional[dict]:
        """Equipar no slot do jogador (gasta play)."""
        # slots: weapon, helmet, armor, pants, boots, mount
        candidates: list[tuple[float, dict, str]] = []

        for c in hand:
            if not c:
                continue
            ctype = c.get("type")
            cid = c.get("id") or ""
            slot = c.get("slot")

            if ctype == "weapon" and not equipment.get("weapon"):
                atk_v = float(c.get("attack") or 0)
                # preferir arma forte no jogador se board de atk cheio ou lethal
                pri = atk_v
                if phase == "lethal":
                    pri += 100
                if empty_slots(atk) and any(is_creature(x) for x in hand):
                    pri -= 80  # prefere board
                if atk_v >= 50:
                    candidates.append((pri, c, "weapon"))
            elif ctype == "armor" and slot in ("helmet", "armor", "pants", "boots"):
                if equipment.get(slot):
                    continue
                prot = float(c.get("protection") or 0)
                pri = prot
                # botas andarilho: swap grátis = muito valor tático
                if cid == "botas_andarilho":
                    pri += 200
                if cid == "calcas_marcha":
                    pri += 80
                if cid == "manto_eclipse":
                    pri += 60
                # se há criatura e item também serve nela, às vezes melhor equip_item
                # mas botas/calças preferem slot jogador
                if cid in ("botas_andarilho", "calcas_marcha", "capacete_sentinela"):
                    candidates.append((pri, c, slot))
                elif not filled_creatures(atk) and not filled_creatures(defense):
                    candidates.append((pri * 0.8, c, slot))
            elif ctype == "creature" and not equipment.get("mount") and cid == "centauro":
                # montaria só se sobra centauro e ataque cheio
                if not empty_slots(atk) and not empty_slots(defense):
                    candidates.append((40.0, c, "mount"))

        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0], reverse=True)
        pri, card, slot = candidates[0]
        if pri < 40 and self.difficulty == "hard":
            return None
        return {
            "action": "play_card",
            "params": {
                "card_id": card["instance_id"],
                "position_type": "equipment",
                "position_index": slot,
            },
            "reason": f"player-eq-{slot}-{card.get('name')}",
        }

    def _pick_play(
        self,
        hand: list,
        atk: list,
        defense: list,
        equipment: dict,
        time_of_day: str,
        modifiers: set,
        turns_to_flip: int,
        phase: str,
        my_life: float,
    ) -> Optional[dict]:
        creatures = [
            c for c in hand
            if is_creature(c) and not self._should_hold_night(c, time_of_day, turns_to_flip)
        ]
        # se só tem noturnos e dia, easy/normal ainda pode jogar
        if not creatures:
            creatures = [c for c in hand if is_creature(c)]
            if self.difficulty == "hard" and time_of_day == "day":
                # hard: só joga noturno se não há alternativa E board vazio crítico
                only_night = all(is_night_creature(c) for c in creatures) if creatures else False
                if only_night and filled_creatures(atk):
                    creatures = []  # segura
                elif only_night and turns_to_flip > 1:
                    creatures = []

        traps = [c for c in hand if is_trap(c)]
        empty_atk = empty_slots(atk)
        empty_def = empty_slots(defense)

        def cprio(c: dict) -> float:
            return self._creature_priority(c, time_of_day, turns_to_flip, hand, atk, defense)

        # prioridade: board de ataque > trap > defesa > equip jogador
        need_attack = bool(empty_atk)
        need_defense = len(filled_creatures(defense)) == 0 and bool(empty_def)
        has_mage_field = any(
            is_creature(c) and c.get("id") in MAGE_IDS for c in atk + defense
        )
        spells_in_hand = any(is_spell(c) for c in hand)

        # mago se tem spell e sem mago
        if need_attack and creatures and spells_in_hand and not has_mage_field:
            mages = [c for c in creatures if c.get("id") in MAGE_IDS]
            if mages:
                best = max(mages, key=cprio)
                return {
                    "action": "play_card",
                    "params": {
                        "card_id": best["instance_id"],
                        "position_type": "attack",
                        "position_index": empty_atk[0],
                    },
                    "reason": f"play-mage-{best.get('name')}",
                }

        if need_attack and creatures:
            best = max(creatures, key=cprio)
            # se score muito negativo (hold), pula
            if cprio(best) > -200 or self.difficulty == "easy":
                return {
                    "action": "play_card",
                    "params": {
                        "card_id": best["instance_id"],
                        "position_type": "attack",
                        "position_index": empty_atk[0],
                    },
                    "reason": f"play-atk-{best.get('name')}",
                }

        if traps and empty_def and self.difficulty != "easy":
            trap = max(traps, key=lambda t: TRAP_VALUE.get(t.get("id"), 50))
            return {
                "action": "play_card",
                "params": {
                    "card_id": trap["instance_id"],
                    "position_type": "defense",
                    "position_index": empty_def[0],
                },
                "reason": f"play-trap-{trap.get('name')}",
            }

        if need_defense and creatures:
            tank = max(
                creatures,
                key=lambda c: float(c.get("life") or 0) - float(c.get("attack") or 0) * 0.2,
            )
            return {
                "action": "play_card",
                "params": {
                    "card_id": tank["instance_id"],
                    "position_type": "defense",
                    "position_index": empty_def[0],
                },
                "reason": f"play-def-{tank.get('name')}",
            }

        if empty_atk and creatures:
            best = max(creatures, key=cprio)
            if cprio(best) > -200 or self.difficulty != "hard":
                return {
                    "action": "play_card",
                    "params": {
                        "card_id": best["instance_id"],
                        "position_type": "attack",
                        "position_index": empty_atk[0],
                    },
                    "reason": f"play-atk2-{best.get('name')}",
                }

        if empty_def and creatures:
            c = max(creatures, key=cprio)
            return {
                "action": "play_card",
                "params": {
                    "card_id": c["instance_id"],
                    "position_type": "defense",
                    "position_index": empty_def[0],
                },
                "reason": f"play-def2-{c.get('name')}",
            }

        # equipamento no jogador se não há play de board
        peq = self._pick_player_equipment(hand, equipment, atk, defense, phase)
        if peq:
            return peq

        return None

    def _pick_spell(
        self,
        spells: list,
        me: str,
        me_data: dict,
        enemies: list,
        atk: list,
        defense: list,
        my_life: float,
        time_of_day: str,
        modifiers: set,
    ) -> Optional[dict]:
        scored: list[tuple[float, dict, dict]] = []
        my_creatures = [c for _, c in filled_creatures(atk) + filled_creatures(defense)]
        best_my = max(my_creatures, key=card_score) if my_creatures else None

        for sp in spells:
            sid = sp.get("id") or ""
            base = float(SPELL_PRIORITY.get(sid, 20))
            params: dict[str, Any] = {"spell_id": sp.get("instance_id") or sid}

            if sid == "feitico_cura":
                if my_life < 900:
                    base += (900 - my_life) / 10
                    params["target_player_id"] = me
                else:
                    base -= 40
            elif sid == "feitico_duro_matar":
                params["target_player_id"] = me
                if my_life < 700:
                    base += 30
            elif sid == "feitico_cortes" and best_my:
                params["target_card_id"] = best_my.get("instance_id")
                params["target_player_id"] = me
                base += card_score(best_my) * 0.05
            elif sid in ("feitico_silencio", "feitico_selo_silencio"):
                if any(is_creature(c) for c in atk):
                    base += 25
                params["target_player_id"] = me
            elif sid == "feitico_julgamento_aurora":
                night_target = None
                for uname, pdata in enemies:
                    for c in (pdata.get("attack_bases") or []) + (pdata.get("defense_bases") or []):
                        if not c or is_hidden_card(c):
                            continue
                        if is_night_creature(c):
                            night_target = (uname, c)
                            break
                    if night_target:
                        break
                if night_target:
                    params["target_player_id"] = night_target[0]
                    params["target_card_id"] = night_target[1].get("instance_id")
                    base += 40
                else:
                    base -= 50
            elif sid == "feitico_clareira_lua":
                if time_of_day == "day" and any(is_night_creature(c) for c in my_creatures):
                    base += 40
                else:
                    base -= 20
            elif sid == "feitico_troca" and enemies:
                best_enemy = max(
                    enemies,
                    key=lambda e: sum(1 for c in (e[1].get("attack_bases") or []) if c),
                )
                if sum(1 for c in (best_enemy[1].get("attack_bases") or []) if c) >= 2:
                    params["target_player_id"] = best_enemy[0]
                    base += 25
                else:
                    base -= 30
            elif sid == "feitico_comunista":
                if len(me_data.get("hand") or []) <= 2:
                    base += 20
                else:
                    base -= 25

            if base > 30:
                scored.append((base, sp, params))

        if not scored:
            return None
        scored.sort(key=lambda x: x[0], reverse=True)
        score, sp, params = scored[0]
        if self.difficulty == "normal" and score < 50:
            return None
        return {
            "action": "cast_spell",
            "params": params,
            "reason": f"spell-{sp.get('name')}-s{int(score)}",
        }

    def _pick_attack_target(
        self,
        enemies: list,
        my_power: float,
        modifiers: set,
        me: str,
    ) -> Optional[str]:
        if not enemies:
            return None

        def threat(entry):
            uname, pdata = entry
            life = float(pdata.get("life") or 0)
            atk_power_e = 0.0
            hidden_defs = 0
            for c in pdata.get("attack_bases") or []:
                if is_creature(c) and not is_hidden_card(c):
                    atk_power_e += float(c.get("attack") or 0)
            for c in pdata.get("defense_bases") or []:
                if c:
                    if is_hidden_card(c):
                        hidden_defs += 1
            defs = sum(1 for c in (pdata.get("defense_bases") or []) if c)
            killable = 1 if life <= my_power else 0
            # menos defesa e menos ocultos = melhor alvo
            return (killable, -life, atk_power_e, -defs, -hidden_defs)

        if self.difficulty == "easy":
            return random.choice(enemies)[0]

        enemies_sorted = sorted(enemies, key=threat, reverse=True)
        return enemies_sorted[0][0]

    def _pick_prophet_curse(self, enemies: list) -> Optional[dict]:
        best = None
        best_score = 0.0
        for uname, pdata in enemies:
            for c in (pdata.get("attack_bases") or []) + (pdata.get("defense_bases") or []):
                if not c or not is_creature(c) or is_hidden_card(c):
                    continue
                sc = card_score(c)
                # bônus se está em ataque (ameaça direta)
                atk_ids = {
                    x.get("instance_id")
                    for x in (pdata.get("attack_bases") or [])
                    if x
                }
                if c.get("instance_id") in atk_ids:
                    sc += 50
                if sc > best_score:
                    best_score = sc
                    best = (uname, c)
        if best and best_score >= 450:
            return {
                "action": "prophet_curse",
                "params": {
                    "target_player_id": best[0],
                    "target_card_id": best[1].get("instance_id"),
                },
                "reason": f"curse-{best[1].get('name')}",
            }
        return None


# ---------------------------------------------------------------------------
# Bot client
# ---------------------------------------------------------------------------
class TwilightBot:
    def __init__(
        self,
        url: str,
        username: str,
        password: str,
        room: str,
        difficulty: str = "normal",
        auto_play: bool = True,
    ):
        self.url = url.rstrip("/")
        self.username = username.strip().lower()
        self.password = password
        self.room = room.strip()
        self.strategy = Strategy(difficulty)
        self.auto_play = auto_play

        self.token: Optional[str] = None
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "TwilightBattleBot/1.1",
                "Accept": "*/*",
            }
        )
        # http_session repassa cookies do login pro handshake do engine.io
        self.sio = socketio.Client(
            reconnection=True,
            reconnection_attempts=10,
            reconnection_delay=1,
            reconnection_delay_max=8,
            logger=False,
            engineio_logger=False,
            http_session=self.session,
        )

        self.game_state: Optional[dict] = None
        self.joined = False
        self.playing_turn = False
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._last_action_error = ""
        self._last_action_ok = False
        # chave do turno que já executamos por completo (user+cycle)
        self._turn_done_for: Optional[str] = None
        self._last_seen_turn: Optional[str] = None
        # primeira rodada: False por padrão; vira True se o server recusar ataque
        # (evita travar se o bot entrar no meio da partida)
        self._attacks_blocked = False
        # contadores de ações do turno atual
        self._used: dict[str, int] = {}
        self._failed: set = set()
        self._turn_key_active: Optional[str] = None

        self._register_handlers()

    # --- HTTP auth ---
    def login(self) -> bool:
        try:
            r = self.session.post(
                f"{self.url}/api/login",
                json={"username": self.username, "password": self.password},
                timeout=15,
            )
        except requests.RequestException as e:
            print(f"[erro] login request: {e}")
            return False

        if r.status_code != 200:
            print(f"[erro] login HTTP {r.status_code}: {r.text[:200]}")
            return False

        data = r.json()
        if not data.get("success"):
            print(f"[erro] login: {data.get('message', data)}")
            return False

        # extrair token do cookie (mesmo se Secure — requests às vezes não reenvia em http)
        self.token = self.session.cookies.get("auth_token")
        if not self.token:
            # fallback: Set-Cookie header
            for c in r.cookies:
                if c.name == "auth_token":
                    self.token = c.value
                    break
        if not self.token:
            # parse manual
            sc = r.headers.get("Set-Cookie", "")
            if "auth_token=" in sc:
                part = sc.split("auth_token=", 1)[1]
                self.token = part.split(";", 1)[0].strip()

        if not self.token:
            print("[erro] login ok mas sem auth_token no cookie")
            return False

        # garantir cookie na session mesmo em HTTP
        self.session.cookies.set("auth_token", self.token, path="/")
        print(f"[ok] logado como {self.username}")
        return True

    def _new_sio_client(self) -> "socketio.Client":
        return socketio.Client(
            reconnection=True,
            reconnection_attempts=10,
            reconnection_delay=1,
            reconnection_delay_max=8,
            logger=False,
            engineio_logger=False,
            http_session=self.session,
        )

    def connect(self) -> bool:
        headers = {
            "Cookie": f"auth_token={self.token}",
            "User-Agent": "TwilightBattleBot/1.1",
        }
        # Força cookie também na jar (domínio do host)
        try:
            from urllib.parse import urlparse

            host = urlparse(self.url).hostname or "game.opentty.fun"
            self.session.cookies.set("auth_token", self.token, domain=host, path="/")
        except Exception:
            self.session.cookies.set("auth_token", self.token, path="/")

        # polling primeiro é mais estável atrás de alguns proxies;
        # websocket puro vem em seguida se polling falhar
        has_ws = True
        try:
            import websocket  # noqa: F401
        except ImportError:
            has_ws = False

        attempts = []
        if has_ws:
            attempts.append({"transports": ["polling", "websocket"], "label": "polling→websocket"})
            attempts.append({"transports": ["websocket"], "label": "websocket"})
        attempts.append({"transports": ["polling"], "label": "polling"})

        last_err: Optional[Exception] = None
        for attempt in attempts:
            try:
                # client limpo a cada tentativa (estado sujo após falha)
                try:
                    if getattr(self, "sio", None) and self.sio.connected:
                        self.sio.disconnect()
                except Exception:
                    pass
                self.sio = self._new_sio_client()
                self._register_handlers()

                print(f"[...] socket via {attempt['label']} → {self.url}")
                self.sio.connect(
                    self.url,
                    headers=headers,
                    transports=attempt["transports"],
                    wait_timeout=20,
                    socketio_path="socket.io",
                    wait=True,
                )
                if self.sio.connected:
                    print(f"[ok] socket conectado ({attempt['label']}) sid={self.sio.sid}")
                    return True
            except Exception as e:
                last_err = e
                print(f"[aviso] falhou {attempt['label']}: {e}")
                time.sleep(0.3)

        print(f"[erro] socket connect: {last_err}")
        if not has_ws:
            print(
                "Falta o pacote websocket-client (causa comum de 'namespaces failed'):\n"
                "  pip install websocket-client"
            )
        else:
            print(
                "Dica: confira URL HTTPS e se o servidor está no ar:\n"
                f"  {self.url}"
            )
        return False

    def join_room(self):
        print(f"[...] entrando na sala {self.room} ...")
        self.sio.emit("join_game", {"game_id": self.room})
        # também pedir estado periodicamente
        time.sleep(0.3)
        self.sio.emit("get_game_state", {"game_id": self.room})
        self.sio.emit("get_chat_history", {"game_id": self.room})

    def send_chat(self, message: str):
        message = (message or "").strip()
        if not message:
            return
        if len(message) > 500:
            message = message[:500]
        self.sio.emit(
            "send_chat_message",
            {"game_id": self.room, "message": message},
        )

    def do_action(self, action: str, params: Optional[dict] = None) -> None:
        payload = {
            "game_id": self.room,
            "action": action,
            "params": params or {},
        }
        self.sio.emit("player_action", payload)

    def request_state(self):
        if self.sio.connected:
            self.sio.emit("get_game_state", {"game_id": self.room})

    # --- handlers ---
    def _register_handlers(self):
        @self.sio.event
        def connect():
            print("[socket] connected")

        @self.sio.event
        def disconnect():
            print("[socket] disconnected")

        @self.sio.event
        def connect_error(data):
            print(f"[socket] connect_error: {data}")

        @self.sio.on("error")
        def on_error(data):
            print(f"[server error] {data}")

        @self.sio.on("player_joined")
        def on_player_joined(data):
            players = data.get("players") or []
            names = [p.get("username") or p.get("name") for p in players]
            print(f"[sala] jogadores: {', '.join(names)}")
            if data.get("username") == self.username:
                self.joined = True
            self.request_state()

        @self.sio.on("reconnect_success")
        def on_reconnect(data):
            print(f"[sala] reconectado: {data.get('message', 'ok')}")
            self.joined = True
            self.request_state()

        @self.sio.on("game_started")
        def on_started(data):
            print("[jogo] PARTIDA INICIADA!")
            mods = set()
            if isinstance(data, dict):
                mods = set(data.get("modifiers") or [])
            st = self.game_state or {}
            mods = mods or set(st.get("modifiers") or [])
            # com no_first_round: ataca livre; senão assume bloqueado até first_round_ended
            self._attacks_blocked = "no_first_round" not in mods
            self._used = {}
            self._failed = set()
            self._turn_key_active = None
            self.request_state()

        @self.sio.on("game_state")
        def on_state(data):
            with self._lock:
                self.game_state = data
            if data.get("finished") or data.get("winner"):
                if data.get("winner"):
                    print(f"\n*** FIM (state): vencedor={data.get('winner_name') or data.get('winner')} ***\n")
                self.auto_play = False
                self._turn_done_for = "FINISHED"
                return
            # se o state já tem mods com no_first_round
            if "no_first_round" in set(data.get("modifiers") or []):
                self._attacks_blocked = False
            # não bloquear o event loop do socketio
            if (
                self.auto_play
                and not self.playing_turn
                and data.get("started")
                and data.get("current_turn") == self.username
            ):
                threading.Thread(target=self._maybe_play, daemon=True).start()

        @self.sio.on("action_success")
        def on_action_success(data):
            log = data.get("log_message") or ""
            action = data.get("action")
            who = data.get("player_name") or data.get("player_id")
            if who == self.username or data.get("player_id") == self.username:
                self._last_action_ok = True
                self._last_action_error = ""
            if log:
                print(f"[ação] {log}")
            elif action:
                print(f"[ação] {who}: {action}")
            if data.get("first_round_ended"):
                self._attacks_blocked = False
                print("[jogo] primeira rodada acabou — ataques liberados")
            self.request_state()

        @self.sio.on("action_error")
        def on_action_error(data):
            msg = data.get("message") or str(data)
            self._last_action_error = msg
            self._last_action_ok = False
            if data.get("game_finished"):
                print(f"[fim] partida já terminou ({msg})")
                self.auto_play = False
                self._turn_done_for = "FINISHED"
                return
            low = msg.lower()
            if "primeira rodada" in low or "ataques bloqueados" in low:
                self._attacks_blocked = True
            # não spammar tudo
            if data.get("player_name") == self.username or data.get("player_id") == self.username:
                print(f"[ação falhou] {msg}")
            self.request_state()

        @self.sio.on("chat_message")
        def on_chat(data):
            user = data.get("username") or "?"
            msg = data.get("message") or ""
            sys_flag = data.get("is_system")
            prefix = "[sys]" if sys_flag else f"<{user}>"
            print(f"{prefix} {msg}")

        @self.sio.on("chat_history")
        def on_chat_history(data):
            msgs = data.get("messages") or []
            if msgs:
                print("--- histórico do chat ---")
                for m in msgs[-15:]:
                    u = m.get("username") or "?"
                    print(f"  <{u}> {m.get('message')}")
                print("-------------------------")

        @self.sio.on("chat_error")
        def on_chat_error(data):
            print(f"[chat erro] {data.get('message')}")

        @self.sio.on("game_over")
        def on_game_over(data):
            print(f"\n*** FIM DE JOGO: {data.get('message')} ***\n")
            self.auto_play = False
            self._turn_done_for = "FINISHED"
            self._stop.set()

        @self.sio.on("player_died")
        def on_died(data):
            print(f"[💀] {data}")

        @self.sio.on("room_closed")
        def on_closed(data):
            print(f"[sala fechada] {data.get('message')}")
            self.auto_play = False
            self._stop.set()

        @self.sio.on("first_round_ended")
        def on_first_round(data):
            self._attacks_blocked = False
            print(f"[jogo] {data.get('message', 'primeira rodada acabou')}")

        @self.sio.on("turn_changed")
        def on_turn(data):
            self.request_state()

    def _turn_key(self, state: dict) -> str:
        return f"{self.username}|{state.get('time_cycle')}|{state.get('current_turn')}"

    def _wait_action_result(self, timeout: float = 2.5) -> bool:
        """Espera action_success/error ou timeout. Retorna True se sucesso."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._last_action_ok:
                return True
            if self._last_action_error:
                return False
            if self._stop.is_set():
                return False
            time.sleep(0.05)
        # timeout: assume ok se não houve erro explícito (rede lenta)
        return not bool(self._last_action_error)

    def _maybe_play(self):
        """Closed-loop: a cada passo reavalia o estado e escolhe a próxima ação."""
        if not self.auto_play:
            return
        with self._lock:
            if self.playing_turn:
                return
            state = self.game_state
            if not state or not state.get("started"):
                return

            current = state.get("current_turn")
            if current != self.username:
                if self._last_seen_turn == self.username:
                    self._turn_done_for = None
                self._last_seen_turn = current
                return

            self._last_seen_turn = current
            me = (state.get("players") or {}).get(self.username)
            if not me or me.get("dead"):
                return

            key = self._turn_key(state)
            if self._turn_done_for == key:
                return
            self.playing_turn = True
            # reset contadores se mudou de turno
            if self._turn_key_active != key:
                self._used = {}
                self._failed = set()
                self._turn_key_active = key

        try:
            time.sleep(0.15)
            self.request_state()
            time.sleep(0.25)
            state = self.game_state or state
            if state.get("current_turn") != self.username:
                return

            if "no_first_round" in set(state.get("modifiers") or []):
                self._attacks_blocked = False

            print(
                f"[bot] meu turno — closed-loop ({self.strategy.difficulty})"
                f"{' [setup/1ª rodada]' if self._attacks_blocked else ''}"
            )

            steps = 0
            max_steps = 18
            while steps < max_steps and not self._stop.is_set():
                st = self.game_state or {}
                if st.get("current_turn") != self.username:
                    break
                if st.get("finished"):
                    break
                me_now = (st.get("players") or {}).get(self.username) or {}
                if me_now.get("dead"):
                    break

                step = self.strategy.next_action(
                    st,
                    self.username,
                    used=self._used,
                    attacks_blocked=self._attacks_blocked,
                    failed=self._failed,
                )
                if not step:
                    break

                action = step["action"]
                params = step.get("params") or {}
                reason = step.get("reason") or ""
                print(f"  → {action} {params}  ({reason})")

                lo, hi = self.strategy.think_delay
                # draw é rápido; decisões de ataque/play pensam mais
                if action == "draw":
                    lo, hi = max(0.35, lo * 0.6), max(0.55, hi * 0.7)
                elif action in ("attack", "cast_spell", "swap_positions"):
                    lo, hi = lo * 1.1, hi * 1.25
                time.sleep(random.uniform(lo, hi))

                self._last_action_error = ""
                self._last_action_ok = False
                self.do_action(action, params)

                gap = max(0.5, self.strategy.action_gap)
                time.sleep(gap + random.uniform(0.0, 0.2))
                ok = self._wait_action_result(timeout=2.2)

                bucket = ACTION_BUCKET.get(action, action)
                if ok:
                    self._used[bucket] = int(self._used.get(bucket, 0)) + 1
                    # limpa falha prévia desse tipo se passou
                    self._failed.discard(action)
                else:
                    # marca falha para não loopar a mesma ação
                    self._failed.add(action)
                    err = (self._last_action_error or "").lower()
                    if "já comprou" in err or "já jogou" in err or "já atacou" in err:
                        self._used[bucket] = self.strategy.max_for(
                            bucket, me_now, me_now.get("hand") or []
                        )
                    if "primeira rodada" in err or "ataques bloqueados" in err:
                        self._attacks_blocked = True
                    print(f"  ⚠ falhou ({self._last_action_error or 'timeout'}); reavaliando")

                # pede estado fresco e espera um pouco
                self.request_state()
                time.sleep(0.2)
                steps += 1

                if action == "end_turn":
                    break

            self._turn_done_for = key
        except Exception as e:
            print(f"[bot] erro no turno: {e}")
            import traceback

            traceback.print_exc()
        finally:
            self.playing_turn = False

    def print_state_summary(self):
        st = self.game_state
        if not st:
            print("(sem estado ainda)")
            return
        print(f"started={st.get('started')} turn={st.get('current_turn')} time={st.get('time_of_day')}")
        print(f"mods={st.get('modifiers')} deck={st.get('deck_count')}")
        for uname, p in (st.get("players") or {}).items():
            mark = " ← VOCÊ" if uname == self.username else ""
            atk_n = sum(1 for c in (p.get("attack_bases") or []) if c)
            def_n = sum(1 for c in (p.get("defense_bases") or []) if c)
            hand_n = len(p.get("hand") or []) if uname == self.username else "?"
            print(
                f"  {uname}: ❤️{p.get('life')} atk={atk_n} def={def_n} hand={hand_n}"
                f"{' 💀' if p.get('dead') else ''}{mark}"
            )
        me = (st.get("players") or {}).get(self.username)
        if me and me.get("hand"):
            print("  mão:")
            for c in me["hand"]:
                print(
                    f"    - {c.get('name')} [{c.get('type')}] "
                    f"atk={c.get('attack')} life={c.get('life')} id={c.get('instance_id')}"
                )

    def run_chat_loop(self):
        print(
            "\n=== Bot pronto. Digite para falar no chat. /help para comandos. ===\n"
        )
        while not self._stop.is_set():
            try:
                line = input()
            except (EOFError, KeyboardInterrupt):
                print("\n[saindo]")
                break
            line = (line or "").rstrip("\n")
            if not line:
                continue
            if line.startswith("/"):
                cmd = line.strip().split()
                name = cmd[0].lower()
                if name in ("/quit", "/exit", "/q"):
                    break
                if name == "/help":
                    print(
                        "Comandos: /quit /state /draw /end /play /refresh /help\n"
                        "Qualquer outra linha vai pro chat da sala."
                    )
                elif name == "/state":
                    self.print_state_summary()
                elif name == "/draw":
                    self.do_action("draw", {})
                elif name == "/end":
                    self.do_action("end_turn", {})
                elif name == "/refresh":
                    self.request_state()
                elif name == "/play":
                    # forçar reavaliar turno
                    self._turn_done_for = None
                    threading.Thread(target=self._maybe_play, daemon=True).start()
                else:
                    print(f"comando desconhecido: {name}")
                continue
            self.send_chat(line)

    def ping_loop(self):
        while not self._stop.is_set():
            try:
                if self.sio.connected:
                    self.sio.emit(
                        "ping_game",
                        {"game_id": self.room, "player_id": self.username},
                    )
                    # refresh estado
                    self.request_state()
            except Exception:
                pass
            self._stop.wait(20)

    def start(self) -> int:
        if not self.login():
            return 1
        if not self.connect():
            return 1
        self.join_room()

        t = threading.Thread(target=self.ping_loop, daemon=True)
        t.start()

        try:
            self.run_chat_loop()
        finally:
            self._stop.set()
            try:
                if self.sio.connected:
                    self.sio.emit("leave_game", {"game_id": self.room})
                    time.sleep(0.2)
                    self.sio.disconnect()
            except Exception:
                pass
        return 0


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Twilight Battle multiplayer bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemplos:\n"
            "  python apps/bot.py --user grok --room VTI5Z2\n"
            "  python apps/bot.py --user grok --password *** --room VTI5Z2 -d hard\n"
            f"  (URL padrão: {DEFAULT_URL})\n"
        ),
    )
    p.add_argument(
        "--url",
        default=DEFAULT_URL,
        help=f"URL do servidor (default: {DEFAULT_URL})",
    )
    p.add_argument(
        "--user",
        "--username",
        dest="username",
        default=None,
        help="Username da conta (pede no terminal se omitir)",
    )
    p.add_argument(
        "--password",
        default=None,
        help="Senha da conta (se omitir, pede com input oculto)",
    )
    p.add_argument(
        "--room",
        "--game",
        dest="room",
        default=None,
        help="ID da sala (pede no terminal se omitir)",
    )
    p.add_argument(
        "--difficulty",
        "-d",
        default="hard",
        choices=["easy", "facil", "normal", "hard", "dificil"],
        help="Dificuldade (default: hard)",
    )
    p.add_argument(
        "--no-auto",
        action="store_true",
        help="Não joga automaticamente (só chat + comandos manuais)",
    )
    return p.parse_args(argv)


def _prompt_missing(args):
    """Preenche url/user/password/room interativamente se faltarem."""
    url = (args.url or "").strip() or DEFAULT_URL
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    args.url = url.rstrip("/")

    if not (args.username or "").strip():
        args.username = input("Username: ").strip()
    if not args.username:
        print("[erro] username obrigatório")
        sys.exit(1)

    if not args.password:
        # getpass esconde a senha; se falhar (IDE sem TTY), cai no input normal
        try:
            args.password = getpass.getpass(f"Senha para {args.username}: ")
        except Exception:
            args.password = input(f"Senha para {args.username}: ")
    if not args.password:
        print("[erro] senha obrigatória")
        sys.exit(1)

    if not (args.room or "").strip():
        args.room = input("ID da sala: ").strip()
    if not args.room:
        print("[erro] room id obrigatório")
        sys.exit(1)

    return args


def main(argv=None):
    args = _prompt_missing(parse_args(argv))
    print(f"[cfg] url={args.url} user={args.username} room={args.room} diff={args.difficulty}")
    bot = TwilightBot(
        url=args.url,
        username=args.username,
        password=args.password,
        room=args.room,
        difficulty=args.difficulty,
        auto_play=not args.no_auto,
    )
    raise SystemExit(bot.start())


if __name__ == "__main__":
    main()
