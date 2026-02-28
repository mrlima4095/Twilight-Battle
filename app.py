# app.py
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
import random
import string
import time
from collections import defaultdict
import uuid

app = Flask(__name__)
app.config['SECRET_KEY'] = 'twilight-battle-secret'
socketio = SocketIO(app, cors_allowed_origins="*")

# Estruturas de dados do jogo
games = {}
players = {}
waiting_players = []

# Definição das cartas
CARDS = {
    # Criaturas
    # - Tropas
    "elfo": {
        "id": "elfo",
        "name": "Elfo",
        "type": "creature",
        "life": 512, 
        "attack": 512,
        "count": 40, 
        "description": "Não ataca outros elfos. Use para realizar oraculos."
    },
    "zumbi": {
        "id": "zumbi", 
        "name": "Zumbi",
        "type": "creature",
        "life": 100, 
        "attack": 100,
        "count": 40, 
        "description": "Morre durante o dia. A menos que derrotado por outro zumbi volta para a mão do jogador.", 
        "dies_daylight": True
    },
    "centauro": {
        "id": "centauro",
        "name": "Centauro", 
        "type": "creature", 
        "life": 512, 
        "attack": 150, 
        "count": 40, 
        "description": "O jogador pode colocar personagens para montar no centauro. Realiza qualquer ataque terrestre."
    },
    
    "mago": {
        "id": "mago",
        "name": "Mago",
        "type": "creature", 
        "life": 800, 
        "attack": 250, 
        "count": 40, 
        "description": "Use-o para invocar feitiços."
    },
    
    # -- Especiais
    "vampiro_wers": {
        "id": "vampiro_wers", 
        "name": "Vampiro - Benjamim Wers", 
        "type": "creature", 
        "life": 512, 
        "attack": 250, 
        "count": 1, 
        "description": "Mata todos os centauros em campo dos oponentes e entrega a vida a jogador.", 
        "dies_daylight": True
    },
    "vampiro_tayler": {
        "id": "vampiro_tayler", 
        "name": "Vampiro - Necrothic Tayler", 
        "type": "creature", 
        "life": 512, 
        "attack": 100, 
        "count": 1, 
        "description": "Rouba a vida do oponente para recuperar a vida de seu jogador.", 
        "dies_daylight": True
    },
    
    "ninfa_lorem": {
        "id": "ninfa", 
        "name": "Ninfa - Belly Lorem", 
        "type": "creature", 
        "life": 512, 
        "attack": 128, 
        "count": 1, 
        "description": "Torna o jogador imune a rituais."
    },
    
    # - Mestres
    "rei_mago": {
        "id": "rei_mago", 
        "name": "Rei Mago", 
        "type": "creature", 
        "life": 2000, 
        "attack": 1500, 
        "count": 1, 
        "description": "Pode impedir outros magos de realizar feitiços. Realiza feitiços sem possuir a carta."
    },
    "mago_negro": {
        "id": "mago_negro", 
        "name": "Mago Negro", 
        "type": "creature", 
        "life": 2000, 
        "attack": 1500, 
        "count": 1, 
        "description": "Não se subordina ao Rei Mago. Realiza rituais sem possuir a carta"
    },
    
    "apollo": {
        "id": "apollo", 
        "name": "Apollo", 
        "type": "creature", 
        "life": 8200, 
        "attack": 2000, 
        "count": 1, 
        "description": "Ataques sofridos com menos de 5k de dano recuperam a vida do jogador se colocado na defesa, não pode ficar na defesa por mais de 5 rodadas."
    },
    
    # - Bestas
    "dragao": {
        "id": "dragao", 
        "name": "Dragão", 
        "type": "creature", 
        "life": 5000, 
        "attack": 1500, 
        "count": 10, 
        "description": "Seu ataque incendeia o inimigo, com isso ele toma 50 de danos nas próximas rodadas do fogo."
    },
    "leviatan": {
        "id": "leviatan", 
        "name": "Leviatã", 
        "type": "creature", 
        "life": 15000, 
        "attack": 15000, 
        "count": 1, 
        "description": "Só pode ser domado por deuses e magos supremos."
    },
    "apofis": {
        "id": "apofis", 
        "name": "Apofis", 
        "type": "creature", 
        "life": 32500, 
        "attack": 5000, 
        "count": 1, 
        "description": "Rei do Caos. Pode desativar armadilhas e magias de outros jogadores."
    },
    "fenix": {
        "id": "fenix", 
        "name": "Fênix", 
        "type": "creature", 
        "life": 32500, 
        "attack": 10000, 
        "count": 1, 
        "description": "Grande ave com ataque de fogo, pode mudar de dia para noite e vice-versa quando bem entender."
    },

    "medusa": {
        "id": "medusa", 
        "name": "Medusa", 
        "type": "creature", 
        "life": 1024, 
        "attack": 512, 
        "count": 1, 
        "description": "Seu ataque transforma personagens em pedra. Cartas com maior vida são imunes."
    },
    
    "profeta": {
        "id": "profeta", 
        "name": "Profeta", 
        "type": "creature", 
        "life": 256, 
        "attack": 50, 
        "count": 1, 
        "description": "Anuncia a morte de um monstro para duas rodadas a frente. A maldição pode ser retirada caso o jogador seja derrotado."
    },
    
    "super_centauro": {
        "id": "super_centauro", 
        "name": "Super Centauro", 
        "type": "creature", 
        "life": 600, 
        "attack": 256, 
        "count": 5, 
        "description": "Apenas ataques diretos. Pode encantar centauros de outros jogadores e pegar eles para a sua mão (os centauros que estão em campo)"
    },
    
    # Itens/Espadas
    "lamina_almas": {
        "id": "lamina_almas", 
        "name": "Lâmina das Almas", 
        "type": "weapon", 
        "attack": 0, 
        "count": 1, 
        "description": "Assume o dano de uma carta do cemitério. Só pode ser equipado por Elfos, magos e vampiros."
    },
    
    "blade_vampires": {
        "id": "blade_vampires", 
        "name": "Blade of Vampires", 
        "type": "weapon", 
        "attack": 5000, 
        "count": 1, 
        "description": "Só pode ser usada por um vampiro. Seu ataque torna o oponente noturno (morre de dia)"
    },
    "blade_dragons": {
        "id": "blade_dragons", 
        "name": "Blade of Dragons", 
        "type": "weapon", 
        "attack": 5000, 
        "count": 1, 
        "description": "Usada apenas por elfos ou vampiros. Seu ataque pode eliminar personagens permanentemente tornando impossíveis de reviver ou ser invocados de volta do cemitério."
    },
    
    # Armaduras/Equipamentos
    "capacete_trevas": {
        "id": "capacete_trevas", 
        "name": "Capacete das Trevas", 
        "type": "armor", 
        "protection": 800, 
        "count": 20, 
        "description": "Impede o dano da luz do dia em mortos-vivos e a proteção é adicionada a carta."
    },
    
    # Talismãs (não podem ser jogados, apenas segurados)
    "talisma_ordem": {
        "id": "talisma_ordem", 
        "name": "Talismã - Ordem", 
        "type": "talisman", 
        "count": 1, 
        "description": "Imunidade ao Caos."
    },
    "talisma_imortalidade": {
        "id": "talisma_imortalidade", 
        "name": "Talismã - Imortalidade", 
        "type": "talisman", 
        "count": 1, 
        "description": "Se o jogador for morto com este item em mãos ele terá seus pontos de vida restaurados."
    },
    "talisma_verdade": {
        "id": "talisma_verdade", 
        "name": "Talismã - Verdade", 
        "type": "talisman", 
        "count": 1, 
        "description": "Imunidade a feitiços e oráculos."
    },
    "talisma_guerreiro": {
        "id": "talisma_guerreiro", 
        "name": "Talismã - Guerreiro", 
        "type": "talisman", 
        "count": 1, 
        "description": "Aumenta em 1024 pontos o ataque e defesa do jogador."
    },
    
    # Runas
    "runa": {
        "id": "runa", 
        "name": "Runa", 
        "type": "rune",
        "count": 40, 
        "description": "Colete quatro runas para realizar uma invocação de um personagem do cemitério."
    },
    
    # Feitiços
    "feitico_cortes": {
        "id": "feitico_cortes", 
        "name": "Feitiço - Cortes", 
        "type": "spell", 
        "count": 1, 
        "description": "Aumenta ataque de um monstro em 1024 pontos por duas rodadas."
    },
    "feitico_duro_matar": {
        "id": "feitico_duro_matar", 
        "name": "Feitiço - Duro de matar", 
        "type": "spell", 
        "count": 1, 
        "description": "Aumenta defesa do jogador em 1024 pontos por duas rodadas."
    },
    "feitico_troca": {
        "id": "feitico_troca", 
        "name": "Feitiço - Troca", 
        "type": "spell", 
        "count": 1, 
        "description": "Troca as cartas de outro Jogador de ataque para defesa e vice-versa."
    },
    "feitico_comunista": {
        "id": "feitico_comunista", 
        "name": "Feitiço - Comunista", 
        "type": "spell", 
        "count": 1, 
        "description": "Faz as cartas das mãos dos jogadores irem de volta para a pilha."
    },
    "feitico_silencio": {
        "id": "feitico_silencio", 
        "name": "Feitiço - Silêncio", 
        "type": "spell", 
        "count": 1, 
        "description": "Os ataques das próximas duas rodadas não ativam armadilhas."
    },
    "feitico_para_sempre": {
        "id": "feitico_para_sempre", 
        "name": "Feitiço - Para Sempre", 
        "type": "spell", 
        "count": 1, 
        "description": "Reverte o efeito da espada Blade of Vampires."
    },
    "feitico_capitalista": {
        "id": "feitico_capitalista", 
        "name": "Feitiço - Capitalista", 
        "type": "spell", 
        "count": 1, 
        "description": "Troque cartas com outros jogadores."
    },
    
    # Oraculo
    "oraculo": {
        "id": "oraculo", 
        "name": "Oráculo", 
        "type": "oracle", 
        "count": 1, 
        "description": "Mate o oponente com o talismã da imortalidade três vezes para que ele seja derrotado permanentemente, seja rápido antes que ele junte todos os talismãs."
    },
    
    # Rituais (requerem condições específicas)
    "ritual_157": {
        "id": "ritual_157", 
        "name": "Ritual 157", 
        "type": "ritual", 
        "count": 1, 
        "description": "Requer Apofis, Mago Negro, 6 zumbis e 2 elfos em modo de defesa. Todos os talismãs da mão do jogador escolhido são roubados."
    },
    "ritual_amor": {
        "id": "ritual_amor", 
        "name": "Ritual Amor", 
        "type": "ritual", 
        "count": 1, 
        "description": "Requer a Ninfa Belly Lorem e o Vampiro Necrothic Tayler. Anula a maldição do Profeta."
    },
    
    # Armadilhas
    "armadilha_51": {
        "id": "armadilha_51", 
        "name": "Armadilha 51", 
        "type": "trap", 
        "count": 1, 
        "description": "Faz o exército do outro jogador ficar bêbado e atacar aliados."
    },
    "armadilha_171": {
        "id": "armadilha_171", 
        "name": "Armadilha 171", 
        "type": "trap", 
        "count": 1, 
        "description": "Rouba a carta que te dá um golpe crítico."
    },
    "armadilha_espelho": {
        "id": "armadilha_espelho", 
        "name": "Armadilha Espelho", 
        "type": "trap", 
        "count": 1, 
        "description": "Reverte ataques e magia."
    },    
    "armadilha_cheat": {
        "id": "armadilha_cheat", 
        "name": "Armadilha Cheat", 
        "type": "trap", 
        "count": 1, 
        "description": "Dobrar o ataque e passar para o próximo jogador na rodada, precisa estar de noite e um mago em campo."
    }
}

