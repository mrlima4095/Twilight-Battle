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
# Estratégia
# ---------------------------------------------------------------------------
class Strategy:
    """Decide ações com base na dificuldade."""

    def __init__(self, difficulty: str = "normal"):
        self.difficulty = (difficulty or "normal").lower().strip()
        if self.difficulty not in ("easy", "facil", "normal", "hard", "dificil", "difícil"):
            self.difficulty = "normal"
        # normalizar
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

    def plan_turn(self, state: dict, me: str) -> list[dict]:
        """
        Retorna lista ordenada de ações:
          {action, params, reason}
        """
        if not state or not state.get("started"):
            return []

        players = state.get("players") or {}
        me_data = players.get(me)
        if not me_data or me_data.get("dead"):
            return []

        if state.get("current_turn") != me:
            return []

        hand = list(me_data.get("hand") or [])
        atk = list(me_data.get("attack_bases") or [])
        defense = list(me_data.get("defense_bases") or [])
        equipment = dict(me_data.get("equipment") or {})
        my_life = float(me_data.get("life") or 0)
        modifiers = set(state.get("modifiers") or [])
        time_of_day = state.get("time_of_day") or "day"
        atk_slots = int(state.get("attack_slot_count") or len(atk) or 3)
        def_slots = int(state.get("defense_slot_count") or len(defense) or 6)

        # garantir tamanho das listas
        while len(atk) < atk_slots:
            atk.append(None)
        while len(defense) < def_slots:
            defense.append(None)

        enemies = [
            (uname, pdata)
            for uname, pdata in players.items()
            if uname != me and not pdata.get("dead") and not pdata.get("observer")
        ]

        actions: list[dict] = []

        # --- Easy: às vezes só compra e passa / joga aleatório ---
        if self.difficulty == "easy" and self.maybe_blunder():
            if hand and random.random() < 0.5:
                c = random.choice([x for x in hand if is_creature(x) or is_trap(x)] or hand)
                if is_creature(c):
                    slots = empty_slots(atk) or empty_slots(defense)
                    if slots:
                        ptype = "attack" if empty_slots(atk) else "defense"
                        actions.append(
                            {
                                "action": "play_card",
                                "params": {
                                    "card_id": c["instance_id"],
                                    "position_type": ptype,
                                    "position_index": slots[0],
                                },
                                "reason": "easy-random-play",
                            }
                        )
                elif is_trap(c) and empty_slots(defense):
                    actions.append(
                        {
                            "action": "play_card",
                            "params": {
                                "card_id": c["instance_id"],
                                "position_type": "defense",
                                "position_index": empty_slots(defense)[0],
                            },
                            "reason": "easy-trap",
                        }
                    )
            actions.append({"action": "draw", "params": {}, "reason": "easy-draw"})
            # às vezes ataca aleatório
            if any(is_creature(c) for c in atk) and enemies and random.random() < 0.4:
                target = random.choice(enemies)[0]
                actions.append(
                    {
                        "action": "attack",
                        "params": {"target_id": target},
                        "reason": "easy-attack",
                    }
                )
            actions.append({"action": "end_turn", "params": {}, "reason": "easy-end"})
            return actions

        # ========== HARD / NORMAL: ordem tática ==========
        # 1) Draw cedo se mão fraca
        playable = [c for c in hand if is_creature(c) or is_trap(c) or is_weapon(c) or is_armor(c) or is_spell(c)]
        should_draw_first = len(hand) < 3 or (len(playable) == 0 and len(hand) < 6)
        if should_draw_first:
            actions.append({"action": "draw", "params": {}, "reason": "draw-early"})

        # 2) Equipar itens da mão em criaturas fortes
        creatures_on_field = filled_creatures(atk) + filled_creatures(defense)
        items = [c for c in hand if is_weapon(c) or is_armor(c)]
        if creatures_on_field and items and self.difficulty != "easy":
            # melhor criatura primeiro
            creatures_on_field.sort(key=lambda x: card_score(x[1]), reverse=True)
            for item in sorted(items, key=lambda c: float(c.get("attack") or c.get("protection") or 0), reverse=True):
                best_creature = None
                for _, creature in creatures_on_field:
                    if self._can_equip(item, creature):
                        best_creature = creature
                        break
                if best_creature:
                    actions.append(
                        {
                            "action": "equip_item",
                            "params": {
                                "item_card_id": item["instance_id"],
                                "creature_card_id": best_creature["instance_id"],
                            },
                            "reason": f"equip-{item.get('name')}-on-{best_creature.get('name')}",
                        }
                    )
                    # remove da mão local para não reusar
                    hand = [c for c in hand if c.get("instance_id") != item.get("instance_id")]
                    if self.difficulty == "normal":
                        break  # normal: 1 equip por turno

        # 2b) Arma no slot do JOGADOR só se não há criatura boa p/ jogar
        #     (play_card gasta a ação de "play" do turno)
        weapons = [c for c in hand if is_weapon(c)]
        creatures_in_hand = [c for c in hand if is_creature(c)]
        want_player_weapon = (
            weapons
            and not equipment.get("weapon")
            and (not creatures_in_hand or not empty_slots(atk))
            and self.difficulty != "easy"
        )
        if want_player_weapon:
            w = max(weapons, key=lambda c: float(c.get("attack") or 0))
            # só se a arma for forte o suficiente
            if float(w.get("attack") or 0) >= 50:
                actions.append(
                    {
                        "action": "play_card",
                        "params": {
                            "card_id": w["instance_id"],
                            "position_type": "equipment",
                            "position_index": "weapon",
                        },
                        "reason": f"player-weapon-{w.get('name')}",
                    }
                )
                hand = [c for c in hand if c.get("instance_id") != w.get("instance_id")]

        # 3) Feitiços (se tiver mago em campo)
        has_mage = any(
            is_creature(c) and (c.get("id") in ("mago", "rei_mago", "mago_negro"))
            for c in atk + defense
        )
        spells = [c for c in hand if is_spell(c)]
        if has_mage and spells and "no_spells" not in modifiers:
            spell_action = self._pick_spell(
                spells, me, me_data, enemies, atk, defense, my_life, time_of_day, modifiers
            )
            if spell_action:
                actions.append(spell_action)
                hand = [
                    c
                    for c in hand
                    if c.get("instance_id") != spell_action["params"].get("spell_id")
                ]

        # 4) Jogar carta (prioridade tática)
        play = self._pick_play(hand, atk, defense, time_of_day, modifiers)
        if play:
            actions.append(play)
            # simular no local
            p = play["params"]
            # marcar slot ocupado mentalmente com stats da carta
            played = next(
                (c for c in hand if c.get("instance_id") == p.get("card_id")),
                None,
            )
            if p["position_type"] == "attack":
                idx = p["position_index"]
                if 0 <= idx < len(atk):
                    if played:
                        atk[idx] = dict(played)
                        atk[idx]["_placeholder"] = True
                    else:
                        atk[idx] = {"_placeholder": True, "type": "creature", "attack": 50}
            elif p["position_type"] == "defense":
                idx = p["position_index"]
                if 0 <= idx < len(defense):
                    defense[idx] = played or {"_placeholder": True}

        # 4b) Second play se Talismã da Sabedoria (hand still has cards - try opportunistic)
        has_sabedoria = any(
            c and c.get("id") == "talisma_sabedoria"
            for c in (hand + (me_data.get("talismans") or []))
        )
        if has_sabedoria:
            play2 = self._pick_play(
                [c for c in hand if c.get("instance_id") != (play or {}).get("params", {}).get("card_id")],
                atk,
                defense,
                time_of_day,
                modifiers,
            )
            if play2:
                actions.append(play2)

        # 5) Call centaurs se tiver 2+ centauros
        centaur_count = sum(
            1
            for c in atk + defense + hand
            if c and c.get("id") == "centauro"
        )
        if centaur_count >= 2 and self.difficulty == "hard":
            actions.append(
                {"action": "call_centaurs", "params": {}, "reason": "call-centaurs"}
            )

        # 6) Prophet curse em ameaça forte (hard)
        if (
            self.difficulty == "hard"
            and "no_prophet" not in modifiers
            and enemies
            and random.random() < 0.55
        ):
            curse = self._pick_prophet_curse(enemies)
            if curse:
                actions.append(curse)

        # 7) Ataque (board já inclui placeholders das plays planejadas)
        my_atk_power = 0.0
        has_attacker = False
        for c in atk:
            if not c:
                continue
            if is_creature(c) or c.get("_placeholder"):
                has_attacker = True
                my_atk_power += float(c.get("attack") or 50)
        if equipment.get("weapon"):
            my_atk_power += float(equipment["weapon"].get("attack") or 0)
        for t in hand:
            if t and t.get("id") == "talisma_guerreiro":
                my_atk_power += 1024

        can_attack = has_attacker and bool(enemies)
        # bleed_out: SEMPRE atacar se possível
        force_attack = "bleed_out" in modifiers

        if can_attack and (my_atk_power > 0 or force_attack):
            target = self._pick_attack_target(enemies, my_atk_power, modifiers, me)
            if target:
                if not (self.difficulty == "easy" and self.maybe_blunder()):
                    actions.append(
                        {
                            "action": "attack",
                            "params": {"target_id": target},
                            "reason": f"attack-{target}-pwr{int(my_atk_power)}",
                        }
                    )
                elif force_attack:
                    actions.append(
                        {
                            "action": "attack",
                            "params": {"target_id": target},
                            "reason": "bleed-force-attack",
                        }
                    )

        # 8) Draw se ainda não pediu e mão pequena
        if not should_draw_first and len(hand) < 7:
            actions.append({"action": "draw", "params": {}, "reason": "draw-late"})

        # 9) End turn
        actions.append({"action": "end_turn", "params": {}, "reason": "end"})

        # Easy/normal: chance de dropar o ataque ou o play
        if self.difficulty != "hard" and self.maybe_blunder():
            actions = [
                a
                for a in actions
                if a["action"] not in ("attack", "cast_spell", "prophet_curse")
                or random.random() > 0.5
            ]
            if not any(a["action"] == "end_turn" for a in actions):
                actions.append({"action": "end_turn", "params": {}, "reason": "end"})

        return actions

    def _can_equip(self, item: dict, creature: dict) -> bool:
        iid = item.get("id") or ""
        cid = creature.get("id") or ""
        if iid == "blade_vampires" and cid not in ("vampiro_tayler", "vampiro_wers"):
            return False
        if iid == "blade_dragons" and cid not in (
            "elfo",
            "vampiro_tayler",
            "vampiro_wers",
            "mago",
            "mago_negro",
            "rei_mago",
        ):
            return False
        if iid == "lamina_almas" and cid not in (
            "elfo",
            "mago",
            "mago_negro",
            "rei_mago",
            "vampiro_tayler",
            "vampiro_wers",
        ):
            return False
        # já tem arma?
        eqs = creature.get("equipped_items") or []
        weapon_ids = {"lamina_almas", "blade_vampires", "blade_dragons"}
        if item.get("type") == "weapon" or iid in weapon_ids:
            if any(e.get("type") == "weapon" or e.get("id") in weapon_ids for e in eqs):
                return False
        return True

    def _pick_play(
        self,
        hand: list,
        atk: list,
        defense: list,
        time_of_day: str,
        modifiers: set,
    ) -> Optional[dict]:
        creatures = [c for c in hand if is_creature(c)]
        traps = [c for c in hand if is_trap(c)]
        empty_atk = empty_slots(atk)
        empty_def = empty_slots(defense)

        if not creatures and not traps:
            return None

        # valor das criaturas — evitar zumbi de dia se hard
        def creature_priority(c: dict) -> float:
            s = card_score(c)
            cid = c.get("id") or ""
            if time_of_day == "day" and (
                c.get("dies_daylight") or cid in NIGHT_CREATURE_IDS
            ):
                s -= 400 if self.difficulty == "hard" else 150
            if time_of_day == "night" and cid in NIGHT_CREATURE_IDS:
                s += 200
            # magos são valiosos para feitiços
            if cid in ("mago", "rei_mago", "mago_negro"):
                s += 180
            # centauro bom
            if cid == "centauro":
                s += 80
            return s

        # Hard: priorizar encher ataque com melhores criaturas, 1 defesa se vazio
        need_defense = len(filled_creatures(defense)) == 0 and empty_def
        need_attack = bool(empty_atk)

        if need_attack and creatures:
            best = max(creatures, key=creature_priority)
            # se só tem slot defesa e criatura fraca, etc.
            return {
                "action": "play_card",
                "params": {
                    "card_id": best["instance_id"],
                    "position_type": "attack",
                    "position_index": empty_atk[0],
                },
                "reason": f"play-atk-{best.get('name')}",
            }

        # armadilhas em defesa (prioridade hard)
        if traps and empty_def and self.difficulty != "easy":
            trap = traps[0]
            # hard: prefere poço e espelho
            if self.difficulty == "hard":
                traps_sorted = sorted(
                    traps,
                    key=lambda t: {
                        "armadilha_poco": 100,
                        "armadilha_espelho": 90,
                        "armadilha_171": 70,
                        "armadilha_cheat": 60,
                    }.get(t.get("id"), 50),
                    reverse=True,
                )
                trap = traps_sorted[0]
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
            # defesa: criatura tank (mais vida / menos ataque relativo) ou qualquer
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

        # se ainda tem slots de ataque e criaturas
        if empty_atk and creatures:
            best = max(creatures, key=creature_priority)
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
            c = max(creatures, key=creature_priority)
            return {
                "action": "play_card",
                "params": {
                    "card_id": c["instance_id"],
                    "position_type": "defense",
                    "position_index": empty_def[0],
                },
                "reason": f"play-def2-{c.get('name')}",
            }

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
        scored: list[tuple[float, dict, dict]] = []  # score, spell, params

        my_creatures = [c for _, c in filled_creatures(atk) + filled_creatures(defense)]
        best_my = max(my_creatures, key=card_score) if my_creatures else None

        for sp in spells:
            sid = sp.get("id") or ""
            base = SPELL_PRIORITY.get(sid, 20)
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
                # achar criatura noturna inimiga
                night_target = None
                for uname, pdata in enemies:
                    for c in (pdata.get("attack_bases") or []) + (pdata.get("defense_bases") or []):
                        if not c or c.get("hidden") or c.get("name") in ("???", "Silhueta"):
                            continue
                        cid = c.get("id") or ""
                        if (
                            cid in NIGHT_CREATURE_IDS
                            or c.get("dies_daylight")
                            or c.get("night_creature")
                            or c.get("werewolf")
                        ):
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
                if time_of_day == "day" and any(
                    (c.get("id") in NIGHT_CREATURE_IDS or c.get("werewolf") or c.get("dies_daylight"))
                    for c in my_creatures
                ):
                    base += 40
                else:
                    base -= 20
            elif sid == "feitico_troca" and enemies:
                # trocar board do inimigo mais armado em ataque
                best_enemy = max(
                    enemies,
                    key=lambda e: sum(
                        1 for c in (e[1].get("attack_bases") or []) if c
                    ),
                )
                if sum(1 for c in (best_enemy[1].get("attack_bases") or []) if c) >= 2:
                    params["target_player_id"] = best_enemy[0]
                    base += 25
                else:
                    base -= 30
            elif sid == "feitico_comunista":
                # se mão inimiga parece grande (não sabemos) — só se mão própria fraca
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
            atk_power = 0.0
            for c in pdata.get("attack_bases") or []:
                if is_creature(c):
                    atk_power += float(c.get("attack") or 0)
            # preferir matar se possível
            killable = 1 if life <= my_power else 0
            # king_hunt: priorizar criador se soubermos — não temos creator no state
            # board fraco = menos defesas
            defs = sum(1 for c in (pdata.get("defense_bases") or []) if c)
            # score: matar > low life > high threat
            return (killable, -life, atk_power, -defs)

        if self.difficulty == "easy":
            return random.choice(enemies)[0]

        enemies_sorted = sorted(enemies, key=threat, reverse=True)
        return enemies_sorted[0][0]

    def _pick_prophet_curse(self, enemies: list) -> Optional[dict]:
        best = None
        best_score = 0.0
        for uname, pdata in enemies:
            for c in (pdata.get("attack_bases") or []) + (pdata.get("defense_bases") or []):
                if not c or not is_creature(c):
                    continue
                # fog pode esconder stats
                if c.get("name") in ("???", "Silhueta") or c.get("hidden"):
                    continue
                sc = card_score(c)
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
                "User-Agent": "TwilightBattleBot/1.0",
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
        # chave do turno que já executamos por completo (user+cycle)
        self._turn_done_for: Optional[str] = None
        self._last_seen_turn: Optional[str] = None

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
            "User-Agent": "TwilightBattleBot/1.0",
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
            if log:
                print(f"[ação] {log}")
            elif action:
                print(f"[ação] {who}: {action}")
            # se outro jogador acabou o turno, puxar estado (pode ser nossa vez)
            if action == "end_turn" or who != self.username:
                self.request_state()
            else:
                self.request_state()

        @self.sio.on("action_error")
        def on_action_error(data):
            msg = data.get("message") or str(data)
            self._last_action_error = msg
            if data.get("game_finished"):
                print(f"[fim] partida já terminou ({msg})")
                self.auto_play = False
                self._turn_done_for = "FINISHED"
                return
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
            print(f"[jogo] {data.get('message', 'primeira rodada acabou')}")

        @self.sio.on("turn_changed")
        def on_turn(data):
            self.request_state()

    def _turn_key(self, state: dict) -> str:
        return f"{state.get('current_turn')}|{state.get('time_cycle')}|{state.get('deck_count')}"

    def _maybe_play(self):
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

            key = f"{self.username}|{state.get('time_cycle')}"
            if self._turn_done_for == key:
                return
            self.playing_turn = True

        try:
            # snapshot fresco
            time.sleep(0.15)
            self.request_state()
            time.sleep(0.25)
            state = self.game_state or state
            if state.get("current_turn") != self.username:
                return

            plan = self.strategy.plan_turn(state, self.username)
            if not plan:
                return

            print(f"[bot] meu turno — {len(plan)} passos ({self.strategy.difficulty})")
            for step in plan:
                if self._stop.is_set():
                    break
                st = self.game_state or {}
                if st.get("current_turn") != self.username:
                    break
                me_now = (st.get("players") or {}).get(self.username) or {}
                if me_now.get("dead"):
                    break

                action = step["action"]
                params = step.get("params") or {}
                reason = step.get("reason") or ""
                print(f"  → {action} {params}  ({reason})")

                lo, hi = self.strategy.think_delay
                time.sleep(random.uniform(lo, hi))

                self._last_action_error = ""
                self.do_action(action, params)
                # gap mínimo ~500ms+ entre ações (evita flood de Swal/estado)
                gap = max(0.5, self.strategy.action_gap)
                time.sleep(gap + random.uniform(0.0, 0.25))

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
