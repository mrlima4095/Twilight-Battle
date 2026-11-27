"""Motor da partida multiplayer (classe Game)."""
import random
import time
from random import shuffle
import uuid

from twilight.cards.deck import create_deck, get_random_disguise
from twilight.cards.definitions import BEAST_CREATURE_IDS, CARDS, CREATURE_ITEM_SLOTS
from twilight.extensions import socketio
from twilight.game.chat import broadcast_system_message
from twilight.game.rituals import RitualManager

class Game:
    def __init__(self, game_id, creator, config=None):
        # Configurações da sala
        self.config = config or {}
        self.max_players = self.config.get('max_players', 6)  # Padrão 6
        self.allow_spectators = self.config.get('allow_spectators', True)
        self.private = self.config.get('private', False)
        self.modifiers = self.config.get('modifiers', [])  # Lista de modificadores ativos
        self.chat_enabled = self.config.get('chat_enabled', True)

        self.game_id = game_id
        self.creator = creator
        self.players = []  # Lista de usernames
        self.player_data = {}  # Dict com username como chave
        self.socket_to_username = {}  # Mapeamento socket.id -> username
        self.deck = create_deck(self.modifiers)
        self.graveyard = []
        self.started = False
        self.finished = False  # True quando há vencedor — trava ações
        self.finished_at = None  # timestamp do fim (para cleanup da sala)
        self.winner = None
        # Reaper: atividade para detectar salas abandonadas / turnos travados
        self.created_at = time.time()
        self.last_action_at = self.created_at
        self.empty_since = None  # quando todos os humanos desconectaram
        self.current_turn = 0  # Índice na lista players
        self.time_of_day = "day"
        self.time_cycle = 0
        # cache dos efeitos dia/noite: evita recalcular todo turno sem mudança
        self._last_day_effects_signature = None
        # respeita config (antes era sobrescrito para 6 sempre)
        self.max_players = int(self.config.get('max_players', 6) or 6)
        self.turn_actions_used = {}
        self.turn_extra_actions = {}
        self.last_spell_id = None  # para Eco do Grimório
        # Ciclo dia/noite: 24 normal, 6 com fast_cycle
        self.day_cycle_length = 6 if 'fast_cycle' in self.modifiers else 24
        # Tutorial 1v1 com mentor (IA fácil)
        self.tutorial = bool(self.config.get('tutorial', False))
        # Dificuldade padrão dos bots adicionados pelo dono da sala.
        self.bot_difficulty = str(self.config.get('bot_difficulty') or 'normal').lower()

        self.first_round = True
        self.players_acted = set()
        self.attacks_blocked = True
        if 'no_first_round' in self.modifiers:
            self.first_round = False
            self.attacks_blocked = False

        # Tamanhos de board
        self.attack_slot_count = 5 if 'war_front' in self.modifiers else 3
        self.defense_slot_count = 1 if 'open_field' in self.modifiers else 6
        # Vida inicial (padrão 1200; hardcore 600)
        self.starting_life = 600 if 'hardcore' in self.modifiers else 1200
        # Mão inicial
        if 'empty_hand' in self.modifiers:
            self.starting_hand_size = 0
        elif 'big_hand' in self.modifiers:
            self.starting_hand_size = 8
        else:
            self.starting_hand_size = 5
    
    def get_player_by_socket(self, socket_id):
        """Retorna o username associado a um socket_id"""
        return self.socket_to_username.get(socket_id)
    def get_socket_id(self, username):
        """Retorna o socket_id atual de um username"""
        for socket_id, uname in self.socket_to_username.items():
            if uname == username:
                return socket_id
        return None
    
    def _make_player_state(self, username, socket_id=None, deal_hand=True):
        """Estado limpo de um jogador (lobby / rematch)."""
        hand = []
        if deal_hand:
            for _ in range(getattr(self, 'starting_hand_size', 5)):
                if self.deck:
                    hand.append(self.deck.pop())

        atk_n = getattr(self, 'attack_slot_count', 3)
        def_n = getattr(self, 'defense_slot_count', 6)
        start_life = getattr(self, 'starting_life', 1200)

        return {
            'name': username,
            'username': username,
            'socket_id': socket_id,
            'life': start_life,
            'hand': hand,
            'attack_bases': [None] * atk_n,
            'defense_bases': [None] * def_n,
            'equipment': {
                'weapon': None,
                'helmet': None,
                'armor': None,
                'pants': None,
                'boots': None,
                'mount': None
            },
            'talismans': [],
            'inventory': [],
            'runes': 0,
            'active_effects': [],
            'profecia_alvo': None,
            'profecia_rodadas': 0,
            'dead': False,
            'observer': False,
            'spectator': False,
            'free_swap_used': False,
            'first_hit_reduced': False,
            'attacked_this_turn': False,
        }

    @staticmethod
    def _default_card_life(card):
        """Vida padrão da carta (original_life, definição ou vida atual)."""
        if not card:
            return 0
        if card.get('original_life') is not None:
            try:
                return int(card['original_life'])
            except (TypeError, ValueError):
                pass
        base = CARDS.get(card.get('id'), {})
        try:
            return int(base.get('life') or card.get('life') or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _ensure_ability_charges(card):
        """Inicializa contadores de habilidades limitadas ao entrar em campo."""
        if card and card.get('id') == 'medusa':
            card.setdefault('medusa_petrify_uses', 2)

    @staticmethod
    def _is_ninfa(card):
        return bool(card and card.get('id') in ('ninfa', 'ninfa_lorem'))

    @staticmethod
    def _is_armor_item(item):
        return bool(item and (item.get('type') == 'armor' or item.get('id') == 'capacete_trevas'))

    @staticmethod
    def _is_weapon_item(item):
        return bool(item and (
            item.get('type') == 'weapon'
            or item.get('id') in ('lamina_almas', 'blade_vampires', 'blade_dragons')
        ))

    @staticmethod
    def _is_beast_creature(card):
        return bool(card and (
            card.get('beast_form') or card.get('id') in BEAST_CREATURE_IDS
        ))

    @classmethod
    def _item_slot(cls, item):
        """Slot canônico de um item em criatura (uma peça por slot)."""
        if not item:
            return None
        slot = item.get('slot')
        if slot in CREATURE_ITEM_SLOTS:
            return slot
        if cls._is_weapon_item(item):
            return 'weapon'
        if cls._is_armor_item(item):
            text = f"{item.get('id', '')} {item.get('name', '')}".lower()
            if 'capacete' in text or 'helmet' in text:
                return 'helmet'
            if 'peitoral' in text or 'armadura' in text or 'manto' in text:
                return 'armor'
            if 'calç' in text or 'calca' in text or 'pants' in text:
                return 'pants'
            if 'bota' in text or 'boot' in text:
                return 'boots'
            return 'armor'
        return None

    def _init_armor_durability(self, item):
        """Durabilidade da armadura = proteção/vida que ela deu ao equipar."""
        if not self._is_armor_item(item):
            return
        if item.get('durability') is None:
            max_durability = int(item.get('protection') or item.get('life') or 0)
            item['max_durability'] = max_durability
            item['durability'] = max_durability

    def _armor_is_pristine(self, item):
        """Só pode ser removida se nunca absorveu dano."""
        if not self._is_armor_item(item):
            return True
        self._init_armor_durability(item)
        try:
            return int(item.get('durability') or 0) >= int(item.get('max_durability') or 0)
        except (TypeError, ValueError):
            return False

    def _damage_armor(self, card, amount):
        """Registra o dano recebido na durabilidade das armaduras equipadas."""
        if not card or amount <= 0:
            return []
        depleted = []
        for item in card.get('equipped_items') or []:
            if amount <= 0:
                break
            if not self._is_armor_item(item):
                continue
            self._init_armor_durability(item)
            try:
                current = int(item.get('durability') or 0)
            except (TypeError, ValueError):
                current = 0
            if current <= 0:
                continue
            spent = min(current, amount)
            item['durability'] = current - spent
            amount -= spent
            if item['durability'] == 0:
                depleted.append(item.get('name', 'Armadura'))
        return depleted

    def _cancel_phoenix_eggs(self, phoenix_instance_id):
        """Cancela ovos de uma Fênix específica (revivida por outra pessoa)."""
        if not phoenix_instance_id:
            return
        for player in self.player_data.values():
            inventory = player.get('inventory') or []
            player['inventory'] = [
                item for item in inventory
                if not (
                    item.get('id') == 'ovo_fenix'
                    and item.get('phoenix_instance_id') == phoenix_instance_id
                )
            ]

    def _handle_non_attack_death(self, player, base_name, index, card, cause='luz do sol'):
        """Morte fora de ataque: sempre cemitério; Fênix ainda pode deixar o ovo."""
        if not player or not card:
            return None
        self.graveyard.append(card)
        player[base_name][index] = None
        info = {'card': card, 'phoenix_egg': False}
        if card.get('id') == 'fenix' and not card.get('phoenix_rebirth_used'):
            self._give_phoenix_egg(player, card)
            info['phoenix_egg'] = True
        return info

    def _lose_phoenix_eggs_on_card_reset(self):
        """O feitiço que devolve as mãos ao deck também destrói ovos de Fênix."""
        lost = []
        for player in self.player_data.values():
            inventory = player.get('inventory') or []
            kept = []
            for item in inventory:
                if item.get('id') != 'ovo_fenix':
                    kept.append(item)
                    continue
                instance_id = item.get('phoenix_instance_id')
                for card in self.graveyard:
                    if (
                        card.get('instance_id') == instance_id
                        and card.get('id') == 'fenix'
                    ):
                        card['phoenix_egg_lost'] = True
                lost.append(player['name'])
            player['inventory'] = kept
        if lost:
            broadcast_system_message(
                self.game_id,
                f'🥚 O feitiço destruiu o Ovo de Fênix de {", ".join(lost)} — a Fênix não volta!',
                fog_message='🥚 Um ovo foi destruído por um feitiço.',
            )
        return lost

    def _give_phoenix_egg(self, player, fenix_card):
        """Cria o ovo com contador de 10 turnos; a habilidade só vale uma vez."""
        if not player or not fenix_card or fenix_card.get('phoenix_rebirth_used'):
            return
        fenix_card['phoenix_rebirth_used'] = True

        instance_id = fenix_card.get('instance_id')
        inventory = player.setdefault('inventory', [])
        if any(
            item.get('id') == 'ovo_fenix' and item.get('phoenix_instance_id') == instance_id
            for item in inventory
        ):
            return

        inventory.append({
            'id': 'ovo_fenix',
            'name': '🥚 Ovo de Fênix',
            'description': 'Clique para ver quantos turnos faltam para a Fênix renascer.',
            'turns_remaining': 10,
            'phoenix_instance_id': instance_id,
        })
        broadcast_system_message(
            self.game_id,
            f"🥚 {player['name']} recebeu o Ovo de Fênix: a Fênix pode renascer em 10 turnos!",
            fog_message=f"🥚 Um ovo misterioso apareceu para {player['name']}.",
        )

    def add_player(self, socket_id, username):
        """Adiciona um jogador ao jogo usando username como identificador"""
        # Lobby (ou pós-rematch): started False permite entrar
        if len(self.players) >= self.max_players or self.started:
            return False
        
        # Verificar se username já está no jogo
        if username in self.players:
            return False
        
        self.players.append(username)
        self.socket_to_username[socket_id] = username
        self.player_data[username] = self._make_player_state(username, socket_id, deal_hand=True)
        
        return True

    def reset_to_lobby(self, last_winner=None):
        """
        Após o fim da partida: volta a sala para o lobby (mesma id, mods, creator).
        Mantém jogadores e sockets; recria baralho e estados.
        """
        last_winner = last_winner or self.winner
        # preserva espectadores e flags de bot
        spectators = {
            u: dict(d)
            for u, d in (self.player_data or {}).items()
            if d and d.get('spectator')
        }
        bot_flags = {
            u: {
                'is_bot': bool(d.get('is_bot')),
                'name': d.get('name') or u,
                'bot_difficulty': d.get('bot_difficulty') or 'easy',
            }
            for u, d in (self.player_data or {}).items()
            if d and d.get('is_bot')
        }
        # quem ainda está na lista de jogadores
        active = list(self.players)
        sockets = dict(self.socket_to_username)

        self.started = False
        self.finished = False
        self.finished_at = None
        self.winner = None
        self.last_winner = last_winner
        self._game_over_emitted = False
        self.deck = create_deck(self.modifiers)
        self.graveyard = []
        self.current_turn = 0
        self.time_of_day = "day"
        self.time_cycle = 0
        self._last_day_effects_signature = None
        self.turn_actions_used = {}
        self.turn_extra_actions = {}
        self.last_spell_id = None

        self.first_round = True
        self.players_acted = set()
        self.attacks_blocked = True
        if 'no_first_round' in self.modifiers:
            self.first_round = False
            self.attacks_blocked = False

        self.player_data = {}
        self.socket_to_username = {}

        for username in active:
            # recupera socket se ainda mapeado
            sock = None
            for sid, uname in sockets.items():
                if uname == username:
                    sock = sid
                    break
            if sock is not None:
                self.socket_to_username[sock] = username
            self.player_data[username] = self._make_player_state(
                username, sock, deal_hand=True
            )
            # restaura bots de tutorial / IA
            if username in bot_flags:
                self.player_data[username]['is_bot'] = True
                self.player_data[username]['name'] = bot_flags[username].get('name') or username
                self.player_data[username]['bot_difficulty'] = (
                    bot_flags[username].get('bot_difficulty') or 'easy'
                )

        # reanexa espectadores
        for uname, data in spectators.items():
            if uname in self.player_data:
                continue
            sock = None
            for sid, u in sockets.items():
                if u == uname:
                    sock = sid
                    break
            if sock is not None:
                self.socket_to_username[sock] = uname
            data = dict(data)
            data['socket_id'] = sock
            data['spectator'] = True
            self.player_data[uname] = data

        self.players = [p for p in active if p in self.player_data]
        return {
            'last_winner': last_winner,
            'players': list(self.players),
            'started': self.started,
            'finished': self.finished,
            'modifiers': list(self.modifiers or []),
            'game_id': self.game_id,
            'creator': self.creator,
        }
    def add_spectator(self, socket_id, username):
        """Adiciona um espectador ao jogo"""
        if username in self.players or username in self.player_data:
            return False, "Jogador já está na partida"
        
        # Adicionar como espectador
        self.socket_to_username[socket_id] = username
        
        self.player_data[username] = {
            'name': username,
            'username': username,
            'socket_id': socket_id,
            'life': 0,
            'hand': [],
            'attack_bases': [None] * getattr(self, 'attack_slot_count', 3),
            'defense_bases': [None] * getattr(self, 'defense_slot_count', 6),
            'equipment': {
                'weapon': None,
                'helmet': None,
                'armor': None,
                'pants': None,
                'boots': None,
                'mount': None
            },
            'talismans': [],
            'inventory': [],
            'runes': 0,
            'active_effects': [],
            'profecia_alvo': None,
            'profecia_rodadas': 0,
            'dead': False,
            'observer': True,  # Marcar como observador/espectador
            'spectator': True,
            'free_swap_used': False,
            'first_hit_reduced': False,
            'attacked_this_turn': False,
        }
        
        return True, "Espectador adicionado com sucesso"
    def remove_player(self, username):
        """Remove um jogador do jogo. Retorna (success, was_creator, winner)"""
        if username not in self.players or username not in self.player_data:
            return False, False, None
        
        was_creator = (username == self.creator)
        
        # Processar morte do jogador
        self.process_player_death(username)
        
        # Encontrar e remover mapeamento socket
        socket_to_remove = None
        for socket_id, uname in self.socket_to_username.items():
            if uname == username:
                socket_to_remove = socket_id
                break
        
        if socket_to_remove:
            del self.socket_to_username[socket_to_remove]
        
        # Remover das listas
        self.players.remove(username)
        
        sockets_to_remove = [sid for sid, uname in self.socket_to_username.items() if uname == username]
        for sid in sockets_to_remove:
            del self.socket_to_username[sid]
            
        # Se não há mais jogadores, marcar para limpeza
        if len(self.players) == 0:
            return True, was_creator, None
        
        # Verificar se há um vencedor
        alive_players = [p for p in self.players if not self.player_data[p].get('dead', False)]
        if len(alive_players) == 1:
            self.finished = True
            if not getattr(self, 'finished_at', None):
                import time as _time
                self.finished_at = _time.time()
            self.winner = alive_players[0]
            return True, was_creator, alive_players[0]
        
        # Se era o turno do jogador que saiu, passar para o próximo
        if username in self.players:
            current_index = self.players.index(username)
            if current_index >= 0 and self.current_turn == current_index:
                self.next_turn()
        
        return True, was_creator, None

    def reconnect_player(self, socket_id, username):
        """Reconecta um jogador ou espectador existente ao jogo"""        
        if username in self.player_data:
            # Jogador já existe, atualizar socket
            old_socket = None
            for s, u in list(self.socket_to_username.items()):
                if u == username:
                    old_socket = s
                    break
            
            if old_socket and old_socket != socket_id:
                del self.socket_to_username[old_socket]
            
            self.socket_to_username[socket_id] = username
            self.player_data[username]['socket_id'] = socket_id
            
            return {
                'success': True,
                'username': username,
                'game_started': self.started,
                'spectator': self.player_data[username].get('spectator', False)
            }
        
        return {'success': False, 'message': 'Jogador não encontrado'}

    def can_act(self, username, action):
        """Verifica se o jogador pode realizar uma ação neste turno"""
        player = self.player_data.get(username, {})
        
        if player.get('dead', False):
            return False
        
        if username != self.players[self.current_turn]:
            return False
        
        # Inicializar contadores se necessário
        if username not in self.turn_actions_used:
            self.turn_actions_used[username] = {}
        
        if action not in self.turn_actions_used[username]:
            self.turn_actions_used[username][action] = 0
        
        # Obter limite máximo para esta ação
        max_actions = self.get_max_actions(username)
        action_limit = max_actions.get(action, 1)
        
        # Verificar se já usou o número máximo de vezes
        return self.turn_actions_used[username][action] < action_limit
    def get_max_actions(self, username):
        """Retorna o número máximo de ações de um determinado tipo que o jogador pode realizar"""
        player = self.player_data.get(username, {})
        
        # Verificar se tem Talismã da Sabedoria
        has_sabedoria = False
        for talisman in player.get('talismans', []):
            if talisman and talisman.get('id') == 'talisma_sabedoria':
                has_sabedoria = True
                break
        
        # Verificar se tem Talismã da Sabedoria na mão também (ativado automaticamente)
        if not has_sabedoria:
            for card in player.get('hand', []):
                if card and card.get('id') == 'talisma_sabedoria':
                    has_sabedoria = True
                    break
        
        # Retornar limite de ações
        return {
            'play': 2 if has_sabedoria else 1,
            'draw': 1,
            'attack': 1,
            'swap': 1,
            'spell': 1,
            'ritual': 1,
            'block': 1,
            'oracle': 1,
            'prophet_curse': 1,
            'call_centaurs': 1,
            'toggle_time': 1
        }

    def get_player_talismans_count(self, username):
        player = self.player_data.get(username)
        if not player:
            return 0
        
        count = 0
        for card in player.get('hand', []):
            if card and card.get('type') == 'talisman':
                count += 1
        return count
    def get_player_runes_count(self, username):
        player = self.player_data.get(username)
        if not player or 'no_runes' in self.modifiers:
            return 0
        
        count = 0
        for card in player.get('hand', []):
            if card and (card.get('type') == 'rune' or card.get('id') == 'runa'):
                count += 1
        return count

    def has_fog(self):
        """Névoa de Guerra ativa nesta sala."""
        return 'fog_of_war' in (self.modifiers or [])

    def get_card_for_player(self, card, viewer_username, owner_username):
        """
        Retorna a versão apropriada da carta para o visualizador.
        - Se o visualizador é o dono, mostra a carta real
        - Se não, mostra o disfarce (se for armadilha)
        - fog_of_war: oponentes só veem silhueta (sem nome/stats)
        """
        # Se for o dono da carta, mostrar o real
        if viewer_username == owner_username:
            # Criar uma cópia sem informações sensíveis de disfarce
            if card.get('is_disguised'):
                # Para o dono, mostrar que é uma armadilha
                display_card = card.copy()
                display_card['type'] = 'trap'
                display_card['is_trap'] = True
                # Remover dados de disfarce
                display_card.pop('disguise', None)
                display_card.pop('is_disguised', None)
                return display_card
            return card
        
        # Para espectadores e oponentes
        display = None
        if card.get('is_disguised') and card.get('disguise'):
            # Retornar o disfarce (parece uma criatura normal)
            disguise = card['disguise'].copy()
            disguise['instance_id'] = card['instance_id']
            disguise['is_disguised'] = True
            disguise['is_trap'] = False  # Esconder que é armadilha
            display = disguise
        else:
            display = card.copy() if isinstance(card, dict) else card

        # Névoa de Guerra: esconde identidade e atributos do inimigo
        if 'fog_of_war' in self.modifiers and display:
            return {
                'instance_id': display.get('instance_id') or card.get('instance_id'),
                'type': 'creature' if display.get('type') in ('creature', 'trap', None) else display.get('type', 'creature'),
                'name': '???',
                'id': 'fog',
                'fog': True,
                'life': None,
                'attack': None,
            }

        return display

    def use_action(self, username, action):
        """Registra que uma ação foi usada"""
        if username not in self.turn_actions_used:
            self.turn_actions_used[username] = {}
        
        if action not in self.turn_actions_used[username]:
            self.turn_actions_used[username][action] = 0
        
        self.turn_actions_used[username][action] += 1

        if action == 'attack' and username in self.player_data:
            self.player_data[username]['attacked_this_turn'] = True
        
        # Log para debug
        max_actions = self.get_max_actions(username)
        action_limit = max_actions.get(action, 1)
        used = self.turn_actions_used[username][action]
    
    def register_action(self, username, action_type):
        """Registra que um jogador realizou uma ação na primeira rodada"""
        if self.first_round and action_type not in ['attack', 'end_turn', 'prophet_curse']:
            self.players_acted.add(username)

            if len(self.players_acted) >= len(self.players):
                self.first_round = False
                self.attacks_blocked = False
                return True
        
        return False

    def process_burn_effects(self):
        """Aplica o dano das cartas queimando (Dragão) e remove efeitos expirados."""
        damaged = []
        destroyed = []

        for username, player in self.player_data.items():
            if player.get('dead', False):
                continue
            for base_name in ('attack_bases', 'defense_bases'):
                for i, card in enumerate(player[base_name]):
                    if not card:
                        continue
                    for effect in list(card.get('effects') or []):
                        if effect.get('type') != 'burn':
                            continue
                        try:
                            damage = int(effect.get('damage') or 50)
                            turns = int(effect.get('turns_remaining') or 0) - 1
                        except (TypeError, ValueError):
                            damage, turns = 50, -1

                        new_life = card.get('life', 0) - damage
                        effect['turns_remaining'] = turns
                        self._damage_armor(card, damage)

                        if new_life <= 0:
                            self._handle_non_attack_death(player, base_name, i, card, cause='queimadura')
                            destroyed.append({
                                'player': username,
                                'card_name': card.get('name', 'Carta'),
                            })
                        else:
                            card['life'] = new_life
                            damaged.append(f"{card.get('name', 'Carta')} (-{damage}🔥)")

                        if turns <= 0:
                            card.setdefault('effects', []).remove(effect)
                        break  # uma queimadura por carta por turno

        if damaged or destroyed:
            broadcast_system_message(
                self.game_id,
                f"🔥 Queimadura: {', '.join(damaged + [d['card_name'] + ' morreu queimando' for d in destroyed])}",
                fog_message=f"🔥 Cartas queimando causaram dano em {len(damaged) + len(destroyed)} carta(s).",
            )
        return damaged, destroyed

    def process_phoenix_eggs(self):
        """Conta os turnos do Ovo de Fênix e devolve a carta com metade da vida."""
        returned = []

        for username, player in self.player_data.items():
            inventory = player.get('inventory') or []
            if player.get('dead', False):
                player['inventory'] = [
                    item for item in inventory if item.get('id') != 'ovo_fenix'
                ]
                continue

            for egg in list(inventory):
                if egg.get('id') != 'ovo_fenix':
                    continue
                try:
                    egg['turns_remaining'] = int(egg.get('turns_remaining') or 0) - 1
                except (TypeError, ValueError):
                    egg['turns_remaining'] = -1

                if egg['turns_remaining'] > 0:
                    continue

                instance_id = egg.get('phoenix_instance_id')
                fenix = None
                graveyard_index = -1
                for i, card in enumerate(self.graveyard):
                    if card.get('instance_id') == instance_id and card.get('id') == 'fenix':
                        fenix = card
                        graveyard_index = i
                        break

                if egg in (player.get('inventory') or []):
                    player['inventory'].remove(egg)

                if not fenix or fenix.get('phoenix_reborn') or fenix.get('phoenix_egg_lost'):
                    broadcast_system_message(
                        self.game_id,
                        f"🥚 O Ovo de Fênix de {username} esfriou — a Fênix não volta mais.",
                        fog_message=f"🥚 Um ovo esfriou para {username}.",
                    )
                    continue

                self.graveyard.pop(graveyard_index)
                half_life = max(1, self._default_card_life(fenix) // 2)
                fenix['life'] = half_life
                fenix['phoenix_reborn'] = True
                player.setdefault('hand', []).append(fenix)
                returned.append({'player': username, 'card': fenix})
                broadcast_system_message(
                    self.game_id,
                    f"🔥 Fênix de {username} renasceu com metade da vida ({half_life}❤️)!",
                    fog_message=f"🔥 Uma Fênix renasceu para {username}!",
                )

        return returned

    def next_turn(self):
        """Avança para o próximo turno, pulando jogadores mortos"""
        if not self.players:
            return

        # Efeitos que contam turnos: queimadura do Dragão e Ovo de Fênix
        self.process_burn_effects()
        self.process_phoenix_eggs()

        # A petrificação da Medusa dura até o fim do próximo turno do alvo
        ending_username = self.players[self.current_turn]
        ending_player = self.player_data.get(ending_username)
        if ending_player:
            for card in ending_player['attack_bases']:
                if card and card.get('petrified'):
                    card.pop('petrified', None)

        # Sangria: se o jogador atual não atacou neste turno, -20 vida
        if 'bleed_out' in self.modifiers and self.players:
            ending = self.players[self.current_turn]
            pdata = self.player_data.get(ending)
            if pdata and not pdata.get('dead') and not pdata.get('attacked_this_turn'):
                pdata['life'] = pdata.get('life', 0) - 20
                broadcast_system_message(
                    self.game_id,
                    f'🩸 Sangria: {ending} não atacou e perde 20 de vida! ({pdata["life"]}❤️)'
                )
                if pdata['life'] <= 0:
                    self.process_player_death(ending)
        
        # Processar maldições do Profeta ANTES de mudar de turno
        destroyed_cards = self.process_prophet_curses()
        
        original_turn = self.current_turn
        next_turn = (self.current_turn + 1) % len(self.players)
        
        # Continuar avançando enquanto o jogador estiver morto
        while self.player_data[self.players[next_turn]].get('dead', False):
            next_turn = (next_turn + 1) % len(self.players)
            
            if next_turn == original_turn:
                break
        
        self.current_turn = next_turn
        self.turn_actions_used = {}  # Resetar todas as ações
        self.turn_extra_actions = {}  # Resetar ações extras
        
        for username in self.players:
            if not self.player_data[username].get('dead', False):
                self.turn_actions_used[username] = {}
                # resets por turno (armaduras com habilidade)
                self.player_data[username]['free_swap_used'] = False
                self.player_data[username]['first_hit_reduced'] = False
                self.player_data[username]['attacked_this_turn'] = False
        
        cycle_changed = False
        if 'disable_daycicle' not in self.modifiers:
            self.time_cycle += 1
            cycle_len = getattr(self, 'day_cycle_length', 24) or 24
            if self.time_cycle % cycle_len == 0:
                cycle_changed = True
                self.time_of_day = "night" if self.time_of_day == "day" else "day"
                if self.time_of_day == "day":
                    # virada do ciclo: sempre reaplica (fora dos turnos normais)
                    self.apply_day_effects(force=True)
                else:
                    self.apply_werewolf_forms()
                    self.refresh_dynamic_weapon_bonuses()
                    self._last_day_effects_signature = self._day_effects_signature()

        if self.time_of_day == "day" and not cycle_changed:
            # Sem virada, só recalcula se cartas/equipamentos mudaram.
            self.apply_day_effects()

        
        current_player = self.players[self.current_turn]
        
        # Se cartas foram destruídas, notificar
        if destroyed_cards:
            destroyed_messages = [f"{d['card_name']} de {d['player']}" for d in destroyed_cards]
            # Podemos emitir um evento aqui se quiser notificar os jogadores
            socketio.emit('prophet_curses_executed', {
                'destroyed': destroyed_cards,
                'message': f'💀 Maldições do Profeta executadas: {", ".join(destroyed_messages)}'
            }, room=self.game_id)

    def can_attack(self, username):
        """Verifica se o jogador pode atacar (bloqueado na primeira rodada)"""
        if self.attacks_blocked:
            return False, "Ataques bloqueados na primeira rodada. Todos precisam jogar primeiro."
        return True, ""
    
    def draw_card(self, username):
        """Compra uma carta"""
        if not self.can_act(username, 'draw'):
            return {'success': False, 'message': 'Você já comprou uma carta neste turno'}
        
        if not self.deck:
            return {'success': False, 'message': 'Monte vazio'}
        
        card = self.deck.pop()
        self.player_data[username]['hand'].append(card)
        self.use_action(username, 'draw')
        
        return {'success': True, 'card': card}
    def play_card(self, username, card_instance_id, position_type, position_index):
        """Joga uma carta da mão para o campo com validação de tipo"""
        if not self.can_act(username, 'play'):
            return {'success': False, 'message': 'Você já jogou uma carta neste turno'}
        
        player = self.player_data[username]
        
        # Encontrar carta na mão
        card_to_play = None
        card_index = -1
        for i, card in enumerate(player['hand']):
            if card['instance_id'] == card_instance_id:
                card_to_play = card
                card_index = i
                break
        
        if not card_to_play:
            return {'success': False, 'message': 'Carta não encontrada na mão'}
        
        # Validar tipo de carta para a posição
        if position_type == 'attack':
            # Apenas criaturas podem atacar
            if card_to_play.get('type') != 'creature':
                return {'success': False, 'message': 'Apenas criaturas podem ser colocadas em bases de ataque'}
        
        elif position_type == 'defense':
            # Defesa pode receber: criaturas E armadilhas
            allowed_types = ['creature', 'trap']
            if card_to_play.get('type') not in allowed_types:
                return {'success': False, 'message': f'Apenas criaturas e armadilhas podem ser colocadas em defesa (tipo: {card_to_play.get("type")})'}
            
            # Se for armadilha, gerar um disfarce aleatório
            if card_to_play.get('type') == 'trap':
                disguise = get_random_disguise()
                disguise['original_trap_id'] = card_to_play['id']
                disguise['original_trap_name'] = card_to_play['name']
                disguise['instance_id'] = card_to_play['instance_id']  # Manter mesmo instance_id
                card_to_play['disguise'] = disguise
                card_to_play['is_disguised'] = True
        
        elif position_type == 'equipment':
            valid_equipment_types = {
                'weapon': ['weapon'],
                'helmet': ['armor'],
                'armor': ['armor'],
                'pants': ['armor'],
                'boots': ['armor'],
                'mount': ['creature']
            }
            # preferência da carta (capacete, peitoral, calças, botas)
            preferred = card_to_play.get('slot')
            slot_name = preferred if preferred in valid_equipment_types else position_index
            if slot_name not in valid_equipment_types:
                return {'success': False, 'message': 'Slot de equipamento inválido'}
            if card_to_play.get('type') not in valid_equipment_types[slot_name]:
                return {'success': False, 'message': f'Esta carta não pode ser equipada em {slot_name}'}
            if player['equipment'].get(slot_name) is not None:
                return {'success': False, 'message': f'Slot de {slot_name} já está ocupado'}
            # guardar slot resolvido para o bloco de colocação
            position_index = slot_name
        
        else:
            return {'success': False, 'message': 'Tipo de posição inválido'}
        
        # IMPORTANTE: validar a posição ANTES de remover a carta da mão,
        # senão uma jogada inválida faz a carta desaparecer do jogo.
        if position_type == 'attack':
            if position_index < 0 or position_index >= len(player['attack_bases']):
                return {'success': False, 'message': 'Posição de ataque inválida'}
            if player['attack_bases'][position_index] is not None:
                return {'success': False, 'message': 'Posição de ataque ocupada'}
        
        elif position_type == 'defense':
            if position_index < 0 or position_index >= len(player['defense_bases']):
                return {'success': False, 'message': 'Posição de defesa inválida'}
            if player['defense_bases'][position_index] is not None:
                return {'success': False, 'message': 'Posição de defesa ocupada'}
        
        # Remover carta da mão (após todas as validações)
        player['hand'].pop(card_index)
        
        # Colocar carta no local apropriado
        if position_type == 'attack':
            player['attack_bases'][position_index] = card_to_play
        
        elif position_type == 'defense':
            player['defense_bases'][position_index] = card_to_play
        
        elif position_type == 'equipment':
            player['equipment'][position_index] = card_to_play
        
        # Lobisomem: aplicar forma atual ao entrar em campo
        if card_to_play.get('type') == 'creature' and card_to_play.get('werewolf'):
            card_to_play['werewolf_form'] = None
            self.apply_werewolf_forms()

        # Habilidades com cota limitada (ex.: Medusa) começam ao entrar em campo
        self._ensure_ability_charges(card_to_play)
        
        self.use_action(username, 'play')
        
        return {'success': True, 'card': card_to_play}
    
    def attack(self, username, target_username):
        """Ataca outro jogador com verificação de primeira rodada e armadilhas"""
        can_attack, message = self.can_attack(username)
        if not can_attack:
            return {'success': False, 'message': message}
        
        if not self.can_act(username, 'attack'):
            return {'success': False, 'message': 'Você já atacou neste turno'}
        
        if target_username not in self.players:
            return {'success': False, 'message': 'Jogador alvo inválido'}
        
        if self.player_data[target_username].get('dead', False):
            return {'success': False, 'message': 'Este jogador já está morto'}
        
        attacker = self.player_data.get(username)
        defender = self.player_data.get(target_username)
        
        if not attacker or not defender:
            return {'success': False, 'message': 'Dados do jogador não encontrados'}
        
        # Calcular poder de ataque
        has_attack_cards = False
        attack_power = 0
        attacking_cards = []
        
        for i, card in enumerate(attacker['attack_bases']):
            if card and card.get('type') == 'creature' and not card.get('petrified'):
                has_attack_cards = True
                card_attack = card.get('attack', 0)
                attack_power += card_attack
                attacking_cards.append({
                    'card': card,
                    'index': i,
                    'attack': card_attack
                })
        
        if not has_attack_cards:
            return {'success': False, 'message': 'Você precisa de criaturas em posição de ataque para atacar'}
        
        # Adicionar bônus de equipamentos (armas com efeito dinâmico: clava/adaga)
        if attacker.get('equipment') and attacker['equipment'].get('weapon'):
            weapon = attacker['equipment']['weapon']
            if weapon.get('type') == 'weapon':
                attack_power += self.get_weapon_attack_value(attacker, weapon)
        
        # Talismã Guerreiro na MÃO
        for talisman in attacker['hand']:
            if talisman.get('id') == 'talisma_guerreiro':
                attack_power += 1024
        
        # Silêncio / Selo: pular armadilhas
        skip_traps = False
        # Selo de Silêncio Menor (próximo ataque do atacante)
        attacker_effects = attacker.get('active_effects') or []
        for eff in list(attacker_effects):
            if eff.get('type') == 'trap_silence_next_attack':
                skip_traps = True
                attacker_effects.remove(eff)
                broadcast_system_message(self.game_id, f'🔇 Selo de Silêncio: o ataque de {username} não ativa armadilhas!')
                break
        # Feitiço Silêncio global (duration turns)
        for uname in (username, target_username):
            for eff in self.player_data[uname].get('active_effects') or []:
                if eff.get('type') == 'silence' and eff.get('duration', 0) > 0:
                    skip_traps = True
                    break

        # Coletar armadilhas do defensor
        trap_cards = []
        if not skip_traps:
            for i, card in enumerate(defender['defense_bases']):
                if card and card.get('type') == 'trap':
                    trap_cards.append({
                        'card': card,
                        'index': i,
                        'name': card.get('name', 'Armadilha')
                    })
        
        # Processar armadilhas
        trap_effects = []

        for trap in trap_cards:
            trap_result = self.activate_trap(trap['card'], attacker, defender, attack_power)
            
            if trap_result:
                self.graveyard.append(defender['defense_bases'][trap['index']])
                defender['defense_bases'][trap['index']] = None

                if trap_result.get('type') == 'mirror_damage':
                    # Armadilha Espelho - refletir dano
                    reflected_damage = trap_result.get('damage_to_reflect', attack_power)
                    
                    # Aplicar dano refletido ao atacante
                    result = self.apply_damage_to_player(username, reflected_damage, is_reflected=True)
                    
                    self.use_action(username, 'attack')
                    
                    return {
                        'success': True,
                        'total_attack': attack_power,
                        'damage_reflected': True,
                        'reflected_damage': reflected_damage,
                        'attacker': username,
                        'attacker_name': attacker['name'],
                        'target': target_username,
                        'target_name': defender['name'],
                        'mirror_result': result,
                        'trap_effects': [{
                            'type': 'mirror_applied',
                            'damage': reflected_damage,
                            'message': f'🪞 Dano refletido! {attacker["name"]} sofreu {result["damage_taken"]} de dano!'
                        }],
                        'log': result['log']
                    }
                elif trap_result.get('type') == 'cheat_pass_damage':
                    # Armadilha Cheat - passar dano para próximo jogador
                    current_index = self.players.index(target_username)
                    next_index = (current_index + 1) % len(self.players)
                    next_player_name = self.players[next_index]
                    
                    # Pular jogadores mortos
                    while self.player_data[next_player_name].get('dead', False) and next_index != current_index:
                        next_index = (next_index + 1) % len(self.players)
                        next_player_name = self.players[next_index]
                    
                    if next_player_name == target_username:
                        # Sem próximo jogador válido, aplicar dano normal
                        pass
                    else:
                        # Aplicar dano ao próximo jogador
                        result = self.apply_damage_to_player(next_player_name, attack_power, skip_talisman=False)
                        
                        self.use_action(username, 'attack')
                        
                        return {
                            'success': True,
                            'total_attack': attack_power,
                            'damage_to_player': result['damage_to_player'],
                            'attacker': username,
                            'attacker_name': attacker['name'],
                            'target': next_player_name,
                            'target_name': self.player_data[next_player_name]['name'],
                            'target_life': self.player_data[next_player_name]['life'],
                            'player_killed': result['player_killed'],
                            'trap_effects': [{
                                'type': 'cheat_applied',
                                'message': f'⚡ Armadilha Cheat! Dano transferido para {next_player_name}!'
                            }],
                            'cheat_transferred': True,
                            'original_target': target_username,
                            'log': result['log']
                        }
                elif trap_result.get('cancel_attack', False):
                    # Armadilha que cancela o ataque
                    return {
                        'success': True,
                        'attack_cancelled': True,
                        'trap_effects': trap_effects,
                        'message': '⚠️ O ataque foi cancelado por uma armadilha!'
                    }
                else:
                    # Outros efeitos de armadilha
                    trap_effects.extend(trap_result.get('effects', []) if isinstance(trap_result, dict) else [trap_result])

        # Se chegou aqui, não houve armadilha que cancelou/refletiu/transferiu o ataque
        # Processar dano normalmente usando apply_damage_to_player
        
        # Passar a mão do atacante para verificar Oráculo
        self.attacker_hand_for_oracle = attacker['hand']
        
        result = self.apply_damage_to_player(target_username, attack_power, is_reflected=False)
        
        # Limpar
        delattr(self, 'attacker_hand_for_oracle')
        
        self.use_action(username, 'attack')
        
        # Se o Oráculo foi usado, remover da mão
        if result.get('oracle_activated'):
            oracle_index = -1
            for i, card in enumerate(attacker['hand']):
                if card and card.get('id') == 'oraculo_imortalidade':
                    oracle_index = i
                    break
            if oracle_index != -1:
                used_oracle = attacker['hand'].pop(oracle_index)
                self.deck.append(used_oracle)
                shuffle(self.deck)
                socketio.emit('oracle_activated', {
                    'attacker': attacker['name'],
                    'defender': defender['name'],
                    'message': f'📜 {attacker["name"]} usou o Oráculo da Imortalidade para anular o Talismã de {defender["name"]}!'
                }, room=self.game_id)

        # Efeitos das criaturas que atacaram (Medusa/Dragão)
        creature_effects = []
        if any(entry.get('card', {}).get('id') == 'medusa' for entry in attacking_cards):
            creature_effects.extend(self.apply_medusa_petrify(defender, username))
        if any(entry.get('card', {}).get('id') == 'dragao' for entry in attacking_cards):
            creature_effects.extend(self.apply_dragon_burn(defender, username))
        
        return {
            'success': True,
            'total_attack': attack_power,
            'damage_absorbed': attack_power - result['damage_to_player'],
            'damage_to_player': result['damage_to_player'],
            'attacker': username,
            'attacker_name': attacker['name'],
            'target': target_username,
            'target_name': defender['name'],
            'target_life': defender['life'] if defender['life'] > 0 else 0,
            'cards_destroyed': result['cards_destroyed'],
            'cards_damaged': result['cards_damaged'],
            'player_killed': result['player_killed'],
            'oracle_activated': result.get('oracle_activated', False),
            'immortality_activated': result.get('immortality_activated', False),
            'log': result['log'],
            'trap_effects': trap_effects,
            'cards_healed': result.get('cards_healed', []),
            'creature_effects': creature_effects,
        }

    def apply_medusa_petrify(self, defender, attacker_username):
        """Medusa petrifica as cartas de ataque do alvo por 1 turno (máx. 2 usos)."""
        attacker = self.player_data.get(attacker_username)
        if not attacker or not defender:
            return []

        medusa = next(
            (card for card in attacker['attack_bases'] if card and card.get('id') == 'medusa'),
            None,
        )
        if not medusa:
            return []

        self._ensure_ability_charges(medusa)
        if medusa.get('medusa_petrify_uses', 0) <= 0:
            return []

        targets = [
            card for card in defender['attack_bases']
            if card and card.get('type') == 'creature'
        ]
        if not targets:
            return []

        for card in targets:
            card['petrified'] = True
        medusa['medusa_petrify_uses'] -= 1
        uses_left = medusa['medusa_petrify_uses']

        broadcast_system_message(
            self.game_id,
            f"🐍 Medusa petrificou {len(targets)} carta(s) de ataque de {defender['name']} "
            f"({uses_left}/2 usos restantes)!",
            fog_message=f"🐍 Cartas de ataque de {defender['name']} foram petrificadas!",
        )

        return [{
            'type': 'medusa_petrify',
            'card_count': len(targets),
            'uses_remaining': uses_left,
            'message': f'{len(targets)} carta(s) petrificada(s)',
        }]

    def apply_dragon_burn(self, defender, attacker_username):
        """Dragão queima todas as cartas do alvo: 50 de dano por 2 turnos."""
        attacker = self.player_data.get(attacker_username)
        if not attacker or not defender:
            return []

        has_dragon = any(
            card and card.get('id') == 'dragao' for card in attacker['attack_bases']
        )
        if not has_dragon:
            return []

        burned = 0
        for base_name in ('defense_bases', 'attack_bases'):
            for card in defender[base_name]:
                if not card or card.get('type') != 'creature':
                    continue
                effects = card.setdefault('effects', [])
                existing = next((eff for eff in effects if eff.get('type') == 'burn'), None)
                if existing:
                    existing['turns_remaining'] = 2
                    existing['damage'] = 50
                else:
                    effects.append({
                        'type': 'burn',
                        'turns_remaining': 2,
                        'damage': 50,
                        'source': 'dragao',
                    })
                burned += 1

        if burned:
            broadcast_system_message(
                self.game_id,
                f"🔥 Dragão queimou {burned} carta(s) de {defender['name']}: 50❤️ por 2 turnos!",
                fog_message=f"🔥 Cartas de {defender['name']} estão queimando por 2 turnos!",
            )

        return [{
            'type': 'dragon_burn',
            'card_count': burned,
            'damage_per_turn': 50,
            'turns': 2,
            'message': f'{burned} carta(s) queimando',
        }]

    def _heal_cards_after_ninfa(self, player, killed_base, killed_index, amount, damage_log):
        """Converte o dano excedente da Ninfa em cura nas próximas cartas da fila."""
        if amount <= 0:
            return []

        healed = []
        sequences = []
        if killed_base == 'defense_bases':
            sequences.append(('defense_bases', range(killed_index + 1, len(player['defense_bases']))))
        sequences.append(('attack_bases', range(len(player['attack_bases']))))

        for base_name, indices in sequences:
            for i in indices:
                if amount <= 0:
                    break
                card = player[base_name][i]
                if not card or card.get('type') != 'creature':
                    continue
                max_life = self._default_card_life(card)
                current_life = card.get('life', 0)
                if current_life >= max_life:
                    continue
                cure = min(amount, max_life - current_life)
                card['life'] = current_life + cure
                amount -= cure
                where = 'defesa' if base_name == 'defense_bases' else 'ataque'
                text = f"{card['name']} ({where}) (+{cure}❤️)"
                healed.append(text)
                damage_log.append(f"🧚 {text} curou até a vida padrão")

        return healed

    def _destroy_card_on_attack(self, target_username, base_name, index, card,
                                overflow=0, damage_log=None, cards_destroyed=None):
        """
        Remove uma carta morta por ataque e aplica as habilidades de morte.
        - Zumbi volta para a mão de quem a tinha em campo.
        - Ninfa transforma o dano excedente em cura na linha de fogo.
        - Fênix deixa o Ovo com contador de 10 turnos (uma vez só).
        """
        player = self.player_data[target_username]
        card_name = card.get('name', 'Carta')
        info = {
            'card': card,
            'card_name': card_name,
            'returned_to_hand': False,
            'healed': [],
            'phoenix_egg': False,
        }
        logs = []

        # Ataque: zumbi volta pra mão; qualquer outra carta vai pro cemitério
        if card.get('id') == 'zumbi':
            player.setdefault('hand', []).append(card)
            info['returned_to_hand'] = True
            logs.append(f"🧟 {card_name} voltou para a mão de {player['name']} (destruído no ataque)")
        else:
            self.graveyard.append(card)
            logs.append(f"{card_name} foi para o cemitério")

            if card.get('id') == 'fenix' and not card.get('phoenix_rebirth_used'):
                self._give_phoenix_egg(player, card)
                info['phoenix_egg'] = True

        player[base_name][index] = None

        if self._is_ninfa(card) and overflow > 0 and damage_log is not None:
            cured = self._heal_cards_after_ninfa(player, base_name, index, overflow, damage_log)
            info['healed'] = cured
            logs.append(f"🧚 Sacrifício da Ninfa: {overflow} de dano restante virou cura nas próximas cartas")

        if cards_destroyed is not None:
            cards_destroyed.append(card_name)
        if damage_log is not None:
            damage_log.extend(logs)

        return info

    def apply_damage_to_player(self, target_username, damage_amount, is_reflected=False, skip_talisman=False):
        """
        Aplica dano a um jogador respeitando suas defesas (criaturas, talismãs, etc)
        A ORDEM de absorção: defesa índice 0→5, depois ataque índice 0→2
        
        Args:
            target_username: Nome do jogador que vai receber o dano
            damage_amount: Quantidade de dano a ser aplicada
            is_reflected: Se o dano é refletido (para mensagens diferenciadas)
            skip_talisman: Se deve pular a verificação do Talismã da Imortalidade
        
        Returns:
            dict: Resultado da aplicação do dano
        """
        target = self.player_data.get(target_username)
        
        if not target:
            return {'damage_taken': 0, 'player_killed': False, 'log': ['Jogador não encontrado']}
        
        if target.get('dead', False):
            return {'damage_taken': 0, 'player_killed': False, 'log': [f'{target["name"]} já está morto']}
        
        # PRIMEIRO: Coletar cartas de defesa na ORDEM (0 a 5)
        defense_cards = []
        for i, card in enumerate(target['defense_bases']):
            if card and card.get('type') == 'creature':
                defense_cards.append({
                    'card': card,
                    'index': i,
                    'current_life': card.get('life', 0),
                    'name': card.get('name', 'Desconhecido')
                })
        
        # SEGUNDO: Coletar cartas de ataque na ORDEM (0 a 2)
        attack_cards = []
        for i, card in enumerate(target['attack_bases']):
            if card and card.get('type') == 'creature':
                attack_cards.append({
                    'card': card,
                    'index': i,
                    'current_life': card.get('life', 0),
                    'name': card.get('name', 'Desconhecido')
                })
        
        remaining_damage = damage_amount
        damage_log = []
        cards_destroyed = []
        cards_damaged = []
        cards_healed = []

        # Capacete da Sentinela: 1º hit do turno -80
        helmet = (target.get('equipment') or {}).get('helmet')
        if helmet and helmet.get('ability') == 'first_hit_reduce' and not target.get('first_hit_reduced'):
            reduce = helmet.get('first_hit_reduce', 80)
            remaining_damage = max(0, remaining_damage - reduce)
            target['first_hit_reduced'] = True
            damage_log.append(f'🪖 Capacete da Sentinela absorveu {reduce} do primeiro golpe')

        # Calças da Marcha no slot pants do jogador: -40 flat em todo dano à vida (aplicado no final)
        pants = (target.get('equipment') or {}).get('pants')
        pants_flat = 0
        if pants and pants.get('ability') == 'damage_flat_reduce':
            pants_flat = pants.get('damage_flat_reduce', 40)
        
        # ORDEM 1: Absorver dano pelas cartas de DEFESA (índice 0 → 5)
        apollo_healed = 0
        for def_card in defense_cards:
            if remaining_damage <= 0:
                break
            
            card = def_card['card']
            # Vida lida na hora: a Ninfa pode ter curado esta carta na linha de fogo
            card_life = card.get('life', def_card.get('current_life', 0))
            reflected_text = " [dano refletido]" if is_reflected else ""

            # Apollo (defesa): dano < 1000 que o atinge → cura o JOGADOR pelo valor
            # total do golpe, mas a CARTA Apollo sofre só a metade do dano.
            if (
                remaining_damage > 0
                and remaining_damage < int(card.get('apollo_guard_threshold', 1000))
                and (
                    card.get('id') == 'apollo'
                    or card.get('ability') == 'apollo_guard'
                )
            ):
                hit = remaining_damage
                heal = hit
                card_damage = max(1, hit // 2) if hit > 0 else 0  # metade (mín. 1 se hit>0)

                old_player_life = target.get('life', 0)
                target['life'] = old_player_life + heal
                apollo_healed = heal

                old_card_life = card_life
                new_card_life = card_life - card_damage
                self._damage_armor(card, card_damage)
                if new_card_life <= 0:
                    self.graveyard.append(card)
                    target['defense_bases'][def_card['index']] = None
                    cards_destroyed.append(card['name'])
                    damage_log.append(
                        f"☀️ Apollo (defesa) converteu {heal} em cura para {target['name']} "
                        f"({old_player_life}→{target['life']}❤️), mas caiu com {card_damage} de dano "
                        f"(metade de {hit}){reflected_text}"
                    )
                else:
                    card['life'] = new_card_life
                    cards_damaged.append(
                        f"{card['name']} (defesa) (-{card_damage}❤️, metade)"
                    )
                    damage_log.append(
                        f"☀️ Apollo (defesa) converteu {heal} em cura para {target['name']} "
                        f"({old_player_life}→{target['life']}❤️) e sofreu só {card_damage} "
                        f"na carta ({old_card_life}→{new_card_life}❤️){reflected_text}"
                    )

                try:
                    broadcast_system_message(
                        self.game_id,
                        f"☀️ Apollo de {target_username}: +{heal}❤️ no jogador, "
                        f"carta toma {card_damage} (metade de {hit})!",
                        fog_message=f"☀️ Uma defesa especial de {target_username} absorveu parte do golpe!",
                    )
                except Exception:
                    pass
                remaining_damage = 0
                break
            
            if remaining_damage >= card_life:
                overflow = remaining_damage - card_life
                self._damage_armor(card, card_life)
                destroyed = self._destroy_card_on_attack(
                    target_username, 'defense_bases', def_card['index'], card,
                    overflow=overflow, damage_log=damage_log, cards_destroyed=cards_destroyed,
                )
                cards_healed.extend(destroyed.get('healed', []))
                damage_log.append(f"{card['name']} (defesa) foi destruída{reflected_text}")
                # Ninfa absorve o restante e não deixa dano passar adiante
                remaining_damage = 0 if destroyed.get('healed') or self._is_ninfa(card) else overflow
            else:
                new_life = card_life - remaining_damage
                card['life'] = new_life
                self._damage_armor(card, remaining_damage)
                cards_damaged.append(f"{card['name']} (defesa) (-{remaining_damage}❤️)")
                damage_log.append(f"{card['name']} (defesa) recebeu {remaining_damage} de dano (vida restante: {new_life}){reflected_text}")
                remaining_damage = 0
        
        # ORDEM 2: Absorver dano pelas cartas de ATAQUE (índice 0 → 2)
        for atk_card in attack_cards:
            if remaining_damage <= 0:
                break
            
            card = atk_card['card']
            # Vida lida na hora: a Ninfa pode ter curado esta carta na linha de fogo
            card_life = card.get('life', atk_card.get('current_life', 0))
            reflected_text = " [dano refletido]" if is_reflected else ""
            
            if remaining_damage >= card_life:
                overflow = remaining_damage - card_life
                self._damage_armor(card, card_life)
                destroyed = self._destroy_card_on_attack(
                    target_username, 'attack_bases', atk_card['index'], card,
                    overflow=overflow, damage_log=damage_log, cards_destroyed=cards_destroyed,
                )
                cards_healed.extend(destroyed.get('healed', []))
                damage_log.append(f"{card['name']} (ataque) foi destruída{reflected_text}")
                # Ninfa absorve o restante e não deixa dano passar adiante
                remaining_damage = 0 if destroyed.get('healed') or self._is_ninfa(card) else overflow
            else:
                new_life = card_life - remaining_damage
                card['life'] = new_life
                self._damage_armor(card, remaining_damage)
                cards_damaged.append(f"{card['name']} (ataque) (-{remaining_damage}❤️)")
                damage_log.append(f"{card['name']} (ataque) recebeu {remaining_damage} de dano (vida restante: {new_life}){reflected_text}")
                remaining_damage = 0
        
        # ORDEM 3: Dano restante vai para o JOGADOR
        damage_to_player = 0
        player_killed = False
        oracle_activated = False
        immortality_activated = False
        
        if remaining_damage > 0:
            damage_to_player = remaining_damage
            reflected_text = " [dano refletido]" if is_reflected else ""
            
            oracle_index = -1
            has_elf_in_defense = False
            
            if not is_reflected and hasattr(self, 'attacker_hand_for_oracle'):
                for i, card in enumerate(self.attacker_hand_for_oracle):
                    if card and card.get('id') == 'oraculo_imortalidade':
                        oracle_index = i
                        break

                if oracle_index != -1: 
                    attacker = self.player_data.get(self.players[self.current_turn])
                    if attacker:
                        for card in attacker['defense_bases']:
                            if card and card.get('id') == 'elfo':
                                has_elf_in_defense = True
                                break
                    
                    if not has_elf_in_defense:
                        damage_log.append("⚠️ Oráculo não pode ser usado: requer um Elfo em modo de defesa")
                        oracle_index = -1

            # Verificar Talismã da Imortalidade no alvo
            immortality_index = -1
            if not skip_talisman:
                for i, talisman in enumerate(target['hand']):
                    if talisman and talisman.get('id') == 'talisma_imortalidade':
                        immortality_index = i
                        break
            
            # Aplicar dano ao jogador (Calças da Marcha reduzem dano final)
            if pants_flat and remaining_damage > 0:
                before = remaining_damage
                remaining_damage = max(0, remaining_damage - pants_flat)
                damage_log.append(f'👖 Calças da Marcha reduziram {before - remaining_damage} de dano')
            damage_to_player = remaining_damage
            old_life = target['life']
            target['life'] -= remaining_damage
            damage_log.append(f"⚔️ {target['name']} recebeu {remaining_damage} de dano direto{reflected_text} (vida: {old_life} → {target['life']})")
            
            # Verificar se morreu
            if target['life'] <= 0:
                # Caso especial: Oráculo anula Talismã
                if oracle_index != -1 and immortality_index != -1:
                    player_killed = True
                    oracle_activated = True
                    self.process_player_death(target_username)
                    damage_log.append(f"💀 {target['name']} foi derrotado! O Oráculo anulou o Talismã da Imortalidade!")
                elif immortality_index != -1 and not skip_talisman:
                    # Talismã da Imortalidade salva
                    talisman = target['hand'][immortality_index]
                    if 'uses_left' not in talisman:
                        talisman['uses_left'] = 2
                    
                    talisman['uses_left'] -= 1
                    uses_left = talisman['uses_left']
                    immortality_activated = True
                    
                    old_life = target['life']
                    target['life'] = 5000
                    
                    damage_log.append(f"✨ Talismã da Imortalidade salvou {target['name']}! ({uses_left} uso(s) restante(s))")
                    damage_log.append(f"   Vida restaurada: {old_life} → 5000")
                    damage_to_player = 0
                    
                    if uses_left <= 0:
                        used_talisman = target['hand'].pop(immortality_index)
                        used_talisman['uses_left'] = 2
                        self.deck.append(used_talisman)
                        shuffle(self.deck)
                        damage_log.append("🔄 Talismã da Imortalidade se esgotou e voltou para o deck!")
                else:
                    player_killed = True
                    self.process_player_death(target_username)
                    damage_log.append(f"💀 {target['name']} foi derrotado!{reflected_text}")
        
        return {
            'damage_taken': damage_amount - remaining_damage,
            'damage_to_player': damage_to_player,
            'player_killed': player_killed,
            'oracle_activated': oracle_activated,
            'immortality_activated': immortality_activated,
            'apollo_healed': apollo_healed,
            'cards_destroyed': cards_destroyed,
            'cards_damaged': cards_damaged,
            'cards_healed': cards_healed,
            'log': damage_log
        }
    def force_attack_between_players(self, attacker_name, target_name):
        """
        Força um ataque entre dois jogadores (usado pela armadilha 51)
        
        Args:
            attacker_name: Nome do jogador que vai atacar
            target_name: Nome do jogador que vai ser atacado
        """
        attacker = self.player_data.get(attacker_name)
        target = self.player_data.get(target_name)
        
        if not attacker or not target:
            return
        
        # Calcular poder de ataque do atacante
        attack_power = 0
        for card in attacker['attack_bases']:
            if card and card.get('type') == 'creature':
                attack_power += card.get('attack', 0)
        
        # Adicionar bônus de equipamentos
        if attacker['equipment']['weapon']:
            weapon = attacker['equipment']['weapon']
            if weapon.get('type') == 'weapon':
                weapon_attack = weapon.get('attack', 0)
                attack_power += weapon_attack
        
        # Talismã Guerreiro
        for talisman in attacker['hand']:
            if talisman.get('id') == 'talisma_guerreiro':
                attack_power += 1024
        
        # Aplicar dano ao alvo (respeitando defesas)
        result = self.apply_damage_to_player(target_name, attack_power, is_reflected=False)
        
        # Broadcast do ataque forçado
        broadcast_system_message(self.game_id, 
            f'🍺 {attacker_name} (controlado pela armadilha) atacou {target_name} causando {attack_power} de dano!')
        
        # Se o alvo morreu, já foi processado pelo apply_damage_to_player
        if result.get('player_killed'):
            broadcast_system_message(self.game_id, f'💀 {target_name} foi derrotado pelo ataque forçado!')

    def process_player_death(self, username):
        """Processa a morte de um jogador"""
        broadcast_system_message(self.game_id, f'💀 {username} foi derrotado!')
        
        player = self.player_data[username]
        
        player['dead'] = True
        player['observer'] = True
        player['life'] = 0
        # Derrotado: ovos de Fênix não têm mais efeito
        player['inventory'] = [
            item for item in (player.get('inventory') or []) if item.get('id') != 'ovo_fenix'
        ]

        # Caça ao Rei: quem matou o criador da sala ganha +300 vida
        if 'king_hunt' in self.modifiers and username == self.creator and self.players:
            killer = self.players[self.current_turn]
            if killer != username and killer in self.player_data and not self.player_data[killer].get('dead'):
                self.player_data[killer]['life'] = self.player_data[killer].get('life', 0) + 300
                broadcast_system_message(
                    self.game_id,
                    f'👑 Caça ao Rei! {killer} eliminou o criador da sala e ganha +300 de vida!'
                )
        
        # Processar cartas da mão
        hand_cards = player['hand'].copy()
        player['hand'] = []
        
        for card in hand_cards:
            if card.get('type') == 'creature':
                self.graveyard.append(card)
            else:
                self.deck.append(card)
        
        # Processar cartas em campo
        for i, card in enumerate(player['attack_bases']):
            if card:
                self.graveyard.append(card)
                player['attack_bases'][i] = None
        
        for i, card in enumerate(player['defense_bases']):
            if card:
                self.graveyard.append(card)
                player['defense_bases'][i] = None

        random.shuffle(self.deck)
 
    def check_winner(self):
        """Verifica se há um vencedor. Marca finished na primeira vez."""
        if self.finished and self.winner:
            return self.winner

        alive_players = []
        for username in self.players:
            pdata = self.player_data.get(username) or {}
            if pdata.get('life', 0) > 0 and not pdata.get('dead', False):
                alive_players.append(username)

        if len(alive_players) == 1:
            self.finished = True
            if not self.finished_at:
                import time as _time
                self.finished_at = _time.time()
            self.winner = alive_players[0]
            return self.winner
        if len(alive_players) == 0 and self.players:
            # empate técnico — ninguém vivo
            self.finished = True
            if not self.finished_at:
                import time as _time
                self.finished_at = _time.time()
            self.winner = None
            return None
        return None

    def end_game(self, winner_username=None):
        """Finaliza a partida explicitamente (admin / leave)."""
        if winner_username and winner_username in self.player_data:
            self.winner = winner_username
        elif not self.winner:
            self.check_winner()
        self.finished = True
        if not self.finished_at:
            import time as _time
            self.finished_at = _time.time()
        return self.winner
    
    def has_daylight_protection(self, player, card=None):
        """Capacete das Trevas, Manto do Eclipse (jogador ou equipado na criatura)."""
        equip = player.get('equipment') or {}
        for slot in ('helmet', 'armor', 'pants', 'boots', 'weapon'):
            item = equip.get(slot)
            if item and (item.get('daylight_protect') or item.get('id') in ('capacete_trevas', 'manto_eclipse')):
                return True
        if card:
            for eq in (card.get('equipped_items') or []):
                if eq.get('daylight_protect') or eq.get('id') in ('capacete_trevas', 'manto_eclipse'):
                    return True
        return False

    def apply_werewolf_forms(self):
        """Ajusta stats do Lobisomem do Crepúsculo conforme dia/noite."""
        is_night = self.time_of_day == 'night'
        for username in self.players:
            player = self.player_data[username]
            for base in ('attack_bases', 'defense_bases'):
                for card in player[base]:
                    if not card or not card.get('werewolf'):
                        continue
                    # stats base da forma
                    if is_night:
                        target_atk = card.get('night_attack', card.get('attack', 0))
                        target_life_cap = card.get('night_life', card.get('life', 0))
                        form = 'night'
                    else:
                        target_atk = card.get('day_attack', card.get('attack', 0))
                        target_life_cap = card.get('day_life', card.get('life', 0))
                        form = 'day'
                    old_form = card.get('werewolf_form')
                    # preservar bônus de equipamento em attack: recompute base + gear
                    gear_atk = 0
                    for eq in (card.get('equipped_items') or []):
                        if eq.get('ability') in ('crepusculo_dagger', 'orc_club') or eq.get('id') in (
                            'adaga_crepusculo', 'clava_orc',
                        ):
                            val = self.get_weapon_attack_value(player, eq)
                            eq['_applied_attack'] = val
                            gear_atk += val
                        else:
                            gear_atk += int(eq.get('attack') or 0)
                    gear_hp = sum((eq.get('protection') or 0) + (eq.get('life') or 0) for eq in (card.get('equipped_items') or []))
                    # Botas de Guerra: +atk se em ataque
                    if base == 'attack_bases':
                        for eq in (card.get('equipped_items') or []):
                            if eq.get('ability') == 'charge_bonus':
                                gear_atk += eq.get('attack_bonus', 0)
                    card['attack'] = target_atk + gear_atk
                    # vida: se mudou de forma, ajusta pro cap da forma (+ gear)
                    new_cap = target_life_cap + gear_hp
                    if old_form != form:
                        # ao trocar forma, preenche até o cap da nova forma (sem curar além)
                        card['life'] = min(card.get('life', new_cap), new_cap) if old_form else new_cap
                        if old_form is None or card.get('life', 0) <= 0:
                            card['life'] = new_cap
                        # se entrou na forma noturna, set life to night cap scaled
                        if form == 'night':
                            card['life'] = new_cap
                        else:
                            # dia: tanque — sobe vida se estava menor que day cap
                            card['life'] = max(card.get('life', 0), min(new_cap, target_life_cap + gear_hp))
                            card['life'] = new_cap
                        card['werewolf_form'] = form
                        broadcast_system_message(
                            self.game_id,
                            f'🐺 {card["name"]} de {username} assume forma de {"NOITE" if is_night else "DIA"} '
                            f'({card["life"]}❤️ / {card["attack"]}⚔️)!'
                        )
                    else:
                        card['attack'] = target_atk + gear_atk

    def _day_effects_signature(self):
        """ Estado relevante para dia/noite, sem contar stats recalculados.

        Inclui o ciclo para que a virada dia<->noite sempre reaplique, e os
        ids de cartas/equipamentos para que cartas recém-jogadas também sejam
        processadas sem recalcular em todos os turnos.
        """
        parts = []
        for username in self.players:
            player = self.player_data.get(username) or {}
            equip = player.get('equipment') or {}
            parts.append((
                username,
                tuple(sorted(
                    (slot, (item or {}).get('id'))
                    for slot, item in equip.items()
                )),
            ))
            for base in ('attack_bases', 'defense_bases'):
                for card in player.get(base) or []:
                    if not card:
                        parts.append(None)
                        continue
                    parts.append((
                        card.get('id'),
                        tuple((eq or {}).get('id') for eq in card.get('equipped_items') or []),
                        bool(card.get('dies_daylight')),
                        bool(card.get('night_creature')),
                        bool(card.get('werewolf')),
                    ))
        return (self.time_cycle, self.time_of_day, tuple(parts))

    def apply_day_effects(self, force=False):
        signature = self._day_effects_signature()
        if not force and signature == getattr(self, '_last_day_effects_signature', None):
            return

        for username in self.players:
            player = self.player_data[username]
            
            # Processar cartas em defesa
            for i, card in enumerate(player['defense_bases']):
                if card:
                    # Verificar se morre durante o dia (zumbis, vampiros)
                    if card.get('dies_daylight'):
                        if not self.has_daylight_protection(player, card):
                            self._handle_non_attack_death(player, 'defense_bases', i, card)
                            broadcast_system_message(
                                self.game_id,
                                f'☀️ {card["name"]} de {username} morreu com a luz do dia!'
                                + (' (foi para o cemitério)' if card.get('id') == 'zumbi' else ''),
                                fog_message=f'☀️ Uma criatura de {username} morreu com a luz do dia!',
                            )
                    
                    # Criaturas noturnas tomam 10 de dano
                    elif card.get('night_creature', False):
                        if self.has_daylight_protection(player, card):
                            continue
                        card_life = card.get('life', 0)
                        if card_life > 0:
                            new_life = max(0, card_life - 10)
                            card['life'] = new_life
                            self._damage_armor(card, 10)
                            
                            if new_life <= 0:
                                self._handle_non_attack_death(player, 'defense_bases', i, card)
                                broadcast_system_message(
                                    self.game_id,
                                    f'☀️ {card["name"]} de {username} foi destruído pelo sol! (-10❤️)'
                                    + (' (foi para o cemitério)' if card.get('id') == 'zumbi' else ''),
                                    fog_message=f'☀️ Uma criatura de {username} foi destruída pelo sol!',
                                )
            
            # Processar cartas em ataque
            for i, card in enumerate(player['attack_bases']):
                if card:
                    # Verificar se morre durante o dia (zumbis, vampiros)
                    if card.get('dies_daylight'):
                        if not self.has_daylight_protection(player, card):
                            self._handle_non_attack_death(player, 'attack_bases', i, card)
                            broadcast_system_message(
                                self.game_id,
                                f'☀️ {card["name"]} de {username} morreu com a luz do dia!'
                                + (' (foi para o cemitério)' if card.get('id') == 'zumbi' else ''),
                                fog_message=f'☀️ Uma criatura de {username} morreu com a luz do dia!',
                            )
                    
                    # Criaturas noturnas tomam 10 de dano
                    elif card.get('night_creature', False):
                        if self.has_daylight_protection(player, card):
                            continue
                        card_life = card.get('life', 0)
                        if card_life > 0:
                            new_life = max(0, card_life - 10)
                            card['life'] = new_life
                            self._damage_armor(card, 10)
                            
                            if new_life <= 0:
                                self._handle_non_attack_death(player, 'attack_bases', i, card)
                                broadcast_system_message(
                                    self.game_id,
                                    f'☀️ {card["name"]} de {username} foi destruído pelo sol! (-10❤️)'
                                    + (' (foi para o cemitério)' if card.get('id') == 'zumbi' else ''),
                                    fog_message=f'☀️ Uma criatura de {username} foi destruída pelo sol!',
                                )
        # lobisomem troca forma no ciclo (também à noite via toggle)
        self.apply_werewolf_forms()
        self.refresh_dynamic_weapon_bonuses()
        self._last_day_effects_signature = self._day_effects_signature()

    def swap_positions(self, username, pos1_type, pos1_index, pos2_type, pos2_index):
        """Troca duas cartas de posição"""
        player = self.player_data[username]
        free_swap = False
        boots = (player.get('equipment') or {}).get('boots')
        if boots and boots.get('ability') == 'free_swap' and not player.get('free_swap_used'):
            free_swap = True
        elif not self.can_act(username, 'swap'):
            return {'success': False, 'message': 'Você já realizou uma troca neste turno'}
        
        positions = {
            'attack': player['attack_bases'],
            'defense': player['defense_bases']
        }
        
        if pos1_type not in positions or pos2_type not in positions:
            return {'success': False, 'message': 'Tipo de posição inválido'}
        
        if pos1_index >= len(positions[pos1_type]) or pos2_index >= len(positions[pos2_type]):
            return {'success': False, 'message': 'Índice de posição inválido'}
        
        card1 = positions[pos1_type][pos1_index]
        card2 = positions[pos2_type][pos2_index]
        
        if not card1 and not card2:
            return {'success': False, 'message': 'Ambas as posições estão vazias'}
        
        positions[pos1_type][pos1_index] = card2
        positions[pos2_type][pos2_index] = card1
        
        if free_swap:
            player['free_swap_used'] = True
            msg = 'Cartas trocadas (Botas do Andarilho — troca grátis)!'
        else:
            self.use_action(username, 'swap')
            msg = 'Cartas trocadas com sucesso'
        
        return {
            'success': True,
            'swapped': True,
            'free_swap': free_swap,
            'message': msg
        }
    
    def get_weapon_attack_value(self, player, weapon):
        """Ataque efetivo de uma arma (efeitos dinâmicos: clava, adaga do crepúsculo)."""
        if not weapon:
            return 0

        ability = weapon.get('ability')
        wid = weapon.get('id')

        # Adaga do Crepúsculo: dia fraco / noite forte
        if ability == 'crepusculo_dagger' or wid == 'adaga_crepusculo':
            if self.time_of_day == 'night':
                return int(weapon.get('night_attack', 600))
            return int(weapon.get('day_attack', weapon.get('attack', 150)))

        base = int(weapon.get('attack', 0) or 0)

        # Clava do Orc: +50 por orc em bases de ataque (cap 3)
        if ability == 'orc_club' or wid == 'clava_orc':
            bonus = int(weapon.get('orc_bonus', 50))
            cap = int(weapon.get('orc_bonus_cap', 3))
            orcs = 0
            for card in (player or {}).get('attack_bases') or []:
                if not card:
                    continue
                cid = (card.get('id') or '')
                if cid == 'orc' or cid.startswith('orc'):
                    orcs += 1
            base += min(cap, orcs) * bonus

        return base

    def refresh_dynamic_weapon_bonuses(self):
        """Atualiza bônus de armas dinâmicas equipadas em criaturas (ex.: adaga dia/noite)."""
        for username in self.players:
            player = self.player_data.get(username)
            if not player:
                continue
            for base in ('attack_bases', 'defense_bases'):
                for card in player.get(base) or []:
                    if not card or card.get('type') != 'creature':
                        continue
                    for eq in card.get('equipped_items') or []:
                        if eq.get('ability') not in ('crepusculo_dagger', 'orc_club') and eq.get('id') not in (
                            'adaga_crepusculo', 'clava_orc',
                        ):
                            continue
                        old = int(eq.get('_applied_attack', 0) or 0)
                        new = self.get_weapon_attack_value(player, eq)
                        card['attack'] = int(card.get('attack', 0) or 0) - old + new
                        eq['_applied_attack'] = new

    def equip_item_to_creature(self, username, item_card_id, creature_card_id):
        """Equipa um item em uma criatura"""

        player = self.player_data.get(username)
        if not player:
            return {'success': False, 'message': 'Jogador não encontrado'}
        
        # Encontrar item na mão
        item_card = None
        item_index = -1
        
        for i, card in enumerate(player['hand']):
            if card['instance_id'] == item_card_id:
                item_card = card
                item_index = i
                break
        
        if not item_card:
            return {'success': False, 'message': 'Item não encontrado na mão'}
        
        if item_card.get('type') not in ['weapon', 'armor'] and item_card.get('id') not in ['lamina_almas', 'blade_vampires', 'blade_dragons', 'capacete_trevas']:
            return {'success': False, 'message': f'Esta carta ({item_card.get("type")}) não é um item equipável'}
        
        # Encontrar criatura alvo
        target_creature = None
        creature_location = None
        
        for base in ['attack_bases', 'defense_bases']:
            for i, card in enumerate(player[base]):
                if card and card.get('instance_id') == creature_card_id:
                    target_creature = card
                    creature_location = (base, i)
                    break
            if target_creature:
                break
        
        if not target_creature:
            return {'success': False, 'message': 'Criatura não encontrada em campo'}
        
        if target_creature.get('type') != 'creature':
            return {'success': False, 'message': 'Alvo não é uma criatura'}
        
        # Verificar restrições de equipamento
        if item_card.get('id') == 'blade_vampires' and target_creature.get('id') not in ['vampiro_tayler', 'vampiro_wers']:
            return {'success': False, 'message': 'Apenas vampiros podem usar a Blade of Vampires'}
        
        if item_card.get('id') == 'blade_dragons' and target_creature.get('id') not in ['elfo', 'vampiro_tayler', 'vampiro_wers', 'mago', 'mago_negro', 'rei_mago']:
            return {'success': False, 'message': 'Apenas elfos, magos e vampiros podem usar a Blade of Dragons'}
        
        if item_card.get('id') == 'lamina_almas' and target_creature.get('id') not in ['elfo', 'mago', 'mago_negro', 'rei_mago', 'vampiro_tayler', 'vampiro_wers']:
            return {'success': False, 'message': 'Apenas elfos, magos e vampiros podem usar a Lâmina das Almas'}

        if item_card.get('id') == 'adaga_crepusculo' or item_card.get('werewolf_only'):
            if not target_creature.get('werewolf') and target_creature.get('id') != 'lobisomem_crepusculo':
                return {'success': False, 'message': 'A Adaga do Crepúsculo só pode ser usada por Lobisomem do Crepúsculo'}

        if item_card.get('id') == 'cajado_mago_negro':
            races = item_card.get('equip_races') or ['mago', 'mago_negro', 'rei_mago']
            if target_creature.get('id') not in races:
                return {'success': False, 'message': 'O Cajado do Mago Negro só pode ser usado por magos'}
        
        # Formas bestiais não usam equipamento; a Adaga do Crepúsculo é a
        # exceção criada exclusivamente para o Lobisomem.
        if self._is_beast_creature(target_creature):
            allowed_beast_item = (
                item_card.get('werewolf_only') and target_creature.get('werewolf')
            )
            if not allowed_beast_item:
                return {
                    'success': False,
                    'message': f'{target_creature["name"]} tem forma bestial e não pode equipar itens',
                }

        if 'equipped_items' not in target_creature:
            target_creature['equipped_items'] = []

        # Um item por slot (arma, capacete, peitoral, calças e botas).
        item_slot = self._item_slot(item_card)
        if not item_slot:
            return {'success': False, 'message': 'Item sem slot de equipamento'}
        occupied = next(
            (eq for eq in target_creature['equipped_items']
             if self._item_slot(eq) == item_slot),
            None,
        )
        if occupied:
            slot_names = {
                'weapon': 'arma',
                'helmet': 'capacete',
                'armor': 'peitoral',
                'pants': 'calças',
                'boots': 'botas',
            }
            return {
                'success': False,
                'message': (
                    f'{target_creature["name"]} já tem um item no slot de '
                    f'{slot_names[item_slot]}: {occupied.get("name", "item")}'
                ),
            }

        # Remover item da mão
        player['hand'].pop(item_index)
        
        # Equipar item
        target_creature['equipped_items'].append(item_card)
        self._init_armor_durability(item_card)
        # Guarda os bônus realmente aplicados para poder desequipar depois
        item_card.pop('_applied_attack', None)
        item_card.pop('_applied_charge_bonus', None)
        item_card.pop('_applied_life', None)
        item_card.pop('_applied_spell_resist', None)

        # Armas dinâmicas (clava / adaga): aplica valor efetivo e guarda para refresh
        if item_card.get('ability') in ('crepusculo_dagger', 'orc_club') or item_card.get('id') in (
            'adaga_crepusculo', 'clava_orc',
        ):
            bonus = self.get_weapon_attack_value(player, item_card)
            target_creature['attack'] = target_creature.get('attack', 0) + bonus
            item_card['_applied_attack'] = bonus
        elif item_card.get('attack'):
            target_creature['attack'] = target_creature.get('attack', 0) + item_card['attack']
            item_card['_applied_attack'] = int(item_card['attack'])
        if item_card.get('attack_bonus') and item_card.get('ability') == 'charge_bonus':
            # Botas de Guerra: bônus só em ataque
            if creature_location and creature_location[0] == 'attack_bases':
                bonus = int(item_card.get('attack_bonus', 0))
                target_creature['attack'] = target_creature.get('attack', 0) + bonus
                item_card['_applied_charge_bonus'] = bonus
        applied_life = int(item_card.get('protection') or 0) + int(item_card.get('life') or 0)
        if applied_life:
            target_creature['life'] = target_creature.get('life', 0) + applied_life
            item_card['_applied_life'] = applied_life

        # Peitoral de Carvalho: ward em elfo/ninfa
        if item_card.get('ability') == 'nature_ward':
            cid = target_creature.get('id') or ''
            if cid in (item_card.get('spell_resist_races') or []) or 'elfo' in cid or 'ninfa' in cid:
                target_creature['spell_resist_charges'] = target_creature.get('spell_resist_charges', 0) + 1
                item_card['_applied_spell_resist'] = 1
                broadcast_system_message(
                    self.game_id,
                    f'🌳 Peitoral de Carvalho: {target_creature["name"]} resiste ao próximo feitiço hostil!',
                    fog_message=f'🌳 Peitoral de Carvalho: uma criatura de {username} resiste ao próximo feitiço hostil!',
                )
        
        broadcast_system_message(
            self.game_id,
            f'🔧 {username} equipou {item_card["name"]} em {target_creature["name"]}',
            fog_message=f'🔧 {username} equipou um item em uma criatura (névoa)',
        )

        return {
            'success': True,
            'creature': target_creature['name'],
            'item': item_card['name'],
            'message': f"{item_card['name']} equipado em {target_creature['name']}"
        }

    def unequip_item_from_creature(self, username, item_card_id, creature_card_id):
        """Remove um item equipado e devolve os bônus e o item para a mão."""
        player = self.player_data.get(username)
        if not player:
            return {'success': False, 'message': 'Jogador não encontrado'}

        target_creature = None
        creature_location = None
        for base in ('attack_bases', 'defense_bases'):
            for i, card in enumerate(player.get(base) or []):
                if card and card.get('instance_id') == creature_card_id:
                    target_creature = card
                    creature_location = (base, i)
                    break
            if target_creature:
                break

        if not target_creature:
            return {'success': False, 'message': 'Criatura não encontrada em campo'}

        equipped = target_creature.get('equipped_items') or []
        item = next(
            (eq for eq in equipped if eq and eq.get('instance_id') == item_card_id),
            None,
        )
        if not item:
            return {'success': False, 'message': 'Item não está equipado nesta criatura'}

        if self._is_armor_item(item) and not self._armor_is_pristine(item):
            return {
                'success': False,
                'message': (
                    f"❌ {item.get('name', 'A armadura')} já absorveu dano "
                    f"({item.get('durability', 0)}/{item.get('max_durability', 0)} de durabilidade) "
                    "e não pode ser removida."
                ),
            }

        is_dynamic_weapon = (
            item.get('ability') in ('crepusculo_dagger', 'orc_club')
            or item.get('id') in ('adaga_crepusculo', 'clava_orc')
        )
        if '_applied_attack' in item:
            attack_bonus = int(item.get('_applied_attack') or 0)
        elif is_dynamic_weapon:
            attack_bonus = int(self.get_weapon_attack_value(player, item))
        else:
            attack_bonus = int(item.get('attack') or 0)

        charge_bonus = 0
        if (
            item.get('ability') == 'charge_bonus'
            and creature_location
            and creature_location[0] == 'attack_bases'
        ):
            charge_bonus = int(
                item.get('_applied_charge_bonus', item.get('attack_bonus', 0)) or 0
            )

        life_bonus = int(
            item.get('_applied_life',
                     int(item.get('protection') or 0) + int(item.get('life') or 0)) or 0
        )
        ward_bonus = int(item.get('_applied_spell_resist') or 0)

        target_creature['attack'] = max(
            0,
            int(target_creature.get('attack') or 0) - attack_bonus - charge_bonus,
        )
        target_creature['life'] = max(
            0,
            int(target_creature.get('life') or 0) - life_bonus,
        )
        if ward_bonus:
            target_creature['spell_resist_charges'] = max(
                0,
                int(target_creature.get('spell_resist_charges') or 0) - ward_bonus,
            )

        equipped.remove(item)
        if not equipped:
            target_creature.pop('equipped_items', None)
        player.setdefault('hand', []).append(item)

        for key in ('_applied_attack', '_applied_charge_bonus', '_applied_life', '_applied_spell_resist'):
            item.pop(key, None)

        broadcast_system_message(
            self.game_id,
            f'🔧 {username} desequipou {item.get("name", "um item")} de {target_creature["name"]}',
            fog_message=f'🔧 {username} desequipou um item de uma criatura (névoa)',
        )

        return {
            'success': True,
            'creature': target_creature['name'],
            'item': item.get('name', 'Item'),
            'message': f"{item.get('name', 'Item')} desequipado de {target_creature['name']} e voltou para a sua mão",
        }

    def get_graveyard_cards(self):
        """Retorna lista de cartas no cemitério"""
        graveyard_info = []
        for card in self.graveyard:
            card_info = {
                'instance_id': card.get('instance_id', str(uuid.uuid4())[:8]),
                'name': card.get('name', 'Carta sem nome'),
                'type': card.get('type', 'unknown'),
                'description': card.get('description', ''),
                'life': card.get('life', 0),
                'attack': card.get('attack', 0),
                'protection': card.get('protection', 0),
                'id': card.get('id', 'unknown')
            }
            graveyard_info.append(card_info)
        return graveyard_info

    def revive_from_graveyard(self, username, target_card_id):
        """Revive uma carta do cemitério usando 4 runas"""

        player = self.player_data.get(username)
        if not player:
            return {'success': False, 'message': 'Jogador não encontrado'}

        if 'no_runes' in self.modifiers:
            return {'success': False, 'message': '❌ Este jogo tem o modificador "Sem Runas" ativo. Não é possível reviver cartas do cemitério!'}
        
        runes_in_hand = []
        for card in player['hand']:
            if card.get('type') == 'rune' or card.get('id') == 'runa':
                runes_in_hand.append(card)
        
        if len(runes_in_hand) < 4:
            return {'success': False, 'message': f'Você precisa de 4 runas na mão (tem {len(runes_in_hand)})'}
        
        target_card = None
        card_index = -1
        
        for i, card in enumerate(self.graveyard):
            if card['instance_id'] == target_card_id:
                target_card = card
                card_index = i
                break
        
        if not target_card:
            for i, card in enumerate(self.graveyard):
                if card['name'].lower() == target_card_id.lower():
                    target_card = card
                    card_index = i
                    break
        
        if not target_card:
            return {'success': False, 'message': 'Carta não encontrada no cemitério'}
        
        self.graveyard.pop(card_index)
        
        runes_removed = 0
        new_hand = []
        for card in player['hand']:
            if (card.get('type') == 'rune' or card.get('id') == 'runa') and runes_removed < 4:
                runes_removed += 1
                self.graveyard.append(card)
            else:
                new_hand.append(card)
        
        player['hand'] = new_hand
        
        if target_card.get('type') == 'creature':
            original_card = CARDS.get(target_card['id'], {})
            if original_card and 'life' in original_card:
                target_card['life'] = original_card['life']

        # Reviver resetou a cota da Medusa; Fênix revivida por runas cancela o ovo
        if target_card.get('id') == 'medusa':
            target_card['medusa_petrify_uses'] = 2
            target_card.pop('petrified', None)
        if target_card.get('id') == 'fenix':
            self._cancel_phoenix_eggs(target_card.get('instance_id'))
        
        player['hand'].append(target_card)
        
        return {
            'success': True,
            'card': {
                'name': target_card['name'],
                'type': target_card.get('type', 'unknown')
            },
            'message': f"{target_card['name']} foi revivido do cemitério!"
        }
    
    def call_centaurs(self, username):
        """Habilidade especial do Super Centauro: Coleta todos os centauros em campo de todos os jogadores para a mão do usuário"""
        if not self.can_act(username, 'call_centaurs'):
            return {'success': False, 'message': 'Você já usou esta habilidade neste turno'}
        
        player = self.player_data.get(username)
        if not player or player.get('dead', False):
            return {'success': False, 'message': 'Jogador inválido ou morto'}
        
        # Verificar se tem Super Centauro em campo (ataque ou defesa)
        has_super_centauro = False
        super_centauro_card = None
        super_centauro_location = None
        
        for base_type in ['attack_bases', 'defense_bases']:
            for i, card in enumerate(player[base_type]):
                if card and card.get('id') == 'super_centauro':
                    has_super_centauro = True
                    super_centauro_card = card
                    super_centauro_location = (base_type, i)
                    break
            if has_super_centauro:
                break
        
        if not has_super_centauro:
            return {'success': False, 'message': 'Você precisa ter um Super Centauro em campo para usar esta habilidade'}
        
        # Verificar se a habilidade já foi usada neste Super Centauro
        if super_centauro_card.get('call_centaurs_used', False):
            return {'success': False, 'message': 'Este Super Centauro já usou sua habilidade de chamar centauros'}
        
        # Coletar todos os centauros em campo de todos os jogadores
        centaurs_collected = []
        centaurs_info = []
        
        for target_username in self.players:
            target_player = self.player_data[target_username]
            if target_player.get('dead', False):
                continue
            
            # Verificar em bases de ataque
            for i, card in enumerate(target_player['attack_bases']):
                if card and card.get('id') == 'centauro':
                    centaurs_collected.append({
                        'player': target_username,
                        'base_type': 'attack_bases',  # CORRIGIDO: usar o nome completo
                        'index': i,
                        'card': card
                    })
            
            # Verificar em bases de defesa
            for i, card in enumerate(target_player['defense_bases']):
                if card and card.get('id') == 'centauro':
                    centaurs_collected.append({
                        'player': target_username,
                        'base_type': 'defense_bases',  # CORRIGIDO: usar o nome completo
                        'index': i,
                        'card': card
                    })
        
        if not centaurs_collected:
            return {'success': False, 'message': 'Não há centauros em campo para coletar'}
        
        # Coletar os centauros e adicionar à mão do jogador
        for centaur_data in centaurs_collected:
            target_player = self.player_data[centaur_data['player']]
            card = centaur_data['card']
            
            # Remover do campo - agora 'base_type' já é 'attack_bases' ou 'defense_bases'
            target_player[centaur_data['base_type']][centaur_data['index']] = None
            
            # Adicionar à mão do jogador que usou a habilidade
            player['hand'].append(card)
            
            centaurs_info.append({
                'card_name': card['name'],
                'from_player': centaur_data['player']
            })
        
        # Marcar que a habilidade foi usada neste Super Centauro
        super_centauro_card['call_centaurs_used'] = True
        
        self.use_action(username, 'call_centaurs')
        
        broadcast_system_message(self.game_id, 
            f'🐎 {username} usou a habilidade CHAMAR CENTAUROS do Super Centauro! Coletou {len(centaurs_info)} centauro(s) de todos os jogadores!')
        
        return {
            'success': True,
            'centaurs_collected': len(centaurs_info),
            'centaurs': centaurs_info,
            'message': f'🐎 Você coletou {len(centaurs_info)} centauro(s) para sua mão!'
        }
    def has_call_centaurs_available(self, username):
        """Verifica se o jogador pode usar a habilidade Chamar Centauros"""
        player = self.player_data.get(username)
        if not player or player.get('dead', False):
            return False
        
        # Verificar se o jogador tem Super Centauro em campo que ainda não usou a habilidade
        for base_type in ['attack_bases', 'defense_bases']:
            for card in player[base_type]:
                if card and card.get('id') == 'super_centauro':
                    if not card.get('call_centaurs_used', False):
                        return True
        return False

    def toggle_time_of_day(self, username):
        """Habilidade da Fênix: muda o ciclo de dia para noite ou vice-versa"""
        # Verificar se o modificador disable_daycicle está ativo
        if 'disable_daycicle' in self.modifiers:
            return {'success': False, 'message': '❌ Modificador "Desativar Ciclo de Dia/Noite" está ativo. Não é possível alterar o ciclo!'}
        
        if not self.can_act(username, 'toggle_time'):
            return {'success': False, 'message': 'Você já usou esta habilidade neste turno'}
        
        player = self.player_data.get(username)
        if not player or player.get('dead', False):
            return {'success': False, 'message': 'Jogador inválido ou morto'}
        
        # Verificar se tem Fênix em campo (ataque ou defesa)
        has_fenix = False
        fenix_card = None
        fenix_location = None
        
        for base_type in ['attack_bases', 'defense_bases']:
            for i, card in enumerate(player[base_type]):
                if card and card.get('id') == 'fenix':
                    has_fenix = True
                    fenix_card = card
                    fenix_location = (base_type, i)
                    break
            if has_fenix:
                break
        
        if not has_fenix:
            return {'success': False, 'message': 'Você precisa ter uma Fênix em campo para usar esta habilidade'}
        
        # Mudar o ciclo
        old_time = self.time_of_day
        self.time_of_day = "night" if self.time_of_day == "day" else "day"
        
        # Aplicar efeitos do dia se mudou para dia; sempre atualiza lobisomens
        if self.time_of_day == "day":
            self.apply_day_effects()
        else:
            self.apply_werewolf_forms()
            self.refresh_dynamic_weapon_bonuses()
        
        self.use_action(username, 'toggle_time')
        
        broadcast_system_message(self.game_id, 
            f'🔥 {username} usou a habilidade da Fênix! O ciclo mudou de {old_time.upper()} para {self.time_of_day.upper()}!')
        
        return {
            'success': True,
            'old_time': old_time,
            'new_time': self.time_of_day,
            'message': f'🌓 O ciclo mudou de {old_time.upper()} para {self.time_of_day.upper()}!'
        }
    def has_toggle_time_available(self, username):
        """Verifica se o jogador pode usar a habilidade da Fênix de mudar ciclo"""
        player = self.player_data.get(username)
        if not player or player.get('dead', False):
            return False
        
        # Verificar se o jogador tem Fênix em campo que ainda não usou a habilidade neste turno
        for base_type in ['attack_bases', 'defense_bases']:
            for card in player[base_type]:
                if card and card.get('id') == 'fenix':
                    if not card.get('toggle_time_used_turn', False):
                        return True
        return False

    # Métodos para rituais
    def get_available_rituals(self, username):
        """Retorna lista de rituais disponíveis"""
        return RitualManager.get_available_rituals(self, username)
    def has_available_rituals(self, username):
        """Verifica se o jogador tem rituais disponíveis (na mão ou por Mago Negro)"""
        player = self.player_data.get(username)
        if not player or player.get('dead', False):
            return False
        
        # Verificar se tem Mago Negro em campo
        has_mago_negro = False
        for card in player['attack_bases'] + player['defense_bases']:
            if card and card.get('id') == 'mago_negro':
                has_mago_negro = True
                break
        
        # Se tem Mago Negro, sempre pode realizar rituais
        if has_mago_negro:
            return True
        
        # Verificar se tem carta de ritual na mão
        for card in player['hand']:
            if card and card.get('type') == 'ritual':
                return True
        
        return False
    def perform_ritual(self, username, ritual_id, target_username=None):
        """Realiza um ritual"""
        if not self.can_act(username, 'ritual'):
            return {'success': False, 'message': 'Você já realizou um ritual neste turno'}
        
        player = self.player_data[username]
        
        has_mago_negro = False
        for card in player['attack_bases'] + player['defense_bases']:
            if card and card['id'] == 'mago_negro':
                has_mago_negro = True
                break
        
        # Localizar a carta de ritual, mas NÃO consumir ainda: só depois de
        # validar as condições (senão a carta some em um ritual que falhou).
        ritual_index = -1
        if not has_mago_negro:
            ritual_card = None
            for i, card in enumerate(player['hand']):
                if card['id'] == ritual_id:
                    ritual_card = card
                    ritual_index = i
                    break
            
            if not ritual_card:
                return {'success': False, 'message': 'Você não tem esta carta de ritual'}
        
        if ritual_id == 'ritual_157':
            if not target_username:
                return {'success': False, 'message': 'Selecione um alvo para o Ritual 157'}
            if target_username not in self.player_data:
                return {'success': False, 'message': 'Alvo inválido'}
            
            can_cast, message = RitualManager.check_ritual_157(self, username)
            if not can_cast:
                return {'success': False, 'message': message}
            
            if ritual_index >= 0:
                player['hand'].pop(ritual_index)
            result = RitualManager.execute_ritual_157(self, username, target_username)
            
        elif ritual_id == 'ritual_amor':
            if not target_username:
                return {'success': False, 'message': 'Selecione o alvo da profecia'}
            if target_username not in self.player_data:
                return {'success': False, 'message': 'Alvo inválido'}
            
            can_cast, message = RitualManager.check_ritual_amor(self, username)
            if not can_cast:
                return {'success': False, 'message': message}
            
            target = self.player_data[target_username]
            has_profecia = False
            if target.get('profecia_alvo') or any(effect.get('type') == 'profecia_morte' for effect in target['active_effects']):
                has_profecia = True
            
            if not has_profecia:
                return {'success': False, 'message': 'O alvo não possui nenhuma profecia ativa'}
            
            if ritual_index >= 0:
                player['hand'].pop(ritual_index)
            result = RitualManager.execute_ritual_amor(self, username, target_username)
        
        else:
            return {'success': False, 'message': 'Ritual desconhecido'}
        
        self.use_action(username, 'ritual')
        result['ritual_id'] = ritual_id
        return result

    # Métodos para magias
    def cast_spell(self, username, spell_card_id, target_username=None, target_card_id=None):
        """Usa um feitiço com suporte para Rei Mago/Mago Negro"""
        
        if not self.can_act(username, 'spell'):
            return {'success': False, 'message': 'Você já usou um feitiço neste turno'}
        
        player = self.player_data[username]
        
        # Verificar se pode usar feitiços
        can_cast = False
        caster_type = None
        mage_card = None
        
        for card in player['attack_bases'] + player['defense_bases']:
            if card and card.get('type') == 'creature':
                if card['id'] == 'mago' and not card.get('blocked', False):
                    can_cast = True
                    caster_type = 'mago'
                    mage_card = card
                elif card['id'] == 'rei_mago':
                    can_cast = True
                    caster_type = 'rei_mago'
                    mage_card = card
                elif card['id'] == 'mago_negro':
                    can_cast = True
                    caster_type = 'mago_negro'
                    mage_card = card
        
        if not can_cast:
            return {'success': False, 'message': 'Você precisa de um Mago em campo para usar feitiços'}
        
        # Procurar o feitiço
        spell_card = None
        
        # Se for Rei Mago ou Mago Negro, pode usar qualquer feitiço (não precisa ter na mão)
        if caster_type in ['rei_mago', 'mago_negro']:
            # Procurar o feitiço pelo ID na definição de cartas
            if spell_card_id in CARDS and CARDS[spell_card_id].get('type') == 'spell':
                spell_info = CARDS[spell_card_id].copy()
                spell_info['instance_id'] = str(uuid.uuid4())[:8]
                spell_card = spell_info
            else:
                # Se não encontrar pelo ID, procurar pelo nome
                for card_id, card_info in CARDS.items():
                    if card_info.get('type') == 'spell' and card_info['name'].lower() == spell_card_id.lower():
                        spell_info = card_info.copy()
                        spell_info['instance_id'] = str(uuid.uuid4())[:8]
                        spell_card = spell_info
                        break
                
                if not spell_card:
                    return {'success': False, 'message': 'Feitiço não encontrado'}
        else:
            # Procurar feitiço na mão
            spell_index = -1
            for i, card in enumerate(player['hand']):
                if card['instance_id'] == spell_card_id or card['id'] == spell_card_id:
                    spell_card = card
                    spell_index = i
                    break
            
            if not spell_card:
                return {'success': False, 'message': 'Feitiço não encontrado na mão'}
            
            # Remover da mão
            player['hand'].pop(spell_index)
        
        # Aplicar efeito do feitiço
        result = self.apply_spell_effect(spell_card, username, target_username, target_card_id, caster_type)

        # Registrar último feitiço (Eco do Grimório não sobrescreve com ele mesmo se falhou)
        if spell_card.get('id') != 'feitico_eco_grimorio' and result.get('type') not in ('error', 'need_target', 'unknown'):
            self.last_spell_id = spell_card.get('id')
        
        # Feitiço volta para o deck (embaixo)
        self.deck.append(spell_card)
        shuffle(self.deck)
        
        self.use_action(username, 'spell')

        broadcast_system_message(
            self.game_id,
            f'✨ {username} usou {spell_card["name"]} {f"em {target_username}" if target_username else ""}',
            fog_message=f'✨ {username} usou um feitiço' + (f' em {target_username}' if target_username else '') + ' (névoa)',
        )
        
        return {
            'success': True,
            'spell': spell_card,
            'effect': result,
            'caster_type': caster_type
        }

    def _find_card_on_field(self, instance_id):
        for uname in self.players:
            for base in ('attack_bases', 'defense_bases'):
                for idx, card in enumerate(self.player_data[uname][base]):
                    if card and card.get('instance_id') == instance_id:
                        return uname, base, idx, card
        return None

    def _staff_spell_bonus(self, player):
        """Cajado do Mago Negro: +spell_power em cura/buff se equipado no jogador ou em mago."""
        bonus = 0
        if not player:
            return 0
        w = (player.get('equipment') or {}).get('weapon')
        if w and (w.get('id') == 'cajado_mago_negro' or w.get('ability') == 'dark_staff'):
            bonus = max(bonus, int(w.get('spell_power', 256)))
        for base in ('attack_bases', 'defense_bases'):
            for card in player.get(base) or []:
                if not card:
                    continue
                for eq in card.get('equipped_items') or []:
                    if eq.get('id') == 'cajado_mago_negro' or eq.get('ability') == 'dark_staff':
                        bonus = max(bonus, int(eq.get('spell_power', 256)))
        return bonus

    def _try_spell_resist(self, target_card):
        """Peitoral de Carvalho: gasta 1 carga de resist."""
        if target_card and target_card.get('spell_resist_charges', 0) > 0:
            target_card['spell_resist_charges'] -= 1
            return True
        return False

    def apply_spell_effect(self, spell, caster_username, target_username=None, target_card_id=None, caster_type=None):
        """Aplica o efeito específico do feitiço"""
        spell_id = spell['id']
        caster = self.player_data[caster_username]
        
        # Se for Rei Mago ou Mago Negro e não tiver alvo definido para alguns feitiços
        if caster_type in ['rei_mago', 'mago_negro'] and not target_username:
            # Para feitiços que precisam de alvo, retornar erro
            if spell_id in ['feitico_cortes', 'feitico_troca', 'feitico_capitalista', 'feitico_cura', 'feitico_julgamento_aurora']:
                return {'type': 'need_target', 'message': 'Este feitiço requer um alvo'}
        
        # Aplicar efeitos específicos
        if spell_id == 'feitico_cortes':
            # Aumenta ataque de um monstro (+ Cajado do Mago Negro)
            power = 1024 + self._staff_spell_bonus(caster)
            if target_card_id:
                found = self._find_card_on_field(target_card_id)
                if found:
                    uname, base, idx, card = found
                    if self._try_spell_resist(card):
                        return {'type': 'resisted', 'target': card['name'], 'message': f'{card["name"]} resistiu ao feitiço!'}
                    card['attack'] = card.get('attack', 0) + power
                    return {'type': 'buff', 'target': card['name'], 'effect': f'+{power} ataque'}
            return {'type': 'error', 'message': 'Alvo não encontrado'}
        
        elif spell_id == 'feitico_duro_matar':
            # Aumenta defesa do jogador (+ Cajado)
            power = 1024 + self._staff_spell_bonus(caster)
            if target_username:
                self.player_data[target_username]['life'] += power
                return {'type': 'buff', 'target': self.player_data[target_username]['name'], 'effect': f'+{power} vida'}
            return {'type': 'error', 'message': 'Alvo não especificado'}
        
        elif spell_id == 'feitico_troca':
            # Troca cartas de defesa por ataque
            if target_username:
                target = self.player_data[target_username]
                attack_bases = target['attack_bases'].copy()
                defense_bases = target['defense_bases'].copy()
                target['attack_bases'] = defense_bases
                target['defense_bases'] = attack_bases
                return {'type': 'swap', 'target': target['name']}
            return {'type': 'error', 'message': 'Alvo não especificado'}
        
        elif spell_id == 'feitico_comunista':
            # Todas as cartas das mãos voltam para a pilha
            lost_eggs = self._lose_phoenix_eggs_on_card_reset()
            for player_uname in self.players:
                player = self.player_data[player_uname]
                for card in player['hand']:
                    self.deck.append(card)
                player['hand'] = []
            random.shuffle(self.deck)
            result = {'type': 'reset_hands'}
            if lost_eggs:
                result['phoenix_eggs_lost'] = lost_eggs
            return result
        
        elif spell_id == 'feitico_silencio':
            # Próximas duas rodadas sem armadilhas
            for player_uname in self.players:
                self.player_data[player_uname]['active_effects'].append({
                    'type': 'silence',
                    'duration': 2
                })
            return {'type': 'silence', 'duration': 2}
        
        elif spell_id == 'feitico_para_sempre':
            # Reverte efeito Blade of Vampires
            for player_uname in self.players:
                player = self.player_data[player_uname]
                for base in ['attack_bases', 'defense_bases']:
                    for card in player[base]:
                        if card and card.get('vampire_effect'):
                            card['vampire_effect'] = False
                            if 'dies_daylight' in card:
                                del card['dies_daylight']
            return {'type': 'revert_vampire', 'message': 'Efeito de vampiro revertido'}
        
        elif spell_id == 'feitico_capitalista':
            # Troca cartas com outros jogadores
            if target_username:
                source_player = caster
                target_player = self.player_data[target_username]
                
                if len(source_player['hand']) > 0 and len(target_player['hand']) > 0:
                    source_card = random.choice(source_player['hand'])
                    target_card = random.choice(target_player['hand'])
                    
                    source_player['hand'].remove(source_card)
                    target_player['hand'].remove(target_card)
                    
                    source_player['hand'].append(target_card)
                    target_player['hand'].append(source_card)
                    
                    return {
                        'type': 'trade', 
                        'target': target_username,
                        'message': f'Cartas trocadas entre {caster_username} e {target_username}'
                    }
                return {'type': 'trade_failed', 'message': 'Não foi possível trocar cartas'}
            return {'type': 'error', 'message': 'Alvo não especificado'}
        
        elif spell_id == 'feitico_cura':
            # Cura o jogador alvo (+ bônus do Cajado do Mago Negro)
            heal_amount = 1024 + self._staff_spell_bonus(caster)
            if target_username:
                self.player_data[target_username]['life'] += heal_amount
                return {
                    'type': 'heal', 
                    'target': self.player_data[target_username]['name'], 
                    'amount': heal_amount,
                    'message': f'{self.player_data[target_username]["name"]} recebeu {heal_amount} de cura!'
                }
            else:
                # Se não tiver alvo, cura a si mesmo
                self.player_data[caster_username]['life'] += heal_amount
                return {
                    'type': 'heal', 
                    'target': self.player_data[caster_username]['name'], 
                    'amount': heal_amount,
                    'message': f'{self.player_data[caster_username]["name"]} recebeu {heal_amount} de cura!'
                }

        elif spell_id == 'feitico_clareira_lua':
            self.time_of_day = 'night'
            self.apply_werewolf_forms()
            self.refresh_dynamic_weapon_bonuses()
            broadcast_system_message(self.game_id, '🌙 Clareira da Lua! A noite cai sobre o campo!')
            return {'type': 'force_night', 'time_of_day': 'night', 'message': 'Ciclo forçado para NOITE'}

        elif spell_id == 'feitico_julgamento_aurora':
            # Destrói 1 criatura noturna (target_card_id ou primeira encontrada do alvo)
            def is_nocturnal(c):
                if not c:
                    return False
                if c.get('dies_daylight') or c.get('night_creature') or c.get('werewolf'):
                    return True
                cid = (c.get('id') or '') + ' ' + (c.get('name') or '')
                cid = cid.lower()
                return any(x in cid for x in ('zumbi', 'vampiro', 'lobisomem'))

            if target_card_id:
                found = self._find_card_on_field(target_card_id)
                if found:
                    uname, base, idx, card = found
                    if uname == caster_username:
                        return {'type': 'error', 'message': 'Escolha uma criatura inimiga'}
                    if not is_nocturnal(card):
                        return {'type': 'error', 'message': 'O alvo não é uma criatura noturna'}
                    if self._try_spell_resist(card):
                        return {'type': 'resisted', 'target': card['name'], 'message': f'{card["name"]} resistiu!'}
                    self.graveyard.append(card)
                    self.player_data[uname][base][idx] = None
                    broadcast_system_message(
                        self.game_id,
                        f'☀️ Julgamento da Aurora destruiu {card["name"]} de {uname}!',
                        fog_message=f'☀️ Julgamento da Aurora destruiu uma criatura noturna de {uname}!',
                    )
                    return {'type': 'destroy', 'target': card['name'], 'owner': uname}
                return {'type': 'error', 'message': 'Carta alvo não encontrada'}
            # sem card id: pega do target_username
            if target_username and target_username in self.player_data:
                target = self.player_data[target_username]
                for base in ('attack_bases', 'defense_bases'):
                    for idx, card in enumerate(target[base]):
                        if is_nocturnal(card):
                            if self._try_spell_resist(card):
                                return {'type': 'resisted', 'target': card['name']}
                            name = card['name']
                            self.graveyard.append(card)
                            target[base][idx] = None
                            broadcast_system_message(
                                self.game_id,
                                f'☀️ Julgamento da Aurora destruiu {name} de {target_username}!',
                                fog_message=f'☀️ Julgamento da Aurora destruiu uma criatura noturna de {target_username}!',
                            )
                            return {'type': 'destroy', 'target': name, 'owner': target_username}
                return {'type': 'error', 'message': 'Nenhuma criatura noturna no alvo'}
            return {'type': 'error', 'message': 'Alvo não especificado'}

        elif spell_id == 'feitico_selo_silencio':
            caster['active_effects'].append({
                'type': 'trap_silence_next_attack',
                'duration': 1
            })
            return {
                'type': 'trap_silence',
                'message': 'Próximo ataque não ativa armadilhas'
            }

        elif spell_id == 'feitico_eco_grimorio':
            if not self.last_spell_id or self.last_spell_id == 'feitico_eco_grimorio':
                return {'type': 'error', 'message': 'Nenhum feitiço anterior para copiar'}
            if self.last_spell_id not in CARDS:
                return {'type': 'error', 'message': 'Feitiço ecoado inválido'}
            echo = CARDS[self.last_spell_id].copy()
            echo['instance_id'] = str(uuid.uuid4())[:8]
            # reentrada: aplica o efeito copiado (sem registrar eco de novo no last se for eco)
            saved = self.last_spell_id
            result = self.apply_spell_effect(echo, caster_username, target_username, target_card_id, caster_type)
            self.last_spell_id = saved  # mantém o original copiado
            result['echo_of'] = saved
            result['message'] = f'Eco copiou {echo.get("name")}!'
            return result

        return {'type': 'unknown', 'message': 'Efeito desconhecido'}
        
    def get_available_spells(self, username):
        """Retorna lista de feitiços disponíveis baseado nos magos em campo"""
        player = self.player_data[username]
        available_spells = []
        
        # Verificar tipos de magos em campo
        has_rei_mago = False
        has_mago_negro = False
        has_common_mage = False
        
        for card in player['attack_bases'] + player['defense_bases']:
            if card and card.get('type') == 'creature':
                if card['id'] == 'rei_mago':
                    has_rei_mago = True
                elif card['id'] == 'mago_negro':
                    has_mago_negro = True
                elif card['id'] == 'mago':
                    has_common_mage = True
        
        # Se tem Rei Mago ou Mago Negro, listar TODOS os feitiços da definição CARDS
        if has_rei_mago or has_mago_negro:
            # Coletar todos os feitiços da definição CARDS
            for card_id, card_info in CARDS.items():
                if card_info.get('type') == 'spell':
                    spell = card_info.copy()
                    spell['instance_id'] = f"spell_{card_id}"  # ID virtual para referência
                    available_spells.append(spell)
        else:
            # Apenas feitiços na mão
            available_spells = [card for card in player['hand'] if card.get('type') == 'spell']
        
        return {
            'success': True,
            'has_mage': has_common_mage or has_rei_mago or has_mago_negro,
            'has_rei_mago': has_rei_mago,
            'has_mago_negro': has_mago_negro,
            'spells': available_spells,
            'spells_in_hand': [card for card in player['hand'] if card.get('type') == 'spell']
        }
    def toggle_mage_block(self, username, target_username, target_card_id):
        """Rei Mago bloqueia/desbloqueia um mago"""
        if not self.can_act(username, 'block'):
            return {'success': False, 'message': 'Você já usou esta habilidade neste turno'}
        
        player = self.player_data[username]
        
        # Verificar se tem Rei Mago
        has_rei_mago = False
        for card in player['attack_bases'] + player['defense_bases']:
            if card and card['id'] == 'rei_mago':
                has_rei_mago = True
                break
        
        if not has_rei_mago:
            return {'success': False, 'message': 'Você precisa do Rei Mago em campo'}
        
        # Encontrar o mago alvo
        target_player = self.player_data[target_username]
        target_card = None
        card_location = None
        
        for base in ['attack_bases', 'defense_bases']:
            for i, card in enumerate(target_player[base]):
                if card and card['instance_id'] == target_card_id:
                    target_card = card
                    card_location = (base, i)
                    break
        
        if not target_card or target_card['id'] not in ['mago', 'rei_mago', 'mago_negro']:
            return {'success': False, 'message': 'Alvo não é um mago'}
        
        # Alternar bloqueio
        if 'blocked' in target_card and target_card['blocked']:
            target_card['blocked'] = False
            message = f"Mago {target_card['name']} desbloqueado"
        else:
            target_card['blocked'] = True
            message = f"Mago {target_card['name']} bloqueado"
        
        self.use_action(username, 'block')
        
        return {
            'success': True,
            'message': message,
            'target_card': target_card['name'],
            'blocked': target_card.get('blocked', False)
        }

    def get_prophet_usage_count(self, username):
        """Retorna quantas vezes o Profeta do jogador já usou a habilidade"""
        player = self.player_data.get(username)
        if not player:
            return 0
        
        # Verificar se tem Profeta em campo
        for base_type in ['attack_bases', 'defense_bases']:
            for card in player[base_type]:
                if card and card.get('id') == 'profeta':
                    return card.get('prophet_uses', 0)
        return 0
    def has_prophet_available(self, username):
        """Verifica se o jogador pode usar a habilidade do Profeta (máximo 2 usos)"""
        player = self.player_data.get(username)
        if not player or player.get('dead', False):
            return False
        
        # Verificar se o jogador tem Profeta em campo
        for base_type in ['attack_bases', 'defense_bases']:
            for card in player[base_type]:
                if card and card.get('id') == 'profeta':
                    uses = card.get('prophet_uses', 0)
                    if uses < 2:  # Máximo 2 usos
                        return True
        return False

    def get_prophet_uses_remaining(self, username):
        """Retorna quantos usos restam para o Profeta do jogador"""
        player = self.player_data.get(username)
        if not player:
            return 0
        
        for base_type in ['attack_bases', 'defense_bases']:
            for card in player[base_type]:
                if card and card.get('id') == 'profeta':
                    uses = card.get('prophet_uses', 0)
                    if uses >= 2:
                        return 0
                    return 2 - uses
        return 0

    def prophet_curse(self, username, target_player_id, target_card_id):
        if 'no_prophet' in self.modifiers:
            return {'success': False, 'message': 'Modificador Sem Profecia: Profetizar está desativado'}

        if not self.can_act(username, 'prophet_curse'):
            return {'success': False, 'message': 'Você já usou a habilidade do Profeta neste turno'}
        
        player = self.player_data.get(username)
        if not player:
            return {'success': False, 'message': 'Jogador não encontrado'}
        
        # Verificar se tem Profeta em campo
        has_prophet = False
        prophet_card = None
        prophet_location = None
        
        for base_type in ['attack_bases', 'defense_bases']:
            for i, card in enumerate(player[base_type]):
                if card and card.get('id') == 'profeta':
                    has_prophet = True
                    prophet_card = card
                    prophet_location = (base_type, i)
                    break
                if has_prophet:
                    break
        
        if not has_prophet:
            return {'success': False, 'message': 'Você precisa ter um Profeta em campo'}
        
        # Verificar quantos usos o Profeta já teve
        uses = prophet_card.get('prophet_uses', 0)
        if uses >= 2:
            return {'success': False, 'message': 'Este Profeta já usou sua habilidade 2 vezes e está esgotado'}
        
        # Encontrar a carta alvo
        target_player = self.player_data.get(target_player_id)
        if not target_player or target_player.get('dead', False):
            return {'success': False, 'message': 'Jogador alvo inválido'}
        
        target_card = None
        target_location = None
        
        for base_type in ['attack_bases', 'defense_bases']:
            for i, card in enumerate(target_player[base_type]):
                if card and card['instance_id'] == target_card_id:
                    target_card = card
                    target_location = (base_type, i)
                    break
            if target_card:
                break
        
        if not target_card:
            return {'success': False, 'message': 'Carta alvo não encontrada em campo'}
        
        # Adicionar efeito de maldição na carta
        if 'effects' not in target_card:
            target_card['effects'] = []
        
        # Verificar se já tem maldição
        for effect in target_card['effects']:
            if effect.get('type') == 'prophet_curse':
                return {'success': False, 'message': 'Esta carta já está amaldiçoada'}
        
        # Adicionar maldição
        curse_effect = {
            'type': 'prophet_curse',
            'caster': username,
            'turns_remaining': 2,
            'applied_at_turn': self.current_turn,
            'applied_at_cycle': self.time_cycle
        }
        target_card['effects'].append(curse_effect)
        
        # Adicionar efeito no jogador para rastrear
        target_player.setdefault('active_effects', []).append({
            'type': 'prophet_curse_target',
            'target_card_id': target_card_id,
            'target_card_name': target_card['name'],
            'caster': username,
            'turns_remaining': 2
        })
        
        # Incrementar o contador de usos do Profeta
        prophet_card['prophet_uses'] = uses + 1
        uses_left = 2 - (uses + 1)
        
        self.use_action(username, 'prophet_curse')
        
        uses_message = f" (usos restantes deste Profeta: {uses_left})" if uses_left > 0 else " (este Profeta está esgotado!)"
        
        broadcast_system_message(
            self.game_id,
            f'🔮 {username} amaldiçoou {target_card["name"]} de {target_player["name"]} (morre em 2 rodadas){uses_message}',
            fog_message=f'🔮 {username} amaldiçoou uma criatura de {target_player["name"]} (morre em 2 rodadas)',
        )
        
        return {
            'success': True,
            'message': f'🔮 Maldição do Profeta aplicada! {target_card["name"]} será destruído em 2 rodadas. Usos restantes do Profeta: {uses_left}',
            'target_card': target_card['name'],
            'target_player': target_player['name'],
            'uses_remaining': uses_left
        }
    def process_prophet_curses(self):
        cards_to_destroy = []
        
        for username, player in self.player_data.items():
            if player.get('dead', False):
                continue
            
            # Processar maldições em cartas
            for base_type in ['attack_bases', 'defense_bases']:
                for i, card in enumerate(player[base_type]):
                    if card and 'effects' in card:
                        for effect in card['effects'][:]:  # Copiar para poder remover
                            if effect.get('type') == 'prophet_curse':
                                effect['turns_remaining'] -= 1
                                
                                if effect['turns_remaining'] <= 0:
                                    cards_to_destroy.append({
                                        'player': username,
                                        'base_type': base_type,
                                        'index': i,
                                        'card': card,
                                        'caster': effect['caster']
                                    })
                                    card['effects'].remove(effect)
        
        # Destruir as cartas
        destroyed_info = []
        for item in cards_to_destroy:
            player = self.player_data[item['player']]
            player[item['base_type']][item['index']] = None
            self.graveyard.append(item['card'])
            destroyed_info.append({
                'player': item['player'],
                'card_name': item['card']['name'],
                'caster': item['caster']
            })
        
        return destroyed_info

    # Métodos para armadilhas
    def activate_trap(self, trap_card, attacker, defender, attack_power):
        trap_id = trap_card.get('original_trap_id') or trap_card.get('id')
        trap_name = trap_card.get('original_trap_name') or trap_card.get('name')
        
        effects = []
        
        # Armadilha 171 - Rouba a carta que dá golpe crítico
        if trap_id == 'armadilha_171':
            # Rouba a carta de maior ataque, mantendo o slot da base livre
            # (pop reduziria o tamanho da lista e deixaria o atacante com
            #  um slot de ataque a menos para o resto da partida).
            index = max(
                (i for i, card in enumerate(attacker['attack_bases']) if card),
                key=lambda i: int(attacker['attack_bases'][i].get('attack') or 0),
                default=-1,
            )

            if index >= 0:
                stolen_card = attacker['attack_bases'][index]
                attacker['attack_bases'][index] = None
                defender['hand'].append(stolen_card)

                broadcast_system_message(
                    self.game_id,
                    f'🔮 Armadilha 171 ativada! {defender["name"]} roubou {stolen_card["name"]} de {attacker["name"]}!',
                    fog_message=f'🔮 Armadilha 171 ativada! {defender["name"]} roubou uma criatura de {attacker["name"]}!',
                )
                effects.append({
                    'type': 'steal_card',
                    'stolen_card': stolen_card['name'],
                    'message': f'🔮 Armadilha 171! {defender["name"]} roubou {stolen_card["name"]} de {attacker["name"]}!',
                    'message_fog': f'🔮 Armadilha 171! {defender["name"]} roubou uma criatura de {attacker["name"]}!',
                })
            
            # Retornar efeito com consumo da armadilha
            return {
                'type': 'trap_consumed',
                'effects': effects,
                'consume_trap': True
            }
        
        # Armadilha Espelho - Reverte ataques
        elif trap_id == 'armadilha_espelho':
            broadcast_system_message(
                self.game_id,
                f'🪞 Armadilha Espelho ativada! O ataque de {attack_power} foi refletido para {attacker["name"]}!',
                fog_message=f'🪞 Armadilha Espelho ativada! O ataque de {attacker["name"]} foi refletido!',
            )
            return {
                'type': 'mirror_damage',
                'cancel_attack': True,
                'damage_to_reflect': attack_power,
                'message': f'🪞 Armadilha Espelho! {attack_power} de dano refletido para {attacker["name"]}!',
                'message_fog': f'🪞 Armadilha Espelho! O ataque de {attacker["name"]} foi refletido!',
                'consume_trap': True
            }
        
        # Armadilha Cheat - Dobra ataque e passa para próximo
        elif trap_id == 'armadilha_cheat':
            is_night = (self.time_of_day == 'night')
            has_mage = False
            
            for card in attacker['attack_bases'] + attacker['defense_bases']:
                if card and card.get('type') == 'creature' and card.get('id') in ['mago', 'rei_mago', 'mago_negro']:
                    has_mage = True
                    break
            
            if is_night and has_mage:
                broadcast_system_message(self.game_id, '⚡ Armadilha Cheat ativada! O dano será transferido para o próximo jogador!')
                return {
                    'type': 'cheat_pass_damage',
                    'cancel_attack': True,
                    'pass_to_next': True,
                    'message': f'⚡ Armadilha Cheat! {attacker["name"]} passou o dano para o próximo jogador!',
                    'consume_trap': True
                }
            else:
                effects.append({
                    'type': 'failed',
                    'message': '⚠️ Armadilha Cheat falhou! Precisa ser noite e ter um mago em campo.'
                })
                return {
                    'type': 'trap_failed',
                    'effects': effects,
                    'consume_trap': True  # Mesmo falhando, a armadilha é consumida
                }
                
        # Armadilha Poço Sem Fundo - Destrói todas as 3 criaturas atacantes
        elif trap_id == 'armadilha_poco':
            destroyed_attackers = []
            for i, card in enumerate(attacker['attack_bases']):
                if card and card.get('type') == 'creature':
                    destroyed_attackers.append(card['name'])
                    self.graveyard.append(card)
                    attacker['attack_bases'][i] = None
            
            n = len(destroyed_attackers)
            broadcast_system_message(
                self.game_id,
                f'🕳️ Poço Sem Fundo ativado! As criaturas atacantes {", ".join(destroyed_attackers)} foram destruídas!',
                fog_message=f'🕳️ Poço Sem Fundo ativado! {n} criatura(s) atacante(s) de {attacker["name"]} foram destruídas!',
            )
            
            return {
                'type': 'destroy_attackers',
                'cancel_attack': True,
                'destroyed': destroyed_attackers,
                'message': f'🕳️ Poço Sem Fundo! As criaturas atacantes foram destruídas: {", ".join(destroyed_attackers)}',
                'message_fog': f'🕳️ Poço Sem Fundo! {n} criatura(s) atacante(s) foram destruídas!',
                'consume_trap': True
            }
        
        return None