def create_deck():
    """Cria o baralho inicial baseado na quantidade de cartas"""
    deck = []
    for card_id, card_info in CARDS.items():
        for _ in range(card_info['count']):
            new_card = card_info.copy()
            new_card['instance_id'] = str(uuid.uuid4())[:8]
            deck.append(new_card)
    random.shuffle(deck)
    return deck

# Classe para gerenciar rituais
class RitualManager:
    @staticmethod
    def check_ritual_157(game, caster_id):
        """Verifica condições do Ritual 157 - Requer Apofis, Mago Negro, 6 zumbis e 2 elfos em modo de defesa"""
        player = game.player_data[caster_id]
        
        # Verificar se tem Apofis em campo (ataque ou defesa)
        has_apofis = False
        for card in player['attack_bases'] + player['defense_bases']:
            if card and card['id'] == 'apofis':
                has_apofis = True
                break
        
        if not has_apofis:
            return False, "Requer Apofis em campo"
        
        # Verificar se tem Mago Negro em campo
        has_mago_negro = False
        for card in player['attack_bases'] + player['defense_bases']:
            if card and card['id'] == 'mago_negro':
                has_mago_negro = True
                break
        
        if not has_mago_negro:
            return False, "Requer Mago Negro em campo"
        
        # Contar zumbis em campo (qualquer posição)
        zumbis_count = 0
        for card in player['attack_bases'] + player['defense_bases']:
            if card and card['id'] == 'zumbi':
                zumbis_count += 1
        
        if zumbis_count < 6:
            return False, f"Requer 6 zumbis em campo (tem {zumbis_count})"
        
        # Contar elfos em MODO DE DEFESA
        elfos_defesa = 0
        for card in player['defense_bases']:
            if card and card['id'] == 'elfo':
                elfos_defesa += 1
        
        if elfos_defesa < 2:
            return False, f"Requer 2 elfos em modo de defesa (tem {elfos_defesa})"
        
        return True, "Ritual 157 pode ser realizado"
    @staticmethod
    def execute_ritual_157(game, caster_id, target_player_id):
        """Executa o Ritual 157 - Rouba todos os talismãs do alvo"""
        caster = game.player_data[caster_id]
        target = game.player_data[target_player_id]
        
        # Coletar todos os talismãs do alvo
        stolen_talismans = []
        for talisman in target['talismans']:
            stolen_talismans.append(talisman)
        
        # Remover talismãs do alvo
        target['talismans'] = []
        
        # Adicionar talismãs ao conjurador
        caster['talismans'].extend(stolen_talismans)
        
        return {
            'success': True,
            'message': f"Ritual 157 realizado! {len(stolen_talismans)} talismãs roubados de {target['name']}",
            'stolen_count': len(stolen_talismans)
        }
    
    @staticmethod
    def check_ritual_amor(game, caster_id):
        """Verifica condições do Ritual Amor - Requer Ninfa Belly Lorem e Vampiro Necrothic Tayler"""
        player = game.player_data[caster_id]
        
        # Verificar se tem Ninfa Lorem em campo
        has_ninfa = False
        for card in player['attack_bases'] + player['defense_bases']:
            if card and card['id'] == 'ninfa':
                has_ninfa = True
                break
        
        if not has_ninfa:
            return False, "Requer Ninfa Belly Lorem em campo"
        
        # Verificar se tem Vampiro Necrothic Tayler em campo
        has_vampiro = False
        for card in player['attack_bases'] + player['defense_bases']:
            if card and card['id'] == 'vampiro_tayler':
                has_vampiro = True
                break
        
        if not has_vampiro:
            return False, "Requer Vampiro Necrothic Tayler em campo"
        
        return True, "Ritual Amor pode ser realizado"
    @staticmethod
    def execute_ritual_amor(game, caster_id, target_player_id):
        """Executa o Ritual Amor - Anula a maldição do Profeta"""
        target = game.player_data[target_player_id]
        
        # Remover profecia do alvo se existir
        if target.get('profecia_alvo'):
            target['profecia_alvo'] = None
            target['profecia_rodadas'] = 0
        
        # Remover efeitos de maldição
        target['active_effects'] = [effect for effect in target['active_effects'] 
                                   if effect.get('type') != 'profecia_morte']
        
        return {
            'success': True,
            'message': f"Ritual Amor realizado! Maldição anulada para {target['name']}"
        }
    
    @staticmethod
    def get_available_rituals(game, player_id):
        """Retorna lista de rituais disponíveis baseado nas condições"""
        player = game.player_data[player_id]
        available_rituals = []
        
        # Verificar se tem carta do ritual na mão (para magos comuns)
        rituals_in_hand = [card for card in player['hand'] if card.get('type') == 'ritual']
        
        # Verificar se tem Mago Negro em campo (pode realizar qualquer ritual)
        has_mago_negro = False
        for card in player['attack_bases'] + player['defense_bases']:
            if card and card['id'] == 'mago_negro':
                has_mago_negro = True
                break
        
        # Lista de rituais disponíveis
        ritual_list = [
            {'id': 'ritual_157', 'name': 'Ritual 157', 'description': 'Rouba todos os talismãs de um jogador'},
            {'id': 'ritual_amor', 'name': 'Ritual Amor', 'description': 'Anula a maldição do Profeta'}
        ]
        
        for ritual in ritual_list:
            # Verificar se pode realizar (tem a carta ou é Mago Negro)
            has_card = any(card['id'] == ritual['id'] for card in rituals_in_hand)
            
            if has_card or has_mago_negro:
                # Verificar condições específicas
                if ritual['id'] == 'ritual_157':
                    can_cast, message = RitualManager.check_ritual_157(game, player_id)
                    if can_cast:
                        ritual['conditions_met'] = True
                        ritual['message'] = '✅ Condições atendidas'
                    else:
                        ritual['conditions_met'] = False
                        ritual['message'] = f'❌ {message}'
                
                elif ritual['id'] == 'ritual_amor':
                    can_cast, message = RitualManager.check_ritual_amor(game, player_id)
                    if can_cast:
                        ritual['conditions_met'] = True
                        ritual['message'] = '✅ Condições atendidas'
                    else:
                        ritual['conditions_met'] = False
                        ritual['message'] = f'❌ {message}'
                
                available_rituals.append(ritual)
        
        return available_rituals
