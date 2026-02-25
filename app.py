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
    "elfo": {"id": "elfo", "name": "Elfo", "type": "creature", "life": 512, "attack": 512, "count": 40, "description": "Não ataca outros elfos. Use para realizar oraculos."},
    "zumbi": {"id": "zumbi", "name": "Zumbi", "type": "creature", "life": 100, "attack": 100, "count": 30, "description": "Morre durante o dia. A menos que derrotado por outro zumbi volta para a mão do jogador.", "dies_daylight": True},
    "medusa": {"id": "medusa", "name": "Medusa", "type": "creature", "life": 1024, "attack": 150, "count": 1, "description": "Seu ataque transforma personagens em pedra. Cartas com maior vida são imunes."},
    "vampiro_tayler": {"id": "vampiro_tayler", "name": "Vampiro - Necrothic Tayler", "type": "creature", "life": 512, "attack": 100, "count": 1, "description": "Rouba a vida do oponente para recuperar a vida de seu jogador.", "dies_daylight": True},
    "vampiro_wers": {"id": "vampiro_wers", "name": "Vampiro - Benjamim Wers", "type": "creature", "life": 512, "attack": 250, "count": 1, "description": "Mata todos os centauros em campo dos oponentes e entrega a vida a jogador.", "dies_daylight": True},
    "profeta": {"id": "profeta", "name": "Profeta", "type": "creature", "life": 256, "attack": 50, "count": 1, "description": "Anuncia a morte de um monstro para duas rodadas a frente. A maldição pode ser retirada caso o jogador seja derrotado."},
    "mago_negro": {"id": "mago_negro", "name": "Mago Negro", "type": "creature", "life": 2000, "attack": 1500, "count": 1, "description": "Não se subordina ao Rei Mago. Realiza rituais sem possuir a carta"},
    "apollo": {"id": "apollo", "name": "Apollo", "type": "creature", "life": 8200, "attack": 2000, "count": 1, "description": "Ataques sofridos com menos de 5k de dano recuperam a vida do jogador se colocado na defesa, não pode ficar na defesa por mais de 5 rodadas. Durante o dia pode revelar cartas em jogo do oponente."},
    "apofis": {"id": "apofis", "name": "Apofis", "type": "creature", "life": 32500, "attack": 5000, "count": 1, "description": "Rei do Caos. Pode desativar armadilhas e magias de outros jogadores."},
    "leviatan": {"id": "leviatan", "name": "Leviatã", "type": "creature", "life": 15000, "attack": 15000, "count": 1, "description": "Imune a elementais de fogo. Só pode ser domado por deuses e magos supremos."},
    "mago": {"id": "mago", "name": "Mago", "type": "creature", "life": 800, "attack": 300, "count": 25, "description": "Use-o para invocar feitiços."},
    "ninfa": {"id": "ninfa", "name": "Ninfa - Belly Lorem", "type": "creature", "life": 512, "attack": 128, "count": 1, "description": "Torna o jogador imune a rituais."},
    "centauro": {"id": "centauro", "name": "Centauro", "type": "creature", "life": 512, "attack": 150, "count": 35, "description": "O jogador pode colocar personagens para montar no centauro. Realiza qualquer ataque terrestre."},
    "super_centauro": {"id": "super_centauro", "name": "Super Centauro", "type": "creature", "life": 600, "attack": 256, "count": 5, "description": "Apenas ataques diretos. Pode encantar centauros de outros jogadores e pegar eles para a sua mão (os centauros que estão em campo)"},
    "rei_mago": {"id": "rei_mago", "name": "Rei Mago", "type": "creature", "life": 2000, "attack": 1500, "count": 1, "description": "Pode impedir outros magos de realizar feitiços. Realiza feitiços sem possuir a carta."},
    "dragao": {"id": "dragao", "name": "Dragão", "type": "creature", "life": 5000, "attack": 1500, "count": 3, "description": "Seu ataque incendeia o inimigo, com isso ele toma 50 de danos nas próximas rodadas do fogo."},
    "fenix": {"id": "fenix", "name": "Fênix", "type": "creature", "life": 32500, "attack": 10000, "count": 1, "description": "Grande ave com ataque de fogo, pode mudar de dia para noite e vice-versa quando bem entender."},
    
    # Itens/Espadas
    "lamina_almas": {"id": "lamina_almas", "name": "Lâmina das Almas", "type": "weapon", "attack": 0, "count": 1, "description": "Assume o dano de uma carta do cemitério. Só pode ser equipado por Elfos, magos e vampiros."},
    "blade_vampires": {"id": "blade_vampires", "name": "Blade of Vampires", "type": "weapon", "attack": 5000, "count": 1, "description": "Só pode ser usada por um vampiro. Seu ataque torna o oponente noturno (morre de dia)"},
    "blade_dragons": {"id": "blade_dragons", "name": "Blade of Dragons", "type": "weapon", "attack": 5000, "count": 1, "description": "Usada apenas por elfos ou vampiros. Seu ataque pode eliminar personagens permanentemente tornando impossíveis de reviver ou ser invocados de volta do cemitério."},
    
    # Armaduras/Equipamentos
    "capacete_trevas": {"id": "capacete_trevas", "name": "Capacete das Trevas", "type": "armor", "protection": 800, "count": 15, "description": "Impede o dano da luz do dia em mortos-vivos e a proteção é adicionada a carta."},
    
    # Talismãs (não podem ser jogados, apenas segurados)
    "talisma_ordem": {"id": "talisma_ordem", "name": "Talismã - Ordem", "type": "talisman", "count": 1, "description": "Imunidade ao Caos."},
    "talisma_imortalidade": {"id": "talisma_imortalidade", "name": "Talismã - Imortalidade", "type": "talisman", "count": 1, "description": "Se o jogador for morto com este item em mãos ele terá seus pontos de vida restaurados."},
    "talisma_verdade": {"id": "talisma_verdade", "name": "Talismã - Verdade", "type": "talisman", "count": 1, "description": "Imunidade a feitiços e oráculos."},
    "talisma_guerreiro": {"id": "talisma_guerreiro", "name": "Talismã - Guerreiro", "type": "talisman", "count": 1, "description": "Aumenta em 1000 pontos o ataque e defesa do jogador."},
    
    # Runas
    "runa": {"id": "runa", "name": "Runa", "type": "rune", "count": 20, "description": "Colete quatro runas para realizar uma invocação de um personagem do cemitério."},
    
    # Feitiços
    "feitico_cortes": {"id": "feitico_cortes", "name": "Feitiço - Cortes", "type": "spell", "count": 1, "description": "Aumenta ataque de um monstro em 1024 pontos."},
    "feitico_duro_matar": {"id": "feitico_duro_matar", "name": "Feitiço - Duro de matar", "type": "spell", "count": 1, "description": "Aumenta defesa do jogador em 1024 pontos."},
    "feitico_troca": {"id": "feitico_troca", "name": "Feitiço - Troca", "type": "spell", "count": 1, "description": "Troca as cartas do Jogador de defesa para ataque e vice-versa de um jogador."},
    "feitico_comunista": {"id": "feitico_comunista", "name": "Feitiço - Comunista", "type": "spell", "count": 1, "description": "Faz as cartas das mãos dos jogadores irem de volta para a pilha."},
    "feitico_silencio": {"id": "feitico_silencio", "name": "Feitiço - Silêncio", "type": "spell", "count": 1, "description": "Os ataques das próximas duas rodadas não ativam armadilhas."},
    "feitico_para_sempre": {"id": "feitico_para_sempre", "name": "Feitiço - Para Sempre", "type": "spell", "count": 1, "description": "Reverte o efeito da espada Blade of Vampires."},
    "feitico_capitalista": {"id": "feitico_capitalista", "name": "Feitiço - Capitalista", "type": "spell", "count": 1, "description": "Troque cartas com outros jogadores."},
    
    # Oraculo
    "oraculo": {"id": "oraculo", "name": "Oráculo", "type": "oracle", "count": 1, "description": "Mate o oponente com o talismã da imortalidade três vezes para que ele seja derrotado permanentemente, seja rápido antes que ele junte todos os talismãs."},
    
    # Rituais (requerem condições específicas)
    "ritual_157": {"id": "ritual_157", "name": "Ritual 157", "type": "ritual", "count": 1, "description": "Requer Apofis, Mago Negro, 6 zumbis e 2 elfos em modo de defesa. Todos os talismãs da mão do jogador escolhido são roubados."},
    "ritual_amor": {"id": "ritual_amor", "name": "Ritual Amor", "type": "ritual", "count": 1, "description": "Requer a Ninfa Belly Lorem e o Vampiro Necrothic Tayler. Anula a maldição do Profeta."},
    
    # Armadilhas
    "armadilha_51": {"id": "armadilha_51", "name": "Armadilha 51", "type": "trap", "count": 1, "description": "Faz o exército do outro jogador ficar bêbado e atacar aliados."},
    "armadilha_171": {"id": "armadilha_171", "name": "Armadilha 171", "type": "trap", "count": 1, "description": "Rouba a carta que te dá um golpe crítico."},
    "armadilha_espelho": {"id": "armadilha_espelho", "name": "Armadilha Espelho", "type": "trap", "count": 1, "description": "Reverte ataques e magia."},
    "armadilha_cheat": {"id": "armadilha_cheat", "name": "Armadilha Cheat", "type": "trap", "count": 1, "description": "Dobrar o ataque e passar para o próximo jogador na rodada, precisa estar de noite e um mago em campo."}
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
            'profecia_rodadas': 0
        }
        return True
    
    def next_turn(self):
        self.current_turn = (self.current_turn + 1) % len(self.players)
        self.turn_actions_used[self.players[self.current_turn]] = set()
        
        # Mudar dia/noite a cada 24 turnos
        self.time_cycle += 1
        if self.time_cycle % 24 == 0:
            self.time_of_day = "night" if self.time_of_day == "day" else "day"
            
            # Efeitos de dia/noite
            if self.time_of_day == "day":
                self.apply_day_effects()
    
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
        """Joga uma carta da mão para o campo"""
        if not self.can_act(player_id, 'play'):
            return {'success': False, 'message': 'Você já jogou uma carta neste turno'}
        
        player = self.player_data[player_id]
        
        # Encontrar carta na mão
        card_to_play = None
        for i, card in enumerate(player['hand']):
            if card['instance_id'] == card_instance_id:
                card_to_play = card
                player['hand'].pop(i)
                break
        
        if not card_to_play:
            return {'success': False, 'message': 'Carta não encontrada na mão'}
        
        # Verificar tipo de carta e posição
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
        else:
            return {'success': False, 'message': 'Tipo de posição inválido'}
        
        self.use_action(player_id, 'play')
        return {'success': True, 'card': card_to_play}
    
    def attack(self, player_id, target_player_id):
        """Ataca outro jogador"""
        if not self.can_act(player_id, 'attack'):
            return {'success': False, 'message': 'Você já atacou neste turno'}
        
        if target_player_id not in self.players:
            return {'success': False, 'message': 'Jogador alvo inválido'}
        
        attacker = self.player_data[player_id]
        defender = self.player_data[target_player_id]
        
        # Calcular poder de ataque total
        total_attack = 0
        for card in attacker['attack_bases']:
            if card:
                total_attack += card.get('attack', 0)
        
        # Adicionar bônus de equipamentos
        if attacker['equipment']['weapon']:
            total_attack += attacker['equipment']['weapon'].get('attack', 0)
        
        # Talismã Guerreiro
        for talisman in attacker['talismans']:
            if talisman['id'] == 'talisma_guerreiro':
                total_attack += 1000
        
        # Calcular defesa total
        total_defense = 0
        defense_cards = []
        for card in defender['defense_bases']:
            if card:
                defense_value = card.get('life', 0)
                if card.get('protection'):
                    defense_value += card['protection']
                total_defense += defense_value
                defense_cards.append(card)
        
        # Aplicar dano
        damage = max(0, total_attack - total_defense)
        
        # Se dano > 0, aplicar ao jogador
        if damage > 0:
            # Verificar talismã da imortalidade
            has_immortality = False
            for talisman in defender['talismans']:
                if talisman['id'] == 'talisma_imortalidade':
                    has_immortality = True
                    break
            
            if has_immortality:
                # Imortalidade: vida restaurada em vez de morrer
                defender['life'] = 5000
                # Remover talismã após uso
                defender['talismans'] = [t for t in defender['talismans'] if t['id'] != 'talisma_imortalidade']
                result_message = "Talismã da Imortalidade salvou o jogador!"
            else:
                defender['life'] -= damage
        
        # Cartas de defesa que absorveram dano vão para o cemitério
        for card in defense_cards:
            self.graveyard.append(card)
        
        # Limpar bases de defesa
        defender['defense_bases'] = [None] * 6
        
        self.use_action(player_id, 'attack')
        
        return {
            'success': True,
            'damage_dealt': damage,
            'attacker': player_id,
            'target': target_player_id,
            'target_life': defender['life']
        }
    
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
        """Realiza um oráculo (requer elfo em defesa)"""
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
        
        # Remover oráculo da mão (volta para o deck)
        oracle_card = player['hand'].pop(oracle_index)
        self.deck.insert(0, oracle_card)  # Volta para o topo do deck
        
        # Revelar oráculo para todos
        return {
            'success': True,
            'message': f'Jogador {player["name"]} revelou um Oráculo! O oráculo voltou para o deck.',
            'oracle_revealed': True
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

# Rotas da aplicação
@app.route('/')
def index():
    return render_template('index.html')

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
                'graveyard_count': len(game.graveyard)
            }
            
            # Informações de todos os jogadores (públicas)
            for p_id in game.players:
                if p_id in game.player_data:
                    player_info = {
                        'name': game.player_data[p_id]['name'],
                        'life': game.player_data[p_id]['life'],
                        'attack_bases': game.player_data[p_id]['attack_bases'],
                        'defense_bases': game.player_data[p_id]['defense_bases'],
                        'talisman_count': len(game.player_data[p_id]['talismans']),
                        'runes': game.player_data[p_id]['runes']
                    }
                    
                    # Informações privadas apenas para o próprio jogador
                    if p_id == player_id:
                        player_info['hand'] = game.player_data[p_id]['hand']
                        player_info['equipment'] = game.player_data[p_id]['equipment']
                        player_info['talismans'] = game.player_data[p_id]['talismans']
                    
                    state['players'][p_id] = player_info
            
            emit('game_state', state)
        else:
            emit('error', {'message': 'Jogador não encontrado'})

