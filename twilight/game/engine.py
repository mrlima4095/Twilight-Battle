"""Motor da partida multiplayer (classe Game)."""
import random
from random import shuffle
import uuid

from flask_socketio import emit

from twilight.cards.deck import create_deck, get_random_disguise
from twilight.cards.definitions import CARDS
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
        self.winner = None
        self.current_turn = 0  # Índice na lista players
        self.time_of_day = "day"
        self.time_cycle = 0
        self.max_players = 6
        self.turn_actions_used = {}
        self.turn_extra_actions = {}
        self.last_spell_id = None  # para Eco do Grimório
        # Ciclo dia/noite: 24 normal, 6 com fast_cycle
        self.day_cycle_length = 6 if 'fast_cycle' in self.modifiers else 24

        self.first_round = True
        self.players_acted = set()
        self.attacks_blocked = True
        if 'no_first_round' in self.modifiers:
            self.first_round = False
            self.attacks_blocked = False

        # Tamanhos de board
        self.attack_slot_count = 5 if 'war_front' in self.modifiers else 3
        self.defense_slot_count = 1 if 'open_field' in self.modifiers else 6
        # Vida inicial
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
    
    def add_player(self, socket_id, username):
        """Adiciona um jogador ao jogo usando username como identificador"""
        if len(self.players) >= self.max_players or self.started:
            return False
        
        # Verificar se username já está no jogo
        if username in self.players:
            return False
        
        self.players.append(username)
        self.socket_to_username[socket_id] = username
        
        # Mão inicial (modificadores: empty_hand / big_hand)
        hand = []
        for _ in range(getattr(self, 'starting_hand_size', 5)):
            if self.deck:
                hand.append(self.deck.pop())
        
        atk_n = getattr(self, 'attack_slot_count', 3)
        def_n = getattr(self, 'defense_slot_count', 6)
        start_life = getattr(self, 'starting_life', 1200)

        self.player_data[username] = {
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
            'runes': 0,
            'active_effects': [],
            'profecia_alvo': None,
            'profecia_rodadas': 0,
            'dead': False,
            'observer': False,
            'free_swap_used': False,
            'first_hit_reduced': False,
            'attacked_this_turn': False,
        }
        
        return True
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

        def get_player_runes_count(self, username):
            player = self.player_data.get(username)
            if not player:
                return 0
            
            runes_count = 0
            for card in player.get('hand', []):
                if card and (card.get('type') == 'rune' or card.get('id') == 'runa'):
                    runes_count += 1
            return runes_count

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

    def next_turn(self):
        """Avança para o próximo turno, pulando jogadores mortos"""
        if not self.players:
            return

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
        
        if self.time_of_day == "day":
            self.apply_day_effects()
        if 'disable_daycicle' not in self.modifiers:
            self.time_cycle += 1
            cycle_len = getattr(self, 'day_cycle_length', 24) or 24
            if self.time_cycle % cycle_len == 0:
                self.time_of_day = "night" if self.time_of_day == "day" else "day"
                if self.time_of_day == "day":
                    self.apply_day_effects()
                else:
                    self.apply_werewolf_forms()

        
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
        
        # Remover carta da mão
        player['hand'].pop(card_index)
        
        # Colocar carta no local apropriado
        if position_type == 'attack':
            if position_index >= len(player['attack_bases']):
                return {'success': False, 'message': 'Posição de ataque inválida'}
            if player['attack_bases'][position_index] is not None:
                return {'success': False, 'message': 'Posição de ataque ocupada'}
            player['attack_bases'][position_index] = card_to_play
        
        elif position_type == 'defense':
            if position_index >= len(player['defense_bases']):
                return {'success': False, 'message': 'Posição de defesa inválida'}
            if player['defense_bases'][position_index] is not None:
                return {'success': False, 'message': 'Posição de defesa ocupada'}
            player['defense_bases'][position_index] = card_to_play
        
        elif position_type == 'equipment':
            player['equipment'][position_index] = card_to_play
        
        # Lobisomem: aplicar forma atual ao entrar em campo
        if card_to_play.get('type') == 'creature' and card_to_play.get('werewolf'):
            card_to_play['werewolf_form'] = None
            self.apply_werewolf_forms()
        
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
            if card and card.get('type') == 'creature':
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
        
        # Adicionar bônus de equipamentos
        if attacker['equipment']['weapon']:
            weapon = attacker['equipment']['weapon']
            if weapon.get('type') == 'weapon':
                weapon_attack = weapon.get('attack', 0)
                attack_power += weapon_attack
        
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
            'trap_effects': trap_effects
        }

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
        for def_card in defense_cards:
            if remaining_damage <= 0:
                break
            
            card = def_card['card']
            card_life = def_card['current_life']
            reflected_text = " [dano refletido]" if is_reflected else ""
            
            if remaining_damage >= card_life:
                remaining_damage -= card_life
                self.graveyard.append(card)
                target['defense_bases'][def_card['index']] = None
                cards_destroyed.append(card['name'])
                damage_log.append(f"{card['name']} (defesa) foi destruída{reflected_text}")
            else:
                new_life = card_life - remaining_damage
                card['life'] = new_life
                cards_damaged.append(f"{card['name']} (defesa) (-{remaining_damage}❤️)")
                damage_log.append(f"{card['name']} (defesa) recebeu {remaining_damage} de dano (vida restante: {new_life}){reflected_text}")
                remaining_damage = 0
        
        # ORDEM 2: Absorver dano pelas cartas de ATAQUE (índice 0 → 2)
        for atk_card in attack_cards:
            if remaining_damage <= 0:
                break
            
            card = atk_card['card']
            card_life = atk_card['current_life']
            reflected_text = " [dano refletido]" if is_reflected else ""
            
            if remaining_damage >= card_life:
                remaining_damage -= card_life
                self.graveyard.append(card)
                target['attack_bases'][atk_card['index']] = None
                cards_destroyed.append(card['name'])
                damage_log.append(f"{card['name']} (ataque) foi destruída{reflected_text}")
            else:
                new_life = card_life - remaining_damage
                card['life'] = new_life
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
                        damage_log.append(f"⚠️ Oráculo não pode ser usado: requer um Elfo em modo de defesa")
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
                        damage_log.append(f"🔄 Talismã da Imortalidade se esgotou e voltou para o deck!")
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
            'cards_destroyed': cards_destroyed,
            'cards_damaged': cards_damaged,
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
            self.winner = alive_players[0]
            return self.winner
        if len(alive_players) == 0 and self.players:
            # empate técnico — ninguém vivo
            self.finished = True
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
                    gear_atk = sum((eq.get('attack') or 0) for eq in (card.get('equipped_items') or []))
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

    def apply_day_effects(self):
        for username in self.players:
            player = self.player_data[username]
            
            # Processar cartas em defesa
            for i, card in enumerate(player['defense_bases']):
                if card:
                    # Verificar se morre durante o dia (zumbis, vampiros)
                    if card.get('dies_daylight'):
                        if not self.has_daylight_protection(player, card):
                            self.graveyard.append(card)
                            player['defense_bases'][i] = None
                            broadcast_system_message(self.game_id, f'☀️ {card["name"]} de {username} morreu com a luz do dia!')
                    
                    # Criaturas noturnas tomam 10 de dano
                    elif card.get('night_creature', False):
                        if self.has_daylight_protection(player, card):
                            continue
                        card_life = card.get('life', 0)
                        if card_life > 0:
                            new_life = max(0, card_life - 10)
                            card['life'] = new_life
                            
                            if new_life <= 0:
                                self.graveyard.append(card)
                                player['defense_bases'][i] = None
                                broadcast_system_message(self.game_id, f'☀️ {card["name"]} de {username} foi destruído pelo sol! (-10❤️)')
            
            # Processar cartas em ataque
            for i, card in enumerate(player['attack_bases']):
                if card:
                    # Verificar se morre durante o dia (zumbis, vampiros)
                    if card.get('dies_daylight'):
                        if not self.has_daylight_protection(player, card):
                            self.graveyard.append(card)
                            player['attack_bases'][i] = None
                            broadcast_system_message(self.game_id, f'☀️ {card["name"]} de {username} morreu com a luz do dia!')
                    
                    # Criaturas noturnas tomam 10 de dano
                    elif card.get('night_creature', False):
                        if self.has_daylight_protection(player, card):
                            continue
                        card_life = card.get('life', 0)
                        if card_life > 0:
                            new_life = max(0, card_life - 10)
                            card['life'] = new_life
                            
                            if new_life <= 0:
                                self.graveyard.append(card)
                                player['attack_bases'][i] = None
                                broadcast_system_message(self.game_id, f'☀️ {card["name"]} de {username} foi destruído pelo sol! (-10❤️)')
        # lobisomem troca forma no ciclo (também à noite via toggle)
        self.apply_werewolf_forms()

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
        
        if 'equipped_items' not in target_creature:
            target_creature['equipped_items'] = []
        
        weapon_count = sum(1 for eq in target_creature['equipped_items'] if eq.get('type') == 'weapon' or eq.get('id') in ['lamina_almas', 'blade_vampires', 'blade_dragons'])
        armor_count = sum(1 for eq in target_creature['equipped_items'] if eq.get('type') == 'armor' or eq.get('id') == 'capacete_trevas')
        
        if (item_card.get('type') == 'weapon' or item_card.get('id') in ['lamina_almas', 'blade_vampires', 'blade_dragons']) and weapon_count >= 1:
            return {'success': False, 'message': 'Criatura já tem uma arma equipada'}
        
        if (item_card.get('type') == 'armor' or item_card.get('id') == 'capacete_trevas') and armor_count >= 4:
            return {'success': False, 'message': 'Criatura já tem muitas armaduras'}
        
        # Remover item da mão
        player['hand'].pop(item_index)
        
        # Equipar item
        target_creature['equipped_items'].append(item_card)
        
        if item_card.get('attack'):
            target_creature['attack'] = target_creature.get('attack', 0) + item_card['attack']
        if item_card.get('attack_bonus') and item_card.get('ability') == 'charge_bonus':
            # Botas de Guerra: bônus só em ataque
            if creature_location and creature_location[0] == 'attack_bases':
                target_creature['attack'] = target_creature.get('attack', 0) + item_card.get('attack_bonus', 0)
        if item_card.get('protection'):
            target_creature['life'] = target_creature.get('life', 0) + item_card['protection']
        if item_card.get('life'):
            target_creature['life'] = target_creature.get('life', 0) + item_card['life']

        # Peitoral de Carvalho: ward em elfo/ninfa
        if item_card.get('ability') == 'nature_ward':
            cid = target_creature.get('id') or ''
            if cid in (item_card.get('spell_resist_races') or []) or 'elfo' in cid or 'ninfa' in cid:
                target_creature['spell_resist_charges'] = target_creature.get('spell_resist_charges', 0) + 1
                broadcast_system_message(
                    self.game_id,
                    f'🌳 Peitoral de Carvalho: {target_creature["name"]} resiste ao próximo feitiço hostil!'
                )
        
        broadcast_system_message(self.game_id, f'🔧 {username} equipou {item_card["name"]} em {target_creature["name"]}')

        return {
            'success': True,
            'creature': target_creature['name'],
            'item': item_card['name'],
            'message': f"{item_card['name']} equipado em {target_creature['name']}"
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
        
        if not has_mago_negro:
            ritual_card = None
            ritual_index = -1
            for i, card in enumerate(player['hand']):
                if card['id'] == ritual_id:
                    ritual_card = card
                    ritual_index = i
                    break
            
            if not ritual_card:
                return {'success': False, 'message': 'Você não tem esta carta de ritual'}
            
            player['hand'].pop(ritual_index)
        
        if ritual_id == 'ritual_157':
            if not target_username:
                return {'success': False, 'message': 'Selecione um alvo para o Ritual 157'}
            
            can_cast, message = RitualManager.check_ritual_157(self, username)
            if not can_cast:
                return {'success': False, 'message': message}
            
            result = RitualManager.execute_ritual_157(self, username, target_username)
            
        elif ritual_id == 'ritual_amor':
            if not target_username:
                return {'success': False, 'message': 'Selecione o alvo da profecia'}
            
            can_cast, message = RitualManager.check_ritual_amor(self, username)
            if not can_cast:
                return {'success': False, 'message': message}
            
            target = self.player_data[target_username]
            has_profecia = False
            if target.get('profecia_alvo') or any(effect.get('type') == 'profecia_morte' for effect in target['active_effects']):
                has_profecia = True
            
            if not has_profecia:
                return {'success': False, 'message': 'O alvo não possui nenhuma profecia ativa'}
            
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

        broadcast_system_message(self.game_id, f'✨ {username} usou {spell_card["name"]} {f"em {target_username}" if target_username else ""}')
        
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
            # Aumenta ataque de um monstro
            if target_card_id:
                found = self._find_card_on_field(target_card_id)
                if found:
                    uname, base, idx, card = found
                    if self._try_spell_resist(card):
                        return {'type': 'resisted', 'target': card['name'], 'message': f'{card["name"]} resistiu ao feitiço!'}
                    card['attack'] = card.get('attack', 0) + 1024
                    return {'type': 'buff', 'target': card['name'], 'effect': '+1024 ataque'}
            return {'type': 'error', 'message': 'Alvo não encontrado'}
        
        elif spell_id == 'feitico_duro_matar':
            # Aumenta defesa do jogador
            if target_username:
                self.player_data[target_username]['life'] += 1024
                return {'type': 'buff', 'target': self.player_data[target_username]['name'], 'effect': '+1024 vida'}
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
            for player_uname in self.players:
                player = self.player_data[player_uname]
                for card in player['hand']:
                    self.deck.append(card)
                player['hand'] = []
            random.shuffle(self.deck)
            return {'type': 'reset_hands'}
        
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
            # Cura o jogador alvo
            heal_amount = 1024
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
                    broadcast_system_message(self.game_id, f'☀️ Julgamento da Aurora destruiu {card["name"]} de {uname}!')
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
                            broadcast_system_message(self.game_id, f'☀️ Julgamento da Aurora destruiu {name} de {target_username}!')
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
        
        broadcast_system_message(self.game_id, f'🔮 {username} amaldiçoou {target_card["name"]} de {target_player["name"]} (morre em 2 rodadas){uses_message}')
        
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
            damage = 0
            index = -1
            for card in attacker['attack_bases']:
                if card and card.get('attack', 0) > damage:
                    damage = card.get('attack', 0)
                    index += 1

            if index >= 0 and index < len(attacker['attack_bases']) and attacker['attack_bases'][index]:
                stolen_card = attacker['attack_bases'].pop(index)
                defender['hand'].append(stolen_card)

                broadcast_system_message(self.game_id, f'🔮 Armadilha 171 ativada! {defender["name"]} roubou {stolen_card["name"]} de {attacker["name"]}!')
                effects.append({
                    'type': 'steal_card',
                    'stolen_card': stolen_card['name'],
                    'message': f'🔮 Armadilha 171! {defender["name"]} roubou {stolen_card["name"]} de {attacker["name"]}!'
                })
            
            # Retornar efeito com consumo da armadilha
            return {
                'type': 'trap_consumed',
                'effects': effects,
                'consume_trap': True
            }
        
        # Armadilha Espelho - Reverte ataques
        elif trap_id == 'armadilha_espelho':
            broadcast_system_message(self.game_id, f'🪞 Armadilha Espelho ativada! O ataque de {attack_power} foi refletido para {attacker["name"]}!')
            return {
                'type': 'mirror_damage',
                'cancel_attack': True,
                'damage_to_reflect': attack_power,
                'message': f'🪞 Armadilha Espelho! {attack_power} de dano refletido para {attacker["name"]}!',
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
                broadcast_system_message(self.game_id, f'⚡ Armadilha Cheat ativada! O dano será transferido para o próximo jogador!')
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
                    'message': f'⚠️ Armadilha Cheat falhou! Precisa ser noite e ter um mago em campo.'
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
            
            broadcast_system_message(self.game_id, f'🕳️ Poço Sem Fundo ativado! As criaturas atacantes {", ".join(destroyed_attackers)} foram destruídas!')
            
            return {
                'type': 'destroy_attackers',
                'cancel_attack': True,
                'destroyed': destroyed_attackers,
                'message': f'🕳️ Poço Sem Fundo! As criaturas atacantes foram destruídas: {", ".join(destroyed_attackers)}',
                'consume_trap': True
            }
        
        return None