class Game:
    def __init__(self, game_id):
        self.game_id = game_id
        self.players = []
        self.player_data = {}
        self.deck = create_deck()
        self.graveyard = []
        self.started = False
        self.current_turn = 0
        self.time_of_day = "day"  # day or night
        self.time_cycle = 0
        self.max_players = 6
        self.turn_actions_used = {}  # Track actions used per player per turn
        
        self.first_round = True
        self.players_acted = set()  # Jogadores que já fizeram uma ação
        self.attacks_blocked = True  # Ataques bloqueados na primeira rodada
        
    def add_player(self, player_id, player_name):
        if len(self.players) >= self.max_players or self.started:
            return False
        
        self.players.append(player_id)
        # Draw 5 initial cards
        hand = []
        for _ in range(5):
            if self.deck:
                hand.append(self.deck.pop())
        
        self.player_data[player_id] = {
            'name': player_name,
            'life': 5000,
            'hand': hand,
            'attack_bases': [None, None, None],  # 3 attack bases
            'defense_bases': [None, None, None, None, None, None],  # 6 defense bases
            'equipment': {
                'weapon': None,
                'helmet': None,
                'armor': None,
                'boots': None,
                'mount': None
            },
            'talismans': [],
            'runes': 0,
            'active_effects': [],
            'profecia_alvo': None,
            'profecia_rodadas': 0,
            'dead': False,
            'observer': False
        }
        return True
    
    def can_attack(self, player_id):
        """Verifica se o jogador pode atacar (bloqueado na primeira rodada)"""
        if self.attacks_blocked:
            return False, "Ataques bloqueados na primeira rodada. Todos precisam jogar primeiro."
        return True, ""
    def register_action(self, player_id, action_type):
        """Registra que um jogador realizou uma ação"""
        if self.first_round and action_type not in ['attack', 'end_turn']:
            self.players_acted.add(player_id)
            print(f"Jogador {player_id} realizou ação. Jogadores que já agiram: {len(self.players_acted)}/{len(self.players)}")
            
            # Verificar se todos já agiram
            if len(self.players_acted) >= len(self.players):
                self.first_round = False
                self.attacks_blocked = False
                print("🎉 PRIMEIRA RODADA CONCLUÍDA! Ataques liberados!")
                
                # Notificar todos os jogadores
                return True  # Indica que a primeira rodada terminou
        
        return False

    def next_turn(self):
        """Avança para o próximo turno, pulando jogadores mortos"""
        if not self.players:
            return
        
        # Encontrar próximo jogador vivo
        original_turn = self.current_turn
        next_turn = (self.current_turn + 1) % len(self.players)
        
        # Continuar avançando enquanto o jogador estiver morto
        while self.player_data[self.players[next_turn]].get('dead', False):
            print(f"Pulando jogador morto: {self.player_data[self.players[next_turn]]['name']}")
            next_turn = (next_turn + 1) % len(self.players)
            
            # Se voltou ao original, todos estão mortos (fim de jogo)
            if next_turn == original_turn:
                # Todos os jogadores restantes estão mortos
                print("Todos os jogadores restantes estão mortos")
                break
        
        self.current_turn = next_turn
        self.turn_actions_used = {}
        
        # Inicializar controle de ações para o novo turno
        for player_id in self.players:
            if not self.player_data[player_id].get('dead', False):
                self.turn_actions_used[player_id] = set()
        
        # Mudar dia/noite a cada 24 turnos
        self.time_cycle += 1
        if self.time_cycle % 24 == 0:
            self.time_of_day = "night" if self.time_of_day == "day" else "day"
            if self.time_of_day == "day":
                self.apply_day_effects()
        
        print(f"Próximo turno: {self.player_data[self.players[self.current_turn]]['name']}")

    def apply_day_effects(self):
        """Aplica efeitos do dia (zumbis e vampiros morrem)"""
        for player_id in self.players:
            player = self.player_data[player_id]
            # Verificar defesa
            for i, card in enumerate(player['defense_bases']):
                if card and card.get('dies_daylight'):
                    # Verificar se tem Capacete das Trevas
                    has_protection = False
                    if player['equipment']['helmet'] and player['equipment']['helmet']['id'] == 'capacete_trevas':
                        has_protection = True
                    
                    if not has_protection:
                        self.graveyard.append(card)
                        player['defense_bases'][i] = None
            
            # Verificar ataque
            for i, card in enumerate(player['attack_bases']):
                if card and card.get('dies_daylight'):
                    has_protection = False
                    if player['equipment']['helmet'] and player['equipment']['helmet']['id'] == 'capacete_trevas':
                        has_protection = True
                    
                    if not has_protection:
                        self.graveyard.append(card)
                        player['attack_bases'][i] = None
    
    def can_act(self, player_id, action):
        """Verifica se o jogador pode realizar uma ação neste turno"""
        player = self.player_data.get(player_id, {})
        
        # Jogadores mortos não podem agir
        if player.get('dead', False):
            return False
        
        if player_id != self.players[self.current_turn]:
            return False
        
        if player_id not in self.turn_actions_used:
            self.turn_actions_used[player_id] = set()
        
        # Cada ação só pode ser feita uma vez por turno
        return action not in self.turn_actions_used[player_id]

    def use_action(self, player_id, action):
        """Registra que uma ação foi usada"""
        self.turn_actions_used[player_id].add(action)
    
    def draw_card(self, player_id):
        """Compra uma carta"""
        if not self.can_act(player_id, 'draw'):
            return {'success': False, 'message': 'Você já comprou uma carta neste turno'}
        
        if not self.deck:
            return {'success': False, 'message': 'Monte vazio'}
        
        card = self.deck.pop()
        self.player_data[player_id]['hand'].append(card)
        self.use_action(player_id, 'draw')
        
        return {'success': True, 'card': card}
    
    def play_card(self, player_id, card_instance_id, position_type, position_index):
        """Joga uma carta da mão para o campo com validação de tipo"""
        if not self.can_act(player_id, 'play'):
            return {'success': False, 'message': 'Você já jogou uma carta neste turno'}
        
        player = self.player_data[player_id]
        
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
        if position_type in ['attack', 'defense']:
            # Apenas criaturas podem ir para bases de ataque/defesa
            if card_to_play.get('type') != 'creature':
                return {'success': False, 'message': 'Apenas criaturas podem ser colocadas em bases de ataque ou defesa'}
        
        elif position_type == 'equipment':
            # Equipamentos vão para slots específicos
            valid_equipment_types = {
                'weapon': ['weapon'],
                'helmet': ['armor'],
                'armor': ['armor'],
                'boots': ['armor'],
                'mount': ['creature']  # Montarias podem ser criaturas específicas
            }
            
            slot_name = position_index  # position_index é o nome do slot aqui
            if slot_name not in valid_equipment_types:
                return {'success': False, 'message': 'Slot de equipamento inválido'}
            
            if card_to_play.get('type') not in valid_equipment_types[slot_name]:
                return {'success': False, 'message': f'Esta carta não pode ser equipada em {slot_name}'}
            
            # Verificar se o slot está vazio
            if player['equipment'][slot_name] is not None:
                return {'success': False, 'message': f'Slot de {slot_name} já está ocupado'}
        
        # Remover carta da mão
        player['hand'].pop(card_index)
        
        # Colocar carta no local apropriado
        if position_type in ['attack', 'defense']:
            if position_type == 'attack':
                if position_index >= len(player['attack_bases']):
                    return {'success': False, 'message': 'Posição de ataque inválida'}
                if player['attack_bases'][position_index] is not None:
                    return {'success': False, 'message': 'Posição de ataque ocupada'}
                player['attack_bases'][position_index] = card_to_play
            else:  # defense
                if position_index >= len(player['defense_bases']):
                    return {'success': False, 'message': 'Posição de defesa inválida'}
                if player['defense_bases'][position_index] is not None:
                    return {'success': False, 'message': 'Posição de defesa ocupada'}
                player['defense_bases'][position_index] = card_to_play
        
        elif position_type == 'equipment':
            player['equipment'][position_index] = card_to_play
        
        self.use_action(player_id, 'play')
        return {'success': True, 'card': card_to_play}
    
    def attack(self, player_id, target_player_id):
        """Ataca outro jogador com verificação de primeira rodada"""
        # Verificar se pode atacar
        can_attack, message = self.can_attack(player_id)
        if not can_attack:
            return {'success': False, 'message': message}
        
        if not self.can_act(player_id, 'attack'):
            return {'success': False, 'message': 'Você já atacou neste turno'}
        
        if target_player_id not in self.players:
            return {'success': False, 'message': 'Jogador alvo inválido'}
        
        # Verificar se o alvo já está morto
        if self.player_data[target_player_id].get('dead', False):
            return {'success': False, 'message': 'Este jogador já está morto'}
        
        attacker = self.player_data.get(player_id)
        defender = self.player_data.get(target_player_id)
        
        if not attacker or not defender:
            return {'success': False, 'message': 'Dados do jogador não encontrados'}
        
        # Verificar se tem cartas de ataque
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
        
        # Talismã Guerreiro
        for talisman in attacker['talismans']:
            if talisman['id'] == 'talisma_guerreiro':
                attack_power += 1000
        
        # Coletar cartas de defesa
        defense_cards = []
        for i, card in enumerate(defender['defense_bases']):
            if card and card.get('type') == 'creature':
                defense_cards.append({
                    'card': card,
                    'index': i,
                    'current_life': card.get('life', 0),
                    'original_life': card.get('life', 0),
                    'name': card.get('name', 'Desconhecido')
                })
        
        # Ordenar cartas de defesa por vida (maior primeiro)
        defense_cards.sort(key=lambda x: x['current_life'], reverse=True)
        
        # Aplicar dano às cartas de defesa
        remaining_damage = attack_power
        damage_log = []
        cards_destroyed = []
        cards_damaged = []
        
        for def_card in defense_cards:
            if remaining_damage <= 0:
                break
            
            card = def_card['card']
            card_life = def_card['current_life']
            
            if remaining_damage >= card_life:
                remaining_damage -= card_life
                self.graveyard.append(card)
                defender['defense_bases'][def_card['index']] = None
                cards_destroyed.append(card['name'])
                damage_log.append(f"{card['name']} foi destruída")
            else:
                new_life = card_life - remaining_damage
                card['life'] = new_life
                cards_damaged.append(f"{card['name']} (-{remaining_damage}❤️)")
                damage_log.append(f"{card['name']} recebeu {remaining_damage} de dano (vida restante: {new_life})")
                remaining_damage = 0
        
        # Dano restante vai para o jogador
        damage_to_player = 0
        player_killed = False
        
        if remaining_damage > 0:
            damage_to_player = remaining_damage
            
            has_immortality = False
            for talisman in defender['hand']:
                if talisman['id'] == 'talisma_imortalidade':
                    has_immortality = True
                    break
            
            if has_immortality:
                defender['life'] = 5000
                #defender['hand'] = [t for t in defender['hand'] if t['id'] != 'talisma_imortalidade']
                damage_log.append("✨ Talismã da Imortalidade salvou o jogador!")
                damage_to_player = 0
            else:
                defender['life'] -= remaining_damage
                damage_log.append(f"⚔️ Jogador recebeu {remaining_damage} de dano direto")
                
                # Verificar se o jogador morreu
                if defender['life'] <= 0:
                    player_killed = True
                    self.process_player_death(target_player_id)
                    damage_log.append(f"💀 {defender['name']} foi derrotado!")

        if player_killed:
            emit('player_died', {
                'player_id': target_player_id,
                'player_name': defender['name'],
                'message': f"{defender['name']} foi derrotado e agora é um espectador!"
            }, room=game_id)
        
        self.use_action(player_id, 'attack')
        
        result = {
            'success': True,
            'total_attack': attack_power,
            'damage_absorbed': attack_power - remaining_damage,
            'damage_to_player': damage_to_player,
            'attacker': player_id,
            'attacker_name': attacker['name'],
            'target': target_player_id,
            'target_name': defender['name'],
            'target_life': defender['life'] if defender['life'] > 0 else 0,
            'cards_destroyed': cards_destroyed,
            'cards_damaged': cards_damaged,
            'player_killed': player_killed,
            'log': damage_log
        }
        
        return result

    def move_card(self, player_id, from_type, from_index, to_type, to_index):
        """Move uma carta entre posições"""
        if not self.can_act(player_id, 'move'):
            return {'success': False, 'message': 'Você já moveu uma carta neste turno'}
        
        player = self.player_data[player_id]
        
        # Validar posições
        if from_type == 'attack':
            if from_index >= len(player['attack_bases']):
                return {'success': False, 'message': 'Posição de origem inválida'}
            card = player['attack_bases'][from_index]
            if not card:
                return {'success': False, 'message': 'Nenhuma carta na posição de origem'}
        elif from_type == 'defense':
            if from_index >= len(player['defense_bases']):
                return {'success': False, 'message': 'Posição de origem inválida'}
            card = player['defense_bases'][from_index]
            if not card:
                return {'success': False, 'message': 'Nenhuma carta na posição de origem'}
        else:
            return {'success': False, 'message': 'Tipo de origem inválido'}
        
        # Validar destino
        if to_type == 'attack':
            if to_index >= len(player['attack_bases']):
                return {'success': False, 'message': 'Posição de destino inválida'}
            if player['attack_bases'][to_index] is not None:
                return {'success': False, 'message': 'Posição de destino ocupada'}
        elif to_type == 'defense':
            if to_index >= len(player['defense_bases']):
                return {'success': False, 'message': 'Posição de destino inválida'}
            if player['defense_bases'][to_index] is not None:
                return {'success': False, 'message': 'Posição de destino ocupada'}
        else:
            return {'success': False, 'message': 'Tipo de destino inválido'}
        
        # Mover carta
        if from_type == 'attack':
            player['attack_bases'][from_index] = None
        else:
            player['defense_bases'][from_index] = None
        
        if to_type == 'attack':
            player['attack_bases'][to_index] = card
        else:
            player['defense_bases'][to_index] = card
        
        self.use_action(player_id, 'move')
        return {'success': True, 'card': card}
    
    def flip_card(self, player_id, position_type, position_index):
        """Desvira uma carta (muda de virada para não virada)"""
        if not self.can_act(player_id, 'flip'):
            return {'success': False, 'message': 'Você já desvirou uma carta neste turno'}
        
        player = self.player_data[player_id]
        
        if position_type == 'attack':
            if position_index >= len(player['attack_bases']):
                return {'success': False, 'message': 'Posição inválida'}
            # Aqui você implementaria a lógica de "virada" se tiver esse estado
            # Por enquanto, apenas registra a ação
        elif position_type == 'defense':
            if position_index >= len(player['defense_bases']):
                return {'success': False, 'message': 'Posição inválida'}
        else:
            return {'success': False, 'message': 'Tipo de posição inválido'}
        
        self.use_action(player_id, 'flip')
        return {'success': True}
    
    def perform_oracle(self, player_id, target_player_id):
        """Realiza um oráculo com seleção de alvo"""
        player = self.player_data[player_id]
        
        # Verificar se tem elfo em defesa
        has_elfo_defense = False
        for card in player['defense_bases']:
            if card and card['id'] == 'elfo':
                has_elfo_defense = True
                break
        
        if not has_elfo_defense:
            return {'success': False, 'message': 'Precisa de um elfo em modo de defesa'}
        
        # Verificar se tem oráculo na mão
        has_oracle = False
        oracle_index = -1
        for i, card in enumerate(player['hand']):
            if card['id'] == 'oraculo':
                has_oracle = True
                oracle_index = i
                break
        
        if not has_oracle:
            return {'success': False, 'message': 'Você não tem o Oráculo'}
        
        # Verificar se o alvo tem talismã da imortalidade
        target_has_immortality = False
        if target_player_id in self.player_data:
            for talisman in self.player_data[target_player_id]['talismans']:
                if talisman['id'] == 'talisma_imortalidade':
                    target_has_immortality = True
                    break
        
        if not target_has_immortality:
            return {'success': False, 'message': 'O alvo não possui Talismã da Imortalidade'}
        
        # Remover oráculo da mão (volta para o deck)
        oracle_card = player['hand'].pop(oracle_index)
        self.deck.insert(0, oracle_card)  # Volta para o topo do deck
        
        return {
            'success': True,
            'message': f'Jogador {player["name"]} revelou um Oráculo contra {self.player_data[target_player_id]["name"]}!',
            'oracle_revealed': True,
            'target': target_player_id
        }

    def check_winner(self):
        """Verifica se há um vencedor"""
        alive_players = []
        for player_id in self.players:
            if self.player_data[player_id]['life'] > 0:
                alive_players.append(player_id)
        
        if len(alive_players) == 1:
            return alive_players[0]
        return None

    def apply_day_damage(self):
        """Aplica dano da luz do dia em criaturas noturnas"""
        for player_id in self.players:
            player = self.player_data[player_id]
            
            # Verificar criaturas em defesa
            for i, card in enumerate(player['defense_bases']):
                if card and card.get('dies_daylight'):
                    self.apply_daylight_damage_to_card(player, card, i, 'defense')
            
            # Verificar criaturas em ataque
            for i, card in enumerate(player['attack_bases']):
                if card and card.get('dies_daylight'):
                    self.apply_daylight_damage_to_card(player, card, i, 'attack')
    
    def apply_daylight_damage_to_card(self, player, card, index, position_type):
        """Aplica dano da luz do dia em uma carta"""
        # Verificar se tem Capacete das Trevas equipado na carta
        has_protection = False
        if 'equipped_items' in card:
            for item in card['equipped_items']:
                if item and item.get('id') == 'capacete_trevas':
                    has_protection = True
                    break
        
        if not has_protection:
            # Aplicar 100 de dano
            current_life = card.get('life', 0)
            new_life = current_life - 100
            
            if new_life <= 0:
                # Carta morre
                self.graveyard.append(card)
                if position_type == 'defense':
                    player['defense_bases'][index] = None
                else:
                    player['attack_bases'][index] = None
            else:
                card['life'] = new_life
    
    def apply_spell_effect(self, spell, caster_id, target_player_id, target_card_id, caster_type):
        """Aplica o efeito específico do feitiço"""
        spell_id = spell['id']
        caster = self.player_data[caster_id]
        
        # Se for Rei Mago ou Mago Negro, pode usar qualquer feitiço mesmo sem ter
        if caster_type in ['rei_mago', 'mago_negro'] and not target_card_id:
            # Lista todos os feitiços disponíveis
            all_spells = [card for card in self.deck + self.graveyard if card.get('type') == 'spell']
            return {'type': 'list_spells', 'spells': all_spells}
        
        # Aplicar efeitos específicos
        if spell_id == 'feitico_cortes':
            # Aumenta ataque de um monstro
            if target_card_id:
                for player in self.players:
                    for base in ['attack_bases', 'defense_bases']:
                        for card in self.player_data[player][base]:
                            if card and card['instance_id'] == target_card_id:
                                card['attack'] = card.get('attack', 0) + 1024
                                return {'type': 'buff', 'target': card['name'], 'effect': '+1024 ataque'}
        
        elif spell_id == 'feitico_duro_matar':
            # Aumenta defesa do jogador
            if target_player_id:
                self.player_data[target_player_id]['life'] += 1024
                return {'type': 'buff', 'target': self.player_data[target_player_id]['name'], 'effect': '+1024 vida'}
        
        elif spell_id == 'feitico_troca':
            # Troca cartas de defesa por ataque
            if target_player_id:
                target = self.player_data[target_player_id]
                attack_bases = target['attack_bases'].copy()
                defense_bases = target['defense_bases'].copy()
                target['attack_bases'] = defense_bases
                target['defense_bases'] = attack_bases
                return {'type': 'swap', 'target': target['name']}
        
        elif spell_id == 'feitico_comunista':
            # Todas as cartas das mãos voltam para a pilha
            for player_id in self.players:
                player = self.player_data[player_id]
                for card in player['hand']:
                    self.deck.append(card)
                player['hand'] = []
            random.shuffle(self.deck)
            return {'type': 'reset_hands'}
        
        elif spell_id == 'feitico_silencio':
            # Próximas duas rodadas sem armadilhas
            for player_id in self.players:
                self.player_data[player_id]['active_effects'].append({
                    'type': 'silence',
                    'duration': 2
                })
            return {'type': 'silence', 'duration': 2}
        
        elif spell_id == 'feitico_para_sempre':
            # Reverte efeito Blade of Vampires
            # Implementar lógica
            return {'type': 'revert_vampire'}
        
        elif spell_id == 'feitico_capitalista':
            # Troca cartas com outros jogadores
            if target_player_id:
                # Implementar lógica de troca
                return {'type': 'trade', 'target': target_player_id}
        
        return {'type': 'unknown'}
    
    def toggle_mage_block(self, player_id, target_player_id, target_card_id):
        """Rei Mago bloqueia/desbloqueia um mago"""
        if not self.can_act(player_id, 'block'):
            return {'success': False, 'message': 'Você já usou esta habilidade neste turno'}
        
        player = self.player_data[player_id]
        
        # Verificar se tem Rei Mago
        has_rei_mago = False
        for card in player['attack_bases'] + player['defense_bases']:
            if card and card['id'] == 'rei_mago':
                has_rei_mago = True
                break
        
        if not has_rei_mago:
            return {'success': False, 'message': 'Você precisa do Rei Mago em campo'}
        
        # Encontrar o mago alvo
        target_player = self.player_data[target_player_id]
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
        
        self.use_action(player_id, 'block')
        
        return {
            'success': True,
            'message': message,
            'target_card': target_card['name'],
            'blocked': target_card.get('blocked', False)
        }
    
    def revive_from_graveyard(self, player_id, target_card_id):
        """Revive uma carta do cemitério usando 4 runas"""
        player = self.player_data[player_id]
        
        # Verificar se tem 4 runas na mão
        runes_in_hand = [card for card in player['hand'] if card.get('type') == 'rune']
        if len(runes_in_hand) < 4:
            return {'success': False, 'message': 'Você precisa de 4 runas na mão'}
        
        # Encontrar carta no cemitério
        target_card = None
        for i, card in enumerate(self.graveyard):
            if card['instance_id'] == target_card_id:
                target_card = card
                self.graveyard.pop(i)
                break
        
        if not target_card:
            return {'success': False, 'message': 'Carta não encontrada no cemitério'}
        
        # Remover 4 runas da mão
        runes_removed = 0
        new_hand = []
        for card in player['hand']:
            if card.get('type') == 'rune' and runes_removed < 4:
                runes_removed += 1
                # Runas vão para o cemitério
                self.graveyard.append(card)
            else:
                new_hand.append(card)
        
        player['hand'] = new_hand
        
        # Adicionar carta revivida à mão
        player['hand'].append(target_card)
        
        return {
            'success': True,
            'card': target_card,
            'message': f"{target_card['name']} foi revivido do cemitério"
        }
    
    def cleanup_empty_games():
        """Limpa jogos vazios ou abandonados"""
        games_to_remove = []
        for game_id, game in games.items():
            # Se não tem jogadores ou todos desconectaram
            if len(game.players) == 0:
                games_to_remove.append(game_id)
            # Se o jogo começou mas não tem jogadores ativos
            elif game.started and all(p not in game.player_data for p in game.players):
                games_to_remove.append(game_id)
        
        for game_id in games_to_remove:
            del games[game_id]
            print(f"Jogo {game_id} removido por inatividade")
    
    def get_available_spells(self, player_id):
        """Retorna lista de feitiços disponíveis baseado nos magos em campo"""
        player = self.player_data[player_id]
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
        
        # Se tem Rei Mago ou Mago Negro, pode ver todos os feitiços do jogo
        if has_rei_mago or has_mago_negro:
            # Coletar todos os feitiços do deck e cemitério
            all_spells = []
            for card in self.deck:
                if card.get('type') == 'spell' and card not in all_spells:
                    all_spells.append(card)
            for card in self.graveyard:
                if card.get('type') == 'spell' and card not in all_spells:
                    all_spells.append(card)
            available_spells = all_spells
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
    
    def cast_spell(self, player_id, spell_card_id, target_player_id=None, target_card_id=None):
        """Usa um feitiço com suporte para Rei Mago/Mago Negro"""
        if not self.can_act(player_id, 'spell'):
            return {'success': False, 'message': 'Você já usou um feitiço neste turno'}
        
        player = self.player_data[player_id]
        
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
        
        # Se for Rei Mago ou Mago Negro, pode usar qualquer feitiço (não precisa ter na mão)
        if caster_type in ['rei_mago', 'mago_negro']:
            # Procurar o feitiço no deck ou cemitério
            spell_card = None
            for card in self.deck + self.graveyard:
                if card.get('type') == 'spell' and (card['id'] == spell_card_id or card['instance_id'] == spell_card_id):
                    spell_card = card
                    break
            
            if not spell_card:
                return {'success': False, 'message': 'Feitiço não encontrado'}
            
            # Remover do deck ou cemitério se aplicável
            if spell_card in self.deck:
                self.deck.remove(spell_card)
            elif spell_card in self.graveyard:
                self.graveyard.remove(spell_card)
        else:
            # Procurar feitiço na mão
            spell_card = None
            spell_index = -1
            for i, card in enumerate(player['hand']):
                if card['instance_id'] == spell_card_id:
                    spell_card = card
                    spell_index = i
                    break
            
            if not spell_card:
                return {'success': False, 'message': 'Feitiço não encontrado na mão'}
            
            # Remover da mão
            player['hand'].pop(spell_index)
        
        # Aplicar efeito do feitiço
        result = self.apply_spell_effect(spell_card, player_id, target_player_id, target_card_id, caster_type)
        
        # Feitiço volta para o deck (embaixo)
        self.deck.append(spell_card)
        
        self.use_action(player_id, 'spell')
        
        return {
            'success': True,
            'spell': spell_card,
            'effect': result,
            'caster_type': caster_type
        }
    
    def equip_item_to_creature(self, player_id, item_card_id, creature_card_id):
        """Equipa um item em uma criatura específica"""
        print(f"Tentando equipar item {item_card_id} em criatura {creature_card_id}")
        
        player = self.player_data.get(player_id)
        if not player:
            return {'success': False, 'message': 'Jogador não encontrado'}
        
        # Encontrar item na mão
        item_card = None
        item_index = -1
        
        for i, card in enumerate(player['hand']):
            if card['instance_id'] == item_card_id:
                item_card = card
                item_index = i
                print(f"Item encontrado na mão: {item_card['name']} (tipo: {item_card.get('type')})")
                break
        
        if not item_card:
            return {'success': False, 'message': 'Item não encontrado na mão'}
        
        # Verificar se é um item equipável (weapon OU armor)
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
                    print(f"Criatura encontrada: {target_creature['name']} na {base}[{i}]")
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
        
        # Inicializar lista de itens equipados se não existir
        if 'equipped_items' not in target_creature:
            target_creature['equipped_items'] = []
        
        # Verificar limite de itens por tipo
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
        
        # Aplicar bônus do item
        if item_card.get('attack'):
            target_creature['attack'] = target_creature.get('attack', 0) + item_card['attack']
        if item_card.get('protection'):
            target_creature['life'] = target_creature.get('life', 0) + item_card['protection']
        if item_card.get('life'):
            target_creature['life'] = target_creature.get('life', 0) + item_card['life']
        
        print(f"Item {item_card['name']} equipado em {target_creature['name']}")
        
        return {
            'success': True,
            'creature': target_creature['name'],
            'item': item_card['name'],
            'message': f"{item_card['name']} equipado em {target_creature['name']}"
        }
    
    def swap_positions(self, player_id, pos1_type, pos1_index, pos2_type, pos2_index):
        """Troca duas cartas de posição (pode ser entre ataque e defesa)"""
        if not self.can_act(player_id, 'swap'):
            return {'success': False, 'message': 'Você já realizou uma troca neste turno'}
        
        player = self.player_data[player_id]
        
        # Validar posições
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
        
        # Se ambas as posições estão vazias, não faz sentido trocar
        if not card1 and not card2:
            return {'success': False, 'message': 'Ambas as posições estão vazias'}
        
        # Realizar troca
        positions[pos1_type][pos1_index] = card2
        positions[pos2_type][pos2_index] = card1
        
        self.use_action(player_id, 'swap')
        
        return {
            'success': True,
            'swapped': True,
            'message': 'Cartas trocadas com sucesso'
        }

    def reconnect_player(self, player_id, player_name):
        """Reconecta um jogador existente ao jogo"""
        print(f"Tentando reconectar jogador {player_name} ({player_id})")
        
        if player_id in self.player_data:
            # Jogador já existe, apenas atualizar status
            print(f"Jogador {player_name} reconectado com sucesso")
            return {
                'success': True,
                'player_id': player_id,
                'player_name': player_name,
                'game_started': self.started
            }
        else:
            # Jogador não encontrado, verificar se pode entrar como novo
            if len(self.players) >= self.max_players or self.started:
                print(f"Jogo cheio ou já começou. Não pode reconectar como novo.")
                return {'success': False, 'message': 'Jogo cheio ou já começou'}
            
            # Adicionar como novo jogador
            if self.add_player(player_id, player_name):
                print(f"Jogador {player_name} adicionado como novo durante reconexão")
                return {
                    'success': True,
                    'player_id': player_id,
                    'player_name': player_name,
                    'game_started': self.started
                }
        
        return {'success': False, 'message': 'Erro ao reconectar'}

    def get_graveyard_cards(self, player_id=None):
        """Retorna lista de cartas no cemitério (com informações básicas)"""
        graveyard_info = []
        for card in self.graveyard:
            card_info = {
                'instance_id': card['instance_id'],
                'name': card['name'],
                'type': card.get('type', 'unknown'),
                'description': card.get('description', ''),
                'life': card.get('life', 0),
                'attack': card.get('attack', 0)
            }
            graveyard_info.append(card_info)
        return graveyard_info

    def revive_from_graveyard(self, player_id, target_card_id):
        """Revive uma carta específica do cemitério usando 4 runas"""
        print(f"Tentando reviver carta {target_card_id} para jogador {player_id}")
        
        player = self.player_data.get(player_id)
        if not player:
            return {'success': False, 'message': 'Jogador não encontrado'}
        
        # Verificar se tem 4 runas na mão
        runes_in_hand = []
        for card in player['hand']:
            if card.get('type') == 'rune' or card.get('id') == 'runa':
                runes_in_hand.append(card)
        
        print(f"Runas na mão: {len(runes_in_hand)}")
        
        if len(runes_in_hand) < 4:
            return {'success': False, 'message': f'Você precisa de 4 runas na mão (tem {len(runes_in_hand)})'}
        
        # Encontrar carta no cemitério
        target_card = None
        card_index = -1
        
        for i, card in enumerate(self.graveyard):
            if card['instance_id'] == target_card_id:
                target_card = card
                card_index = i
                print(f"Carta encontrada no cemitério: {target_card['name']}")
                break
        
        if not target_card:
            # Tentar buscar por nome (fallback)
            for i, card in enumerate(self.graveyard):
                if card['name'].lower() == target_card_id.lower():
                    target_card = card
                    card_index = i
                    print(f"Carta encontrada por nome: {target_card['name']}")
                    break
        
        if not target_card:
            return {'success': False, 'message': 'Carta não encontrada no cemitério'}
        
        # Remover do cemitério
        self.graveyard.pop(card_index)
        
        # Remover 4 runas da mão
        runes_removed = 0
        new_hand = []
        for card in player['hand']:
            if (card.get('type') == 'rune' or card.get('id') == 'runa') and runes_removed < 4:
                runes_removed += 1
                # Runas vão para o cemitério
                self.graveyard.append(card)
                print(f"Runa removida: {card['name']}")
            else:
                new_hand.append(card)
        
        player['hand'] = new_hand
        
        # Restaurar vida da carta (se era criatura)
        if target_card.get('type') == 'creature':
            # Restaurar vida original baseada na definição da carta
            original_card = CARDS.get(target_card['id'], {})
            if original_card and 'life' in original_card:
                target_card['life'] = original_card['life']
        
        # Adicionar carta revivida à mão
        player['hand'].append(target_card)
        
        print(f"Carta {target_card['name']} revivida com sucesso!")
        
        return {
            'success': True,
            'card': {
                'name': target_card['name'],
                'type': target_card.get('type', 'unknown')
            },
            'message': f"{target_card['name']} foi revivido do cemitério!"
        }

    def perform_ritual(self, player_id, ritual_id, target_player_id=None):
        if not self.can_act(player_id, 'ritual'):
            return {'success': False, 'message': 'Você já realizou um ritual neste turno'}
        
        player = self.player_data[player_id]
        
        # Verificar se tem Mago Negro em campo
        has_mago_negro = False
        for card in player['attack_bases'] + player['defense_bases']:
            if card and card['id'] == 'mago_negro':
                has_mago_negro = True
                break
        
        # Se não tem Mago Negro, verificar se tem a carta do ritual na mão
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
            
            # Remover ritual da mão
            player['hand'].pop(ritual_index)
        else:
            # Mago Negro pode realizar rituais sem ter a carta
            print(f"Mago Negro realizando ritual {ritual_id} sem possuir a carta")
        
        # Verificar condições específicas do ritual
        if ritual_id == 'ritual_157':
            # Precisa de alvo
            if not target_player_id:
                return {'success': False, 'message': 'Selecione um alvo para o Ritual 157'}
            
            # Verificar condições
            can_cast, message = RitualManager.check_ritual_157(self, player_id)
            if not can_cast:
                return {'success': False, 'message': message}
            
            # Executar ritual
            result = RitualManager.execute_ritual_157(self, player_id, target_player_id)
            
        elif ritual_id == 'ritual_amor':
            # Precisa de alvo (quem tem a profecia)
            if not target_player_id:
                return {'success': False, 'message': 'Selecione o alvo da profecia'}
            
            # Verificar condições
            can_cast, message = RitualManager.check_ritual_amor(self, player_id)
            if not can_cast:
                return {'success': False, 'message': message}
            
            # Verificar se o alvo tem profecia
            target = self.player_data[target_player_id]
            has_profecia = False
            if target.get('profecia_alvo') or any(effect.get('type') == 'profecia_morte' for effect in target['active_effects']):
                has_profecia = True
            
            if not has_profecia:
                return {'success': False, 'message': 'O alvo não possui nenhuma profecia ativa'}
            
            # Executar ritual
            result = RitualManager.execute_ritual_amor(self, player_id, target_player_id)
        
        else:
            return {'success': False, 'message': 'Ritual desconhecido'}
        
        self.use_action(player_id, 'ritual')
        result['ritual_id'] = ritual_id
        return result
    def get_available_rituals(self, player_id): return RitualManager.get_available_rituals(self, player_id)

    def process_player_death(self, player_id):
        """Processa a morte de um jogador: move cartas para lugares apropriados e marca como morto"""
        print(f"Processando morte do jogador {player_id}")
        
        player = self.player_data[player_id]
        
        # Marcar como morto
        player['dead'] = True
        player['observer'] = True
        player['life'] = 0
        
        # Processar cartas da mão
        hand_cards = player['hand'].copy()
        player['hand'] = []
        
        for card in hand_cards:
            if card.get('type') == 'creature':
                # Criaturas vão para o cemitério
                self.graveyard.append(card)
                print(f"Criatura {card['name']} movida para o cemitério")
            else:
                # Outros tipos de carta voltam para o monte (embaixo)
                self.deck.append(card)
                print(f"Carta {card['name']} (tipo: {card.get('type')}) voltou para o monte")
        
        # Processar cartas em campo (ataque)
        for i, card in enumerate(player['attack_bases']):
            if card:
                self.graveyard.append(card)
                player['attack_bases'][i] = None
                print(f"Carta de ataque {card['name']} movida para o cemitério")
        
        # Processar cartas em campo (defesa)
        for i, card in enumerate(player['defense_bases']):
            if card:
                self.graveyard.append(card)
                player['defense_bases'][i] = None
                print(f"Carta de defesa {card['name']} movida para o cemitério")
        
        # Processar equipamentos
        for slot, card in player['equipment'].items():
            if card:
                self.graveyard.append(card)
                player['equipment'][slot] = None
                print(f"Equipamento {card['name']} movido para o cemitério")
        
        # Processar talismãs (vão para o cemitério também)
        for talisman in player['talismans']:
            self.graveyard.append(talisman)
        player['talismans'] = []
        
        # Embaralhar o monte para misturar as cartas que voltaram
        random.shuffle(self.deck)
        
        print(f"Jogador {player['name']} processado como morto. Monte: {len(self.deck)} cartas, Cemitério: {len(self.graveyard)} cartas")