@socketio.on('player_action')
def handle_player_action(data):
    game_id = data['game_id']
    action = data['action']
    params = data.get('params', {})
    
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
    
    if game.players[game.current_turn] != player_id:
        emit('error', {'message': 'Não é o seu turno'})
        return
    
    # Processar ações
    result = None
    
    if action == 'draw':
        result = game.draw_card(player_id)
    elif action == 'play_card':
        result = game.play_card(player_id, params['card_id'], params['position_type'], params['position_index'])
    elif action == 'attack':
        result = game.attack(player_id, params['target_id'])
    elif action == 'move_card':
        result = game.move_card(player_id, params['from_type'], params['from_index'], params['to_type'], params['to_index'])
    elif action == 'flip_card':
        result = game.flip_card(player_id, params['position_type'], params['position_index'])
    elif action == 'oracle':
        result = game.perform_oracle(player_id, params['target_id'])
    elif action == 'end_turn':
        game.next_turn()
        result = {'success': True, 'next_turn': game.players[game.current_turn]}
    
    if result and result['success']:
        # Atualizar todos os jogadores
        emit('action_success', {
            'player_id': player_id,
            'action': action,
            'result': result
        }, room=game_id)
        
        # Verificar vencedor
        winner = game.check_winner()
        if winner:
            emit('game_over', {'winner': winner}, room=game_id)
    else:
        emit('action_error', {
            'message': result['message'] if result else 'Ação inválida'
        })

if __name__ == '__main__':
    socketio.run(app, debug=True, port=5000)