# Rotas da aplicação
@app.route('/')
def index():
    return render_template('index.html')
@app.route('/rules')
def rules():
    return render_template('rules.html')

@app.route('/game/<game_id>')
def game(game_id):
    if game_id not in games:
        return "Jogo não encontrado", 404
    return render_template('game.html', game_id=game_id)

@app.route('/api/games')
def get_games():
    games_list = []
    for game_id, game in games.items():
        games_list.append({
            'id': game_id,
            'players': len(game.players),
            'max_players': game.max_players,
            'started': game.started
        })
    return jsonify(games_list)

@app.route('/api/create-game', methods=['POST'])
def create_game():
    game_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    games[game_id] = Game(game_id)
    return jsonify({'game_id': game_id})

@app.route('/start-game/<game_id>', methods=['POST'])
def start_game(game_id):
    if game_id in games:
        game = games[game_id]
        if len(game.players) >= 2:  # Mínimo 2 jogadores
            game.started = True
            # Notificar todos os jogadores
            socketio.emit('game_started', {'game_id': game_id}, room=game_id)
            return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'Não foi possível iniciar o jogo'})

@app.route('/api/cleanup-games', methods=['POST'])
def cleanup_games():
    Game.cleanup_empty_games()
    return jsonify({'success': True})

# Socket.IO events
@socketio.on('connect')
def handle_connect():
    print(f'Client connected: {request.sid}')

@socketio.on('disconnect')
def handle_disconnect():
    print(f'Client disconnected: {request.sid}')
    # Remover jogador das salas
    for game_id, game in games.items():
        if request.sid in game.players:
            game.players.remove(request.sid)
            if request.sid in game.player_data:
                del game.player_data[request.sid]
            emit('player_left', {'player_id': request.sid}, room=game_id)
            break

@socketio.on('join_game')
def handle_join_game(data):
    game_id = data['game_id']
    player_name = data['player_name']
    
    if game_id not in games:
        emit('error', {'message': 'Jogo não encontrado'})
        return
    
    game = games[game_id]
    
    if game.started:
        emit('error', {'message': 'O jogo já começou'})
        return
    
    if game.add_player(request.sid, player_name):
        join_room(game_id)
        emit('player_joined', {
            'player_id': request.sid,
            'player_name': player_name,
            'players': [{'id': p, 'name': game.player_data[p]['name']} for p in game.players]
        }, room=game_id)
    else:
        emit('error', {'message': 'Não foi possível entrar no jogo'})

@socketio.on('get_game_state')
def handle_get_game_state(data):
    game_id = data['game_id']
    if game_id in games:
        game = games[game_id]
        player_id = request.sid
        
        if player_id in game.player_data:
            # Filtrar informações para o jogador
            state = {
                'game_id': game_id,
                'started': game.started,
                'time_of_day': game.time_of_day,
                'time_cycle': game.time_cycle,
                'current_turn': game.players[game.current_turn] if game.players else None,
                'players': {},
                'deck_count': len(game.deck),
                'graveyard_count': len(game.graveyard),
                'current_player_dead': game.player_data[player_id].get('dead', False)  # Novo campo
            }
            
            # Informações de todos os jogadores (públicas)
            for p_id in game.players:
                if p_id in game.player_data:
                    player_info = {
                        'name': game.player_data[p_id]['name'],
                        'life': game.player_data[p_id]['life'] if not game.player_data[p_id].get('dead', False) else 0,
                        'attack_bases': game.player_data[p_id]['attack_bases'],
                        'defense_bases': game.player_data[p_id]['defense_bases'],
                        'talisman_count': len(game.player_data[p_id]['talismans']),
                        'runes': game.player_data[p_id]['runes'],
                        'dead': game.player_data[p_id].get('dead', False),  # Informar se está morto
                        'observer': game.player_data[p_id].get('observer', False)
                    }
                    
                    # Informações privadas apenas para o próprio jogador
                    if p_id == player_id and not player_info.get('dead', False):
                        player_info['hand'] = game.player_data[p_id]['hand']
                        player_info['equipment'] = game.player_data[p_id]['equipment']
                        player_info['talismans'] = game.player_data[p_id]['talismans']
                    
                    state['players'][p_id] = player_info
            
            emit('game_state', state)
        else:
            emit('error', {'message': 'Jogador não encontrado'})

@socketio.on('get_graveyard')
def handle_get_graveyard(data):
    """Retorna lista de cartas no cemitério"""
    game_id = data['game_id']
    
    if game_id not in games:
        emit('error', {'message': 'Jogo não encontrado'})
        return
    
    game = games[game_id]
    player_id = request.sid
    
    if player_id not in game.player_data:
        emit('error', {'message': 'Jogador não encontrado'})
        return
    
    graveyard_cards = game.get_graveyard_cards()
    
    emit('graveyard_list', {
        'cards': graveyard_cards,
        'count': len(graveyard_cards)
    })

@socketio.on('get_rituals')
def handle_get_rituals(data):
    """Retorna lista de rituais disponíveis para o jogador"""
    game_id = data['game_id']
    
    if game_id not in games:
        emit('error', {'message': 'Jogo não encontrado'})
        return
    
    game = games[game_id]
    player_id = request.sid
    
    if player_id not in game.player_data:
        emit('error', {'message': 'Jogador não encontrado'})
        return
    
    rituals = game.get_available_rituals(player_id)
    
    emit('rituals_list', {
        'rituals': rituals,
        'count': len(rituals)
    })

@socketio.on('reconnect_game')
def handle_reconnect_game(data):
    """Gerencia reconexão de jogadores"""
    game_id = data['game_id']
    player_id = data['player_id']
    player_name = data['player_name']
    
    print(f"Tentativa de reconexão: {player_name} ({player_id}) na sala {game_id}")
    
    if game_id not in games:
        emit('error', {'message': 'Jogo não encontrado'})
        return
    
    game = games[game_id]
    
    # Tentar reconectar
    result = game.reconnect_player(player_id, player_name)
    
    if result['success']:
        # Adicionar à sala
        join_room(game_id)
        
        # Atualizar lista de jogadores
        players_list = [{'id': p, 'name': game.player_data[p]['name']} for p in game.players]
        
        # Notificar todos
        emit('player_joined', {
            'player_id': player_id,
            'player_name': player_name,
            'players': players_list,
            'reconnected': True
        }, room=game_id)
        
        # Notificar o jogador reconectado
        emit('reconnect_success', {
            'player_id': player_id,
            'player_name': player_name,
            'game_started': game.started
        })
        
        print(f"Jogador {player_name} reconectado com sucesso")
    else:
        emit('error', {'message': result['message']})

@socketio.on('ping_game')
def handle_ping_game(data):
    """Mantém a conexão ativa e verifica se jogador ainda está no jogo"""
    game_id = data['game_id']
    player_id = data['player_id']
    
    if game_id in games:
        game = games[game_id]
        if player_id in game.player_data:
            # Jogador ainda está no jogo
            emit('pong_game', {'status': 'ok'})
        else:
            emit('pong_game', {'status': 'player_not_found'})

@socketio.on('player_action')
def handle_player_action(data):
    game_id = data['game_id']
    action = data['action']
    params = data.get('params', {})
    
    print(f"Ação recebida: {action} no jogo {game_id} do jogador {request.sid}")
    
    if game_id not in games:
        emit('error', {'message': 'Jogo não encontrado'})
        return
    
    game = games[game_id]
    player_id = request.sid
    
    if not game.started:
        emit('error', {'message': 'O jogo ainda não começou'})
        return
    
    if player_id not in game.player_data:
        emit('error', {'message': 'Jogador não encontrado'})
        return
    
    if game.player_data[player_id].get('dead', False):
        emit('error', {'message': 'Você está morto e não pode mais realizar ações. Agora você é um espectador.'})
        return

    if game.players[game.current_turn] != player_id:
        emit('error', {'message': 'Não é o seu turno'})
        return

    result = None
    
    try:
        if action == 'draw':
            result = game.draw_card(player_id)
        elif action == 'play_card':
            result = game.play_card(player_id, params['card_id'], params['position_type'], params['position_index'])
        elif action == 'attack':
            result = game.attack(player_id, params['target_id'])
        elif action == 'equip_item':
            result = game.equip_item_to_creature(player_id, params['item_card_id'], params['creature_card_id'])
        elif action == 'cast_spell':
            result = game.cast_spell(player_id, params['spell_id'], params.get('target_player_id'), params.get('target_card_id'))
        elif action == 'ritual':
            result = game.perform_ritual(player_id, params['ritual_id'], params.get('target_player_id'))
        elif action == 'swap_positions':
            result = game.swap_positions(
                player_id, 
                params['pos1_type'], 
                params['pos1_index'], 
                params['pos2_type'], 
                params['pos2_index']
            )
        elif action == 'move_card':
            result = game.move_card(player_id, params['from_type'], params['from_index'], params['to_type'], params['to_index'])
        elif action == 'flip_card':
            result = game.flip_card(player_id, params['position_type'], params['position_index'])
        elif action == 'oracle':
            result = game.perform_oracle(player_id, params['target_id'])
        elif action == 'revive':
            result = game.revive_from_graveyard(player_id, params.get('card_id'))
        elif action == 'end_turn':
            game.next_turn()
            result = {'success': True, 'next_turn': game.players[game.current_turn]}
        
        if result and result.get('success'):
            # Registrar ação para primeira rodada (exceto end_turn)
            first_round_ended = False
            if action != 'end_turn':
                first_round_ended = game.register_action(player_id, action)
            
            if first_round_ended:
                result['first_round_ended'] = True
                # Notificar todos que a primeira rodada terminou
                emit('first_round_ended', {}, room=game_id)
            
            print(f"Ação {action} bem-sucedida: {result}")
            emit('action_success', {
                'player_id': player_id,
                'action': action,
                'result': result
            }, room=game_id)
            
            winner = game.check_winner()
            if winner:
                emit('game_over', {'winner': winner}, room=game_id)
        else:
            error_msg = result['message'] if result else 'Ação inválida'
            print(f"Erro na ação {action}: {error_msg}")
            emit('action_error', {'message': error_msg})
            
    except Exception as e:
        print(f"Exceção na ação {action}: {str(e)}")
        import traceback
        traceback.print_exc()
        emit('action_error', {'message': f'Erro interno: {str(e)}'})

if __name__ == '__main__':
    socketio.run(app, debug=True, port=5000)