# app.py
from flask import Flask, render_template, request, jsonify, make_response, url_for, redirect
from flask_socketio import SocketIO, emit, join_room, leave_room
import cmd, uuid, jwt, json, hashlib, hmac, secrets, random, string, sys, shlex, time, threading
from datetime import datetime, timedelta
from collections import defaultdict
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'twilight-battle-secret'
app.config['JWT_SECRET'] = 'twilight-battle-jwt-secret-key-change-in-production'
app.config['JWT_EXPIRATION_HOURS'] = 24
socketio = SocketIO(app, logging=False, cors_allowed_origins="*")

ACCOUNTS_FILE = 'accounts.json'

def load_accounts():
    try:
        with open(ACCOUNTS_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
def save_accounts(accounts):
    with open(ACCOUNTS_FILE, 'w') as f:
        json.dump(accounts, f, indent=4)
def hash_password(password):
    salt = secrets.token_hex(16)
    password_hash = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    ).hex()
    return f"{salt}${password_hash}"
def verify_password(password, hashed):
    try:
        salt, password_hash = hashed.split('$')
        check_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        ).hex()
        return hmac.compare_digest(check_hash, password_hash)
    except:
        return False
def create_token(username):
    payload = {
        'username': username,
        'exp': datetime.utcnow() + timedelta(hours=app.config['JWT_EXPIRATION_HOURS']),
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, app.config['JWT_SECRET'], algorithm='HS256')
def verify_token(token):
    try:
        payload = jwt.decode(token, app.config['JWT_SECRET'], algorithms=['HS256'])
        return payload['username']
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def get_current_user():
    token = request.cookies.get('auth_token')
    if token:
        return verify_token(token)
    return None

def update_user_game(username, game_id):
    """Atualiza o jogo atual do usuário"""
    accounts = load_accounts()
    if username in accounts:
        accounts[username]['current_game'] = game_id
        save_accounts(accounts)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        username = get_current_user()
        if not username:
            return redirect('/')
        return f(username, *args, **kwargs)
    return decorated_function

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
        "count": 2, 
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
    "talisma_sabedoria": {
        "id": "talisma_sabedoria", 
        "name": "Talismã - Sabedoria", 
        "type": "talisman", 
        "count": 1, 
        "description": "Permite jogar duas cartas por turno (em vez de uma)."
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
    "feitico_cura": {
        "id": "feitico_cura", 
        "name": "Feitiço - Cura", 
        "type": "spell", 
        "count": 10, 
        "description": "Cura 1024 pontos de vida do jogador alvo. Pode ser usado em si mesmo ou em outros jogadores."
    },
    
    # Oraculo
    "oraculo_imortalidade": {
        "id": "oraculo_imortalidade", 
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
    },
    "armadilha_poco": {
        "id": "armadilha_poco", 
        "name": "Armadilha - Poço Sem Fundo", 
        "type": "trap", 
        "count": 1, 
        "description": "Quando o oponente atacar, TODAS as 3 criaturas atacantes são destruídas e enviadas para o cemitério. Armadilha é desativada após o uso."
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
        self.players = []  # Lista de usernames
        self.player_data = {}  # Dict com username como chave
        self.socket_to_username = {}  # Mapeamento socket.id -> username
        self.deck = create_deck()
        self.graveyard = []
        self.started = False
        self.current_turn = 0  # Índice na lista players
        self.time_of_day = "day"
        self.time_cycle = 0
        self.max_players = 6
        self.turn_actions_used = {}
        self.turn_extra_actions = {}

        self.first_round = True
        self.players_acted = set()
        self.attacks_blocked = True
    
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
        
        # Draw 5 initial cards
        hand = []
        for _ in range(5):
            if self.deck:
                hand.append(self.deck.pop())
        
        self.player_data[username] = {
            'name': username,
            'username': username,
            'socket_id': socket_id,
            'life': 5000,
            'hand': hand,
            'attack_bases': [None, None, None],
            'defense_bases': [None, None, None, None, None, None],
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
            'attack_bases': [None, None, None],
            'defense_bases': [None, None, None, None, None, None],
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
            'observer': True,  # Marcar como observador/espectador
            'spectator': True
        }
        
        return True, "Espectador adicionado com sucesso"
    def remove_player(self, username):
        """Remove um jogador do jogo usando username"""
        if username not in self.players or username not in self.player_data:
            return False
    
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
        
        # Se não há mais jogadores, marcar para limpeza
        if len(self.players) == 0:
            return True
        
        # Verificar se há um vencedor
        alive_players = [p for p in self.players if not self.player_data[p].get('dead', False)]
        if len(alive_players) == 1:
            return alive_players[0]  # Retorna o username do vencedor
        
        # Se era o turno do jogador que saiu, passar para o próximo
        if username in self.players:
            current_index = self.players.index(username)
            if current_index >= 0 and self.current_turn == current_index:
                self.next_turn()
        
        return True
    
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
            'prophet_curse': 1  # Adicionar limite para a habilidade do Profeta
        }

    def use_action(self, username, action):
        """Registra que uma ação foi usada"""
        if username not in self.turn_actions_used:
            self.turn_actions_used[username] = {}
        
        if action not in self.turn_actions_used[username]:
            self.turn_actions_used[username][action] = 0
        
        self.turn_actions_used[username][action] += 1
        
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
        
        self.time_cycle += 1
        if self.time_cycle % 24 == 0:
            self.time_of_day = "night" if self.time_of_day == "day" else "day"
            if self.time_of_day == "day":
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
        if position_type in ['attack', 'defense']:
            if card_to_play.get('type') != 'creature':
                return {'success': False, 'message': 'Apenas criaturas podem ser colocadas em bases de ataque ou defesa'}
        
        elif position_type == 'equipment':
            valid_equipment_types = {
                'weapon': ['weapon'],
                'helmet': ['armor'],
                'armor': ['armor'],
                'boots': ['armor'],
                'mount': ['creature']
            }
            
            slot_name = position_index
            if slot_name not in valid_equipment_types:
                return {'success': False, 'message': 'Slot de equipamento inválido'}
            
            if card_to_play.get('type') not in valid_equipment_types[slot_name]:
                return {'success': False, 'message': f'Esta carta não pode ser equipada em {slot_name}'}
            
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
            else:
                if position_index >= len(player['defense_bases']):
                    return {'success': False, 'message': 'Posição de defesa inválida'}
                if player['defense_bases'][position_index] is not None:
                    return {'success': False, 'message': 'Posição de defesa ocupada'}
                player['defense_bases'][position_index] = card_to_play
        
        elif position_type == 'equipment':
            player['equipment'][position_index] = card_to_play
        
        self.use_action(username, 'play')
        return {'success': True, 'card': card_to_play}
    
    def attack(self, username, target_username):
        """Ataca outro jogador com verificação de primeira rodada"""
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
                damage_log.append("✨ Talismã da Imortalidade salvou o jogador!")
                damage_to_player = 0
            else:
                defender['life'] -= remaining_damage
                damage_log.append(f"⚔️ Jogador recebeu {remaining_damage} de dano direto")
                
                if defender['life'] <= 0:
                    player_killed = True
                    self.process_player_death(target_username)
                    damage_log.append(f"💀 {defender['name']} foi derrotado!")
        
        self.use_action(username, 'attack')
        
        result = {
            'success': True,
            'total_attack': attack_power,
            'damage_absorbed': attack_power - remaining_damage,
            'damage_to_player': damage_to_player,
            'attacker': username,
            'attacker_name': attacker['name'],
            'target': target_username,
            'target_name': defender['name'],
            'target_life': defender['life'] if defender['life'] > 0 else 0,
            'cards_destroyed': cards_destroyed,
            'cards_damaged': cards_damaged,
            'player_killed': player_killed,
            'log': damage_log
        }
        
        return result
    
    def process_player_death(self, username):
        """Processa a morte de um jogador"""
        
        player = self.player_data[username]
        
        player['dead'] = True
        player['observer'] = True
        player['life'] = 0
        
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
        """Verifica se há um vencedor"""
        alive_players = []
        for username in self.players:
            if self.player_data[username]['life'] > 0 and not self.player_data[username].get('dead', False):
                alive_players.append(username)
        
        if len(alive_players) == 1:
            return alive_players[0]
        return None
    
    def apply_day_effects(self):
        """Aplica efeitos do dia (zumbis e vampiros morrem)"""
        for username in self.players:
            player = self.player_data[username]
            for i, card in enumerate(player['defense_bases']):
                if card and card.get('dies_daylight'):
                    has_protection = False
                    if player['equipment']['helmet'] and player['equipment']['helmet']['id'] == 'capacete_trevas':
                        has_protection = True
                    
                    if not has_protection:
                        self.graveyard.append(card)
                        player['defense_bases'][i] = None
            
            for i, card in enumerate(player['attack_bases']):
                if card and card.get('dies_daylight'):
                    has_protection = False
                    if player['equipment']['helmet'] and player['equipment']['helmet']['id'] == 'capacete_trevas':
                        has_protection = True
                    
                    if not has_protection:
                        self.graveyard.append(card)
                        player['attack_bases'][i] = None
    
    def swap_positions(self, username, pos1_type, pos1_index, pos2_type, pos2_index):
        """Troca duas cartas de posição"""
        if not self.can_act(username, 'swap'):
            return {'success': False, 'message': 'Você já realizou uma troca neste turno'}
        
        player = self.player_data[username]
        
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
        
        self.use_action(username, 'swap')
        
        return {
            'success': True,
            'swapped': True,
            'message': 'Cartas trocadas com sucesso'
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
        if item_card.get('protection'):
            target_creature['life'] = target_creature.get('life', 0) + item_card['protection']
        if item_card.get('life'):
            target_creature['life'] = target_creature.get('life', 0) + item_card['life']
        
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
        
        # Feitiço volta para o deck (embaixo)
        self.deck.append(spell_card)
        
        self.use_action(username, 'spell')
        
        return {
            'success': True,
            'spell': spell_card,
            'effect': result,
            'caster_type': caster_type
        }
    def apply_spell_effect(self, spell, caster_username, target_username=None, target_card_id=None, caster_type=None):
        """Aplica o efeito específico do feitiço"""
        spell_id = spell['id']
        caster = self.player_data[caster_username]
        
        # Se for Rei Mago ou Mago Negro e não tiver alvo definido para alguns feitiços
        if caster_type in ['rei_mago', 'mago_negro'] and not target_username:
            # Para feitiços que precisam de alvo, retornar erro
            if spell_id in ['feitico_cortes', 'feitico_troca', 'feitico_capitalista', 'feitico_cura']:
                return {'type': 'need_target', 'message': 'Este feitiço requer um alvo'}
        
        # Aplicar efeitos específicos
        if spell_id == 'feitico_cortes':
            # Aumenta ataque de um monstro
            if target_card_id:
                for player_uname in self.players:
                    for base in ['attack_bases', 'defense_bases']:
                        for card in self.player_data[player_uname][base]:
                            if card and card['instance_id'] == target_card_id:
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
                    # Trocar uma carta aleatória
                    import random
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

    def prophet_curse(self, username, target_player_id, target_card_id):
        """Aplica a maldição do Profeta - carta morre em 2 rodadas"""
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
                if card and card['id'] == 'profeta':
                    has_prophet = True
                    prophet_card = card
                    prophet_location = (base_type, i)
                    break
            if has_prophet:
                break
        
        if not has_prophet:
            return {'success': False, 'message': 'Você precisa ter um Profeta em campo'}
        
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
            'turns_remaining': 2,  # 2 rodadas completas (todos jogam 2 vezes)
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
        
        self.use_action(username, 'prophet_curse')
        
        return {
            'success': True,
            'message': f'🔮 Maldição do Profeta aplicada! {target_card["name"]} será destruído em 2 rodadas',
            'target_card': target_card['name'],
            'target_player': target_player['name']
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

# Rotas da aplicação
@app.route('/')
def index():
    username = get_current_user()
    if username:
        accounts = load_accounts()
        current_game = accounts.get(username, {}).get('current_game')
        if current_game and current_game in games:
            return render_template('game.html', game_id=current_game, username=username)
    else:
        return render_template('auth.html')
    return render_template('index.html')
@app.route('/rules')
def rules(): return render_template('rules.html')

@app.route('/story')
@login_required
def story(cache): return render_template('story.html')

@app.route('/game/<game_id>')
@login_required
def game(username, game_id):
    if game_id not in games:
        return redirect("/")

    update_user_game(username, game_id)
    
    return render_template('game.html', game_id=game_id, username=username)

@app.route('/spectate/<game_id>')
@login_required
def spectate_game(username, game_id):
    if game_id not in games:
        return redirect("/")
    
    # Não atualiza current_game para espectadores (opcional)
    # update_user_game(username, game_id)
    
    return render_template('spectate.html', game_id=game_id, username=username)

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
def cleanup_games(): return jsonify({'success': True})

# Login
@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username', '').strip().lower()
    password = data.get('password', '').strip()
    
    if not username or not password: return jsonify({'success': False, 'message': 'Usuário e senha obrigatórios'})
    if len(username) < 3 or len(username) > 20: return jsonify({'success': False, 'message': 'Usuário deve ter entre 3 e 20 caracteres'})
    if len(password) < 4: return jsonify({'success': False, 'message': 'Senha deve ter pelo menos 4 caracteres'})
    
    accounts = load_accounts()
    
    if username in accounts: return jsonify({'success': False, 'message': 'Usuário já existe'})
    
    # Criar nova conta
    accounts[username] = {
        'password': hash_password(password),
        'created_at': datetime.utcnow().isoformat(),
        'current_game': None  # Nenhum jogo ativo
    }
    
    save_accounts(accounts)
    
    # Criar token
    token = create_token(username)
    
    response = jsonify({'success': True, 'username': username})
    response.set_cookie(
        'auth_token',
        token,
        httponly=True,
        secure=True,  # True em produção com HTTPS
        samesite='Lax',
        max_age=app.config['JWT_EXPIRATION_HOURS'] * 3600
    )
    
    return response

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username', '').strip().lower()
    password = data.get('password', '').strip()
    
    if not username or not password: return jsonify({'success': False, 'message': 'Usuário e senha obrigatórios'})
    
    accounts = load_accounts()
    
    if username not in accounts: return jsonify({'success': False, 'message': 'Usuário ou senha inválidos'})
    if not verify_password(password, accounts[username]['password']): return jsonify({'success': False, 'message': 'Usuário ou senha inválidos'})
    
    # Criar token
    token = create_token(username)
    
    response = jsonify({
        'success': True,
        'username': username,
        'current_game': accounts[username].get('current_game')
    })
    
    response.set_cookie(
        'auth_token',
        token,
        httponly=True,
        secure=True,  # True em produção com HTTPS
        samesite='Lax',
        max_age=app.config['JWT_EXPIRATION_HOURS'] * 3600
    )
    
    return response

@app.route('/api/logout', methods=['POST'])
def logout():
    response = jsonify({'success': True})
    response.delete_cookie('auth_token')
    return response

@app.route('/api/check-auth')
def check_auth():
    username = get_current_user()
    
    if not username:
        return jsonify({'authenticated': False})
    
    accounts = load_accounts()
    current_game = accounts.get(username, {}).get('current_game')
    
    # Verificar se o jogo ainda existe
    if current_game and current_game in games:
        return jsonify({
            'authenticated': True,
            'username': username,
            'current_game': current_game,
            'game_exists': True
        })
    else:
        # Se o jogo não existe mais, limpar da conta
        if current_game and username in accounts:
            accounts[username]['current_game'] = None
            save_accounts(accounts)
        
        return jsonify({
            'authenticated': True,
            'username': username,
            'current_game': None,
            'game_exists': False
        })

# Socket.IO events
@socketio.on('connect')
def handle_connect(): pass

@socketio.on('disconnect')
def handle_disconnect():
    # Encontrar jogo e jogador
    for game_id, game in games.items():
        username = game.get_player_by_socket(request.sid)
        if username:
            # Remover mapeamento socket
            if request.sid in game.socket_to_username:
                del game.socket_to_username[request.sid]
            
            # Não remover o jogador automaticamente, apenas marcar como offline
            # O jogador pode reconectar depois
            emit('player_disconnected', {
                'username': username
            }, room=game_id)
            break

@socketio.on('join_game')
def handle_join_game(data):
    game_id = data['game_id']
    
    # Obter username do token
    username = get_current_user()
    if not username:
        emit('error', {'message': 'Usuário não autenticado'})
        return
    
    if game_id not in games:
        emit('error', {'message': 'Jogo não encontrado'})
        return
    
    game = games[game_id]
    
    if game.started:
        emit('error', {'message': 'O jogo já começou'})
        return
    
    if game.add_player(request.sid, username):
        join_room(game_id)
        
        # Atualizar jogo atual na conta
        update_user_game(username, game_id)
        
        # Lista de jogadores (usernames)
        players_list = [{'username': p, 'name': game.player_data[p]['name']} for p in game.players]
        
        emit('player_joined', {
            'username': username,
            'players': players_list
        }, room=game_id)
    else:
        emit('error', {'message': 'Não foi possível entrar no jogo'})

@socketio.on('leave_game')
def handle_leave_game(data):
    """Jogador sai voluntariamente do jogo"""
    game_id = data['game_id']
    
    # Obter username do token
    username = get_current_user()
    if not username:
        emit('error', {'message': 'Usuário não autenticado'})
        return
    
    if game_id not in games:
        emit('error', {'message': 'Jogo não encontrado'})
        return
    
    game = games[game_id]
    
    if username not in game.player_data:
        emit('error', {'message': 'Jogador não encontrado'})
        return
    
    # Remover jogador
    result = game.remove_player(username)
    
    # Limpar jogo atual da conta do usuário
    accounts = load_accounts()
    if username in accounts and accounts[username].get('current_game') == game_id:
        accounts[username]['current_game'] = None
        save_accounts(accounts)
    
    # Notificar todos os jogadores
    emit('player_left', {
        'username': username,
        'message': f'{username} saiu do jogo'
    }, room=game_id)
    
    # Se result for um username, é o vencedor
    if isinstance(result, str):
        winner = result
        winner_name = game.player_data[winner]['name']
        emit('game_over', {
            'winner': winner,
            'winner_name': winner_name,
            'message': f'🏆 {winner_name} VENCEU O JOGO!'
        }, room=game_id)
    
    # Remover da sala
    leave_room(game_id)

@socketio.on('get_game_state')
def handle_get_game_state(data):
    game_id = data['game_id']
    
    if game_id not in games:
        emit('error', {'message': 'Jogo não encontrado'})
        return
    
    game = games[game_id]
    username = game.get_player_by_socket(request.sid)
    
    if not username:
        emit('error', {'message': 'Jogador não encontrado'})
        return
    
    # Determinar o jogador da vez
    current_turn_username = None
    if game.players and game.current_turn < len(game.players):
        current_turn_username = game.players[game.current_turn]
    
    # Verificar se é espectador
    is_spectator = game.player_data[username].get('spectator', False)
    
    # Filtrar informações para o jogador
    state = {
        'game_id': game_id,
        'started': game.started,
        'time_of_day': game.time_of_day,
        'time_cycle': game.time_cycle,
        'current_turn': current_turn_username,
        'players': {},
        'deck_count': len(game.deck),
        'graveyard_count': len(game.graveyard),
        'is_spectator': is_spectator,
        'spectators': []  # Lista de espectadores
    }
    
    # Coletar lista de espectadores
    for uname, data in game.player_data.items():
        if data.get('spectator', False) and uname != username:
            state['spectators'].append({
                'username': uname,
                'name': data['name']
            })
    
    # Informações de todos os jogadores
    for uname in game.players:
        if uname in game.player_data:
            player_info = {
                'name': game.player_data[uname]['name'],
                'username': uname,
                'life': game.player_data[uname]['life'] if not game.player_data[uname].get('dead', False) else 0,
                'attack_bases': game.player_data[uname]['attack_bases'],
                'defense_bases': game.player_data[uname]['defense_bases'],
                'talisman_count': len(game.player_data[uname]['talismans']),
                'runes': game.player_data[uname]['runes'],
                'dead': game.player_data[uname].get('dead', False),
                'observer': game.player_data[uname].get('observer', False)
            }
            
            # Informações privadas apenas para o próprio jogador (não para espectadores)
            if uname == username and not is_spectator and not player_info.get('dead', False):
                player_info['hand'] = game.player_data[uname]['hand']
                player_info['equipment'] = game.player_data[uname]['equipment']
                player_info['talismans'] = game.player_data[uname]['talismans']
            
            state['players'][uname] = player_info
    
    emit('game_state', state)

@socketio.on('get_graveyard')
def handle_get_graveyard(data):
    """Retorna lista de cartas no cemitério"""
    game_id = data['game_id']

    if game_id not in games:
        emit('error', {'message': 'Jogo não encontrado'})
        return
    
    game = games[game_id]
    username = game.get_player_by_socket(request.sid)
    
    if not username:
        emit('error', {'message': 'Jogador não encontrado'})
        return
    
    graveyard_cards = game.get_graveyard_cards()
    
    emit('graveyard_list', {
        'cards': graveyard_cards,
        'count': len(graveyard_cards)
    })

@socketio.on('get_spells')
def handle_get_spells(data):
    """Retorna lista de feitiços disponíveis para o jogador"""
    game_id = data['game_id']
    
    if game_id not in games:
        emit('error', {'message': 'Jogo não encontrado'})
        return
    
    game = games[game_id]
    username = game.get_player_by_socket(request.sid)
    
    if not username:
        emit('error', {'message': 'Jogador não encontrado'})
        return
    
    spells_data = game.get_available_spells(username)
    
    emit('spells_list', spells_data)

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

@socketio.on('spectate_game')
def handle_spectate_game(data):
    """Entrar como espectador em um jogo em andamento"""
    game_id = data['game_id']
    
    # Obter username do token
    username = get_current_user()
    if not username:
        emit('error', {'message': 'Usuário não autenticado'})
        return
    
    if game_id not in games:
        emit('error', {'message': 'Jogo não encontrado'})
        return
    
    game = games[game_id]
    
    # Verificar se já está como jogador
    if username in game.players:
        # Já é jogador, fazer reconnect normal
        socketio.emit('reconnect_game', {'game_id': game_id})
        return
    
    # Verificar se já é espectador
    if username in game.player_data and game.player_data[username].get('spectator', False):
        # Atualizar socket
        game.reconnect_player(request.sid, username)
        join_room(game_id)
        emit('spectate_success', {
            'username': username,
            'game_started': game.started,
            'spectator': True
        })
        return
    
    # Adicionar como novo espectador
    success, message = game.add_spectator(request.sid, username)
    
    if success:
        join_room(game_id)
        
        # Atualizar jogo atual na conta (opcional para espectadores)
        update_user_game(username, game_id)
        
        # Lista de jogadores para o espectador
        players_list = [{'username': p, 'name': game.player_data[p]['name']} for p in game.players]
        
        # Notificar todos que um espectador entrou
        emit('spectator_joined', {
            'username': username,
            'players': players_list,
            'spectator': True
        }, room=game_id)
        
        # Notificar o espectador
        emit('spectate_success', {
            'username': username,
            'game_started': game.started,
            'spectator': True
        })
    else:
        emit('error', {'message': message})

@socketio.on('reconnect_game')
def handle_reconnect_game(data):
    """Gerencia reconexão de jogadores"""
    game_id = data['game_id']
    
    # Obter username do token
    username = get_current_user()
    if not username:
        emit('error', {'message': 'Usuário não autenticado'})
        return

    if game_id not in games:
        emit('error', {'message': 'Jogo não encontrado'})
        return
    
    game = games[game_id]
    
    # Tentar reconectar
    result = game.reconnect_player(request.sid, username)
    
    if result['success']:
        # Adicionar à sala
        join_room(game_id)
        
        # Atualizar jogo atual na conta
        update_user_game(username, game_id)
        
        # Atualizar lista de jogadores
        players_list = [{'username': p, 'name': game.player_data[p]['name']} for p in game.players]
        
        # Notificar todos
        emit('player_joined', {
            'username': username,
            'players': players_list,
            'reconnected': True
        }, room=game_id)
        
        # Notificar o jogador reconectado
        emit('reconnect_success', {
            'username': username,
            'game_started': game.started
        })
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
    
    # Verificar autenticação
    username = get_current_user()
    if not username:
        emit('error', {'message': 'Usuário não autenticado'})
        return
    
    if game_id not in games:
        emit('error', {'message': 'Jogo não encontrado'})
        return
    
    game = games[game_id]
    
    # Verificar se o socket corresponde ao username
    socket_username = game.get_player_by_socket(request.sid)
    if socket_username != username:
        emit('error', {'message': 'Sessão inválida'})
        return
    
    if not game.started:
        emit('error', {'message': 'O jogo ainda não começou'})
        return
    
    if username not in game.player_data:
        emit('error', {'message': 'Jogador não encontrado'})
        return
    
    if game.player_data[username].get('dead', False):
        emit('error', {'message': 'Você está morto e não pode mais realizar ações.'})
        return
    
    if game.players[game.current_turn] != username:
        emit('error', {'message': 'Não é o seu turno'})
        return

    result = None
    player_name = username
    timestamp = time.strftime('%H:%M:%S')
    
    try:
        if action == 'draw':
            result = game.draw_card(player_name)
            if result and result.get('success'):
                log_message = f"📥 {player_name} comprou uma carta"
                
        elif action == 'play_card':
            result = game.play_card(player_name, params['card_id'], params['position_type'], params['position_index'])
            if result and result.get('success'):
                card_name = result.get('card', {}).get('name', 'uma carta')
                log_message = f"🎴 {player_name} jogou {card_name}"
                
        elif action == 'attack':
            result = game.attack(player_name, params['target_id'])
            if result and result.get('success'):
                target_name = result.get('target_name', 'um oponente')
                damage = result.get('damage_to_player', 0)
                log_message = f"⚔️ {player_name} atacou {target_name} causando {damage} de dano"
                
        elif action == 'equip_item':
            result = game.equip_item_to_creature(player_name, params['item_card_id'], params['creature_card_id'])
            if result and result.get('success'):
                log_message = f"🔰 {player_name} equipou {result.get('item', 'um item')} em {result.get('creature', 'uma criatura')}"
                
        elif action == 'cast_spell':
            result = game.cast_spell(player_name, params['spell_id'], params.get('target_player_id'), params.get('target_card_id'))
            if result and result.get('success'):
                spell_name = result.get('spell', {}).get('name', 'um feitiço')
                log_message = f"✨ {player_name} usou {spell_name}"
                
        elif action == 'ritual':
            result = game.perform_ritual(player_name, params['ritual_id'], params.get('target_player_id'))
            if result and result.get('success'):
                log_message = f"📿 {player_name} realizou {result.get('message', 'um ritual')}"
                
        elif action == 'swap_positions':
            result = game.swap_positions(
                player_name, 
                params['pos1_type'], 
                params['pos1_index'], 
                params['pos2_type'], 
                params['pos2_index']
            )
            if result and result.get('success'):
                log_message = f"🔄 {player_name} trocou posições das cartas"
                
        elif action == 'move_card':
            result = game.move_card(player_name, params['from_type'], params['from_index'], params['to_type'], params['to_index'])
            if result and result.get('success'):
                log_message = f"↔️ {player_name} moveu uma carta"

        elif action == 'prophet_curse':
            result = game.prophet_curse(
                player_name, 
                params['target_player_id'], 
                params['target_card_id']
            )
            if result and result.get('success'):
                log_message = f"🔮 {player_name} amaldiçoou {result.get('target_card', 'uma carta')} de {result.get('target_player', 'um oponente')} (morre em 2 rodadas)"

        elif action == 'revive':
            # Verificar se params['card_id'] existe
            card_id = params.get('card_id') or params.get('target_card_id')
            if not card_id:
                emit('action_error', {
                    'message': 'ID da carta não fornecido',
                    'player_name': player_name,
                    'action': action,
                    'timestamp': timestamp
                })
                return
            
            result = game.revive_from_graveyard(player_name, card_id)
            if result and result.get('success'):
                card_name = result.get('card', {}).get('name', 'uma carta')
                log_message = f"🔄 {player_name} reviveu {card_name} do cemitério"

        elif action == 'flip_card':
            result = game.flip_card(player_name, params['position_type'], params['position_index'])
            if result and result.get('success'):
                log_message = f"🔄 {player_name} desvirou uma carta"
                
        elif action == 'oracle':
            result = game.perform_oracle(player_name, params['target_id'])
            if result and result.get('success'):
                log_message = f"👁️ {player_name} realizou um oráculo"

        elif action == 'end_turn':
            game.next_turn()
            next_player_name = game.players[game.current_turn]
            next_player_name = game.player_data[next_player_name]['name']
            result = {'success': True, 'next_turn': next_player_name}
            log_message = f"⏰ {player_name} finalizou o turno (próximo: {next_player_name})"
        
        if result and result.get('success'):
            # Registrar ação para primeira rodada (exceto end_turn)
            first_round_ended = False
            if action != 'end_turn':
                first_round_ended = game.register_action(player_name, action)
            
            if first_round_ended:
                result['first_round_ended'] = True
                # Notificar todos que a primeira rodada terminou
                emit('first_round_ended', {
                    'message': '🎉 PRIMEIRA RODADA CONCLUÍDA! Todos já jogaram, ataques liberados!'
                }, room=game_id)
            
            # Emitir ação com todas as informações para o log
            emit('action_success', {
                'player_id': player_name,
                'player_name': player_name,
                'action': action,
                'result': result,
                'log_message': log_message,
                'timestamp': timestamp
            }, room=game_id)
            
            winner = game.check_winner()
            if winner:
                winner_name = game.player_data[winner]['name']
                emit('game_over', {
                    'winner': winner,
                    'winner_name': winner_name,
                    'message': f'🏆 {winner_name} VENCEU O JOGO!'
                }, room=game_id)
        else:
            error_msg = result['message'] if result else 'Ação inválida'
            emit('action_error', {
                'message': error_msg,
                'player_name': player_name,
                'action': action,
                'timestamp': timestamp
            })
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        emit('action_error', {
            'message': f'Erro interno: {str(e)}',
            'player_name': player_name,
            'action': action,
            'timestamp': timestamp
        })

class AdminShell(cmd.Cmd):
    intro = """╔══════════════════════════════════════════════════════════════╗\n║                 TWILIGHT BATTLE - ADMIN SHELL                ║\n╠══════════════════════════════════════════════════════════════╣\n║ Comandos disponíveis:                                        ║\n║  give [jogador] [id_carta] [quantidade] - Dar cartas         ║\n║  take [jogador] [id_carta] [quantidade] - Remover cartas     ║\n║  info [jogador] - Info do jogador                            ║\n║  info game [game_id] - Info do jogo                          ║\n║  damage [jogador] [quantidade] - Causar dano                 ║\n║  heal [jogador] [quantidade] - Curar                         ║\n║  list games - Listar todos os jogos                          ║\n║  list players - Listar todos os jogadores online             ║\n║  kill [jogador] - Mata um jogador                            ║\n║  revive [jogador] - Revive um jogador                        ║\n║  addcard [jogador] [id_carta] [quantidade] - Adicionar carta ║\n║  removecard [jogador] [id_carta] [quantidade] - Remover carta║\n║  reset - Resetar todos os jogos                              ║\n║  exit/sair - Sair do admin shell                             ║\n╚══════════════════════════════════════════════════════════════╝\n"""
    prompt = '⚔️ admin> '
    
    def get_player_game(self, username):
        """Retorna o jogo atual de um jogador"""
        accounts = load_accounts()
        if username not in accounts:
            return None, "Jogador não encontrado no accounts.json"
        
        game_id = accounts[username].get('current_game')
        if not game_id:
            return None, f"Jogador {username} não está em nenhum jogo"
        
        if game_id not in games:
            # Limpar referência inválida
            accounts[username]['current_game'] = None
            save_accounts(accounts)
            return None, f"Jogo {game_id} não existe mais (referência removida)"
        
        return games[game_id], None
    
    def find_card_by_id(self, card_id):
        """Encontra uma carta pelo ID"""
        for cid, card_info in CARDS.items():
            if cid == card_id or card_info['name'].lower() == card_id.lower():
                return cid, card_info
        return None, None
    
    def do_give(self, arg):
        """give [jogador] [id_carta] [quantidade] - Dar cartas para um jogador"""
        args = shlex.split(arg)
        if len(args) < 2:
            print("❌ Uso: give [jogador] [id_carta] [quantidade]")
            return
        
        username = args[0].lower()
        card_id = args[1].lower()
        quantidade = int(args[2]) if len(args) > 2 else 1
        
        # Verificar se carta existe
        cid, card_info = self.find_card_by_id(card_id)
        if not cid:
            print(f"❌ Carta '{card_id}' não encontrada")
            return
        
        # Encontrar jogo do jogador
        game, error = self.get_player_game(username)
        if error:
            print(f"❌ {error}")
            return
        
        if username not in game.player_data:
            print(f"❌ Jogador {username} não está neste jogo")
            return
        
        # Adicionar cartas
        player = game.player_data[username]
        cards_added = []
        
        for i in range(quantidade):
            new_card = card_info.copy()
            new_card['instance_id'] = str(uuid.uuid4())[:8]
            player['hand'].append(new_card)
            cards_added.append(new_card['name'])
        
        print(f"✅ {quantidade}x {card_info['name']} adicionada(s) à mão de {username}")
        
        # Notificar jogador via socket
        socketio.emit('admin_action', {
            'type': 'cards_added',
            'cards': cards_added,
            'message': f'Admin adicionou {quantidade}x {card_info["name"]} à sua mão'
        }, room=game.game_id)
    
    def do_take(self, arg):
        """take [jogador] [id_carta] [quantidade] - Remover cartas de um jogador"""
        args = shlex.split(arg)
        if len(args) < 2:
            print("❌ Uso: take [jogador] [id_carta] [quantidade]")
            return
        
        username = args[0].lower()
        card_id = args[1].lower()
        quantidade = int(args[2]) if len(args) > 2 else 1
        
        # Encontrar jogo do jogador
        game, error = self.get_player_game(username)
        if error:
            print(f"❌ {error}")
            return
        
        if username not in game.player_data:
            print(f"❌ Jogador {username} não está neste jogo")
            return
        
        player = game.player_data[username]
        cards_removed = []
        cards_to_remove = []
        
        # Encontrar cartas para remover
        for card in player['hand']:
            if card['id'] == card_id or card['name'].lower() == card_id.lower():
                cards_to_remove.append(card)
                if len(cards_to_remove) >= quantidade:
                    break
        
        if not cards_to_remove:
            print(f"❌ Nenhuma carta '{card_id}' encontrada na mão de {username}")
            return
        
        # Remover cartas
        for card in cards_to_remove:
            player['hand'].remove(card)
            cards_removed.append(card['name'])
        
        print(f"✅ {len(cards_removed)}x {card_id} removida(s) de {username}")
        
        # Notificar jogador
        socketio.emit('admin_action', {
            'type': 'cards_removed',
            'cards': cards_removed,
            'message': f'Admin removeu {len(cards_removed)}x {card_id} da sua mão'
        }, room=game.game_id)
    
    def do_info(self, arg):
        """info [jogador] - Info do jogador | info game [game_id] - Info do jogo"""
        args = shlex.split(arg)
        if not args:
            print("❌ Uso: info [jogador] ou info game [game_id]")
            return
        
        if args[0] == 'game' and len(args) > 1:
            # Info do jogo
            game_id = args[1]
            if game_id not in games:
                print(f"❌ Jogo {game_id} não encontrado")
                return
            
            game = games[game_id]
            print(f"\n📊 JOGO: {game_id}")
            print(f"   Status: {'Em andamento' if game.started else 'Aguardando'}")
            print(f"   Turno: {game.time_of_day.upper()} (ciclo {game.time_cycle})")
            print(f"   Jogador da vez: {game.players[game.current_turn] if game.players else 'Nenhum'}")
            print(f"   Jogadores: {len(game.players)}/{game.max_players}")
            print(f"   Cartas no monte: {len(game.deck)}")
            print(f"   Cartas no cemitério: {len(game.graveyard)}")
            print("\n   👥 Jogadores:")
            
            for username in game.players:
                player = game.player_data[username]
                status = "💀 MORTO" if player.get('dead') else "✨ VIVO"
                print(f"     • {username} - {player['name']} [{status}]")
                print(f"        Vida: {player['life']} | Mão: {len(player['hand'])} cartas")
                print(f"        Ataque: {sum(1 for c in player['attack_bases'] if c)} criaturas")
                print(f"        Defesa: {sum(1 for c in player['defense_bases'] if c)} criaturas")
        else:
            # Info do jogador
            username = args[0].lower()
            
            # Verificar accounts
            accounts = load_accounts()
            if username not in accounts:
                print(f"❌ Jogador {username} não encontrado no accounts.json")
                return
            
            print(f"\n👤 JOGADOR: {username}")
            print(f"   Conta criada: {accounts[username].get('created_at', 'Desconhecida')}")
            
            # Verificar jogo atual
            game_id = accounts[username].get('current_game')
            if game_id:
                print(f"   Jogo atual: {game_id}")
                
                if game_id in games:
                    game = games[game_id]
                    if username in game.player_data:
                        player = game.player_data[username]
                        status = "💀 MORTO" if player.get('dead') else "✨ VIVO"
                        print(f"   Status no jogo: {status}")
                        print(f"   Vida: {player['life']}")
                        print(f"   Cartas na mão: {len(player['hand'])}")
                        
                        if player['hand']:
                            print("\n   📚 MÃO:")
                            for card in player['hand']:
                                card_type = card.get('type', 'desconhecido')
                                card_atk = card.get('attack', '')
                                card_life = card.get('life', '')
                                stats = f" [{card_atk}⚔️/{card_life}❤️]" if card_atk and card_life else ""
                                print(f"     • {card['name']} ({card_type}){stats}")
                        
                        print("\n   ⚔️ ATAQUE:")
                        for i, card in enumerate(player['attack_bases']):
                            if card:
                                print(f"     [{i}] {card['name']} - {card.get('attack', 0)}⚔️")
                            else:
                                print(f"     [{i}] ⬜ Vazio")
                        
                        print("\n   🛡️ DEFESA:")
                        for i, card in enumerate(player['defense_bases']):
                            if card:
                                print(f"     [{i}] {card['name']} - {card.get('life', 0)}❤️")
                            else:
                                print(f"     [{i}] ⬜ Vazio")
                    else:
                        print(f"   ⚠️ Jogador não está na partida {game_id}")
                else:
                    print(f"   ⚠️ Jogo {game_id} não existe mais")
            else:
                print(f"   ⚠️ Jogador não está em nenhum jogo")
    
    def do_damage(self, arg):
        """damage [jogador] [quantidade] - Causar dano a um jogador"""
        args = shlex.split(arg)
        if len(args) < 2:
            print("❌ Uso: damage [jogador] [quantidade]")
            return
        
        username = args[0].lower()
        try:
            dano = int(args[1])
        except ValueError:
            print("❌ Quantidade deve ser um número")
            return
        
        game, error = self.get_player_game(username)
        if error:
            print(f"❌ {error}")
            return
        
        if username not in game.player_data:
            print(f"❌ Jogador {username} não está neste jogo")
            return
        
        player = game.player_data[username]
        vida_antiga = player['life']
        player['life'] = max(0, player['life'] - dano)
        
        if player['life'] <= 0:
            game.process_player_death(username)
            print(f"💀 {username} MORREU com {dano} de dano!")
        else:
            print(f"💔 {username} perdeu {dano} de vida: {vida_antiga} → {player['life']}")
        
        # Notificar todos
        socketio.emit('admin_action', {
            'type': 'damage',
            'target': username,
            'damage': dano,
            'new_life': player['life']
        }, room=game.game_id)
    
    def do_heal(self, arg):
        """heal [jogador] [quantidade] - Curar um jogador"""
        args = shlex.split(arg)
        if len(args) < 2:
            print("❌ Uso: heal [jogador] [quantidade]")
            return
        
        username = args[0].lower()
        try:
            cura = int(args[1])
        except ValueError:
            print("❌ Quantidade deve ser um número")
            return
        
        game, error = self.get_player_game(username)
        if error:
            print(f"❌ {error}")
            return
        
        if username not in game.player_data:
            print(f"❌ Jogador {username} não está neste jogo")
            return
        
        player = game.player_data[username]
        vida_antiga = player['life']
        player['life'] += cura
        
        print(f"💚 {username} recebeu {cura} de cura: {vida_antiga} → {player['life']}")
        
        socketio.emit('admin_action', {
            'type': 'heal',
            'target': username,
            'heal': cura,
            'new_life': player['life']
        }, room=game.game_id)
    
    def do_kill(self, arg):
        """kill [jogador] - Mata um jogador instantaneamente"""
        username = arg.strip().lower()
        if not username:
            print("❌ Uso: kill [jogador]")
            return
        
        game, error = self.get_player_game(username)
        if error:
            print(f"❌ {error}")
            return
        
        if username not in game.player_data:
            print(f"❌ Jogador {username} não está neste jogo")
            return
        
        game.process_player_death(username)
        print(f"💀 {username} foi morto pelo admin!")
        
        socketio.emit('admin_action', {
            'type': 'kill',
            'target': username,
            'message': f'☠️ Admin matou {username}!'
        }, room=game.game_id)
    
    def do_revive(self, arg):
        """revive [jogador] - Revive um jogador morto"""
        username = arg.strip().lower()
        if not username:
            print("❌ Uso: revive [jogador]")
            return
        
        game, error = self.get_player_game(username)
        if error:
            print(f"❌ {error}")
            return
        
        if username not in game.player_data:
            print(f"❌ Jogador {username} não está neste jogo")
            return
        
        player = game.player_data[username]
        if not player.get('dead', False):
            print(f"⚠️ {username} não está morto")
            return
        
        player['dead'] = False
        player['observer'] = False
        player['life'] = 5000
        
        print(f"✨ {username} foi revivido pelo admin!")
        
        socketio.emit('admin_action', {
            'type': 'revive',
            'target': username,
            'message': f'✨ Admin reviveu {username}!'
        }, room=game.game_id)
    
    def do_addcard(self, arg):
        """addcard [jogador] [id_carta] [quantidade] - Adicionar carta à mão"""
        self.do_give(arg)
    
    def do_removecard(self, arg):
        """removecard [jogador] [id_carta] [quantidade] - Remover carta da mão"""
        self.do_take(arg)
    
    def do_toggle_time(self, arg):
        """toggle-time [game-id] - Muda o ciclo de dia/noite do jogo"""
        args = shlex.split(arg)
        if not args:
            print("❌ Uso: toggle-time [game-id]")
            return
        
        game_id = args[0]
        
        if game_id not in games:
            print(f"❌ Jogo {game_id} não encontrado")
            return
        
        game = games[game_id]
        
        # Alternar o ciclo
        old_time = game.time_of_day
        game.time_of_day = "night" if game.time_of_day == "day" else "day"
        
        print(f"🌓 Jogo {game_id}: {old_time.upper()} → {game.time_of_day.upper()}")
        
        # Aplicar efeitos do dia se mudou para dia
        if game.time_of_day == "day":
            game.apply_day_effects()
            print("   ⚰️ Efeitos do dia aplicados (zumbis e vampiros morreram)")
        
        # Notificar todos os jogadores
        socketio.emit('time_changed', {
            'type': 'time_change',
            'new_time': game.time_of_day,
            'old_time': old_time,
            'message': f'🌓 Admin alterou o ciclo: {old_time.upper()} → {game.time_of_day.upper()}'
        }, room=game_id)
        
        print(f"   ✅ Jogadores notificados")

    def do_list(self, arg):
        """list games - Listar jogos | list players - Listar jogadores online"""
        args = shlex.split(arg)
        if not args:
            print("❌ Uso: list games ou list players")
            return
        
        if args[0] == 'games':
            if not games:
                print("📭 Nenhum jogo ativo no momento")
                return
            
            print(f"\n🎮 JOGOS ATIVOS ({len(games)}):")
            for game_id, game in games.items():
                status = "▶️ EM ANDAMENTO" if game.started else "⏸️ AGUARDANDO"
                turno = f" | Turno: {game.players[game.current_turn]}" if game.players and game.started else ""
                print(f"  • {game_id}: {status} | {len(game.players)}/{game.max_players} jogadores{turno}")
        
        elif args[0] == 'players':
            accounts = load_accounts()
            online_players = []
            
            for username, data in accounts.items():
                game_id = data.get('current_game')
                if game_id and game_id in games:
                    online_players.append((username, game_id))
            
            if not online_players:
                print("📭 Nenhum jogador online no momento")
                return
            
            print(f"\n👥 JOGADORES ONLINE ({len(online_players)}):")
            for username, game_id in online_players:
                game = games[game_id]
                if username in game.player_data:
                    player = game.player_data[username]
                    status = "💀 MORTO" if player.get('dead') else "✨ VIVO"
                    vida = player['life']
                    print(f"  • {username} - Jogo: {game_id} [{status}] {vida}❤️")
                else:
                    print(f"  • {username} - Jogo: {game_id} [⚠️ não na partida]")
    
    def do_sync(self, arg):
        """sync [game-id] - Força sincronização do jogo para todos os jogadores na sala"""
        args = shlex.split(arg)
        if not args:
            print("❌ Uso: sync [game-id]")
            return
        
        game_id = args[0]
        
        if game_id not in games:
            print(f"❌ Jogo {game_id} não encontrado")
            return
        
        game = games[game_id]
        
        # Enviar estado atualizado para cada jogador na sala
        players_updated = 0
        for username in game.players:
            socket_id = game.get_socket_id(username)
            if socket_id and username in game.player_data:
                # Construir estado específico para cada jogador
                current_turn_username = None
                if game.players and game.current_turn < len(game.players):
                    current_turn_username = game.players[game.current_turn]
                
                state = {
                    'game_id': game_id,
                    'started': game.started,
                    'time_of_day': game.time_of_day,
                    'time_cycle': game.time_cycle,
                    'current_turn': current_turn_username,
                    'players': {},
                    'deck_count': len(game.deck),
                    'graveyard_count': len(game.graveyard),
                    'current_player_dead': game.player_data[username].get('dead', False)
                }
                
                # Informações de todos os jogadores
                for uname in game.players:
                    if uname in game.player_data:
                        player_info = {
                            'name': game.player_data[uname]['name'],
                            'username': uname,
                            'life': game.player_data[uname]['life'] if not game.player_data[uname].get('dead', False) else 0,
                            'attack_bases': game.player_data[uname]['attack_bases'],
                            'defense_bases': game.player_data[uname]['defense_bases'],
                            'talisman_count': len(game.player_data[uname]['talismans']),
                            'runes': game.player_data[uname]['runes'],
                            'dead': game.player_data[uname].get('dead', False),
                            'observer': game.player_data[uname].get('observer', False)
                        }
                        
                        # Informações privadas apenas para o próprio jogador
                        if uname == username and not player_info.get('dead', False):
                            player_info['hand'] = game.player_data[uname]['hand']
                            player_info['equipment'] = game.player_data[uname]['equipment']
                            player_info['talismans'] = game.player_data[uname]['talismans']
                        
                        state['players'][uname] = player_info
                
                # Enviar estado para o jogador específico
                socketio.emit('game_state', state, room=socket_id)
                players_updated += 1
        
        print(f"✅ Sincronização forçada para {players_updated} jogadores no jogo {game_id}")

    def do_reset(self, arg):
        """reset - Resetar todos os jogos (CUIDADO!)"""
        confirm = input("⚠️ Tem certeza que quer resetar TODOS os jogos? (s/N): ")
        if confirm.lower() == 's':
            games.clear()
            print("✅ Todos os jogos foram resetados")
    
    def do_exit(self, arg):
        """exit - Sair do admin shell"""
        print("👋 Até mais!")
        return True
    
    def do_sair(self, arg):
        """sair - Sair do admin shell"""
        return self.do_exit(arg)
    
    def default(self, line):
        print(f"❌ Comando desconhecido: {line}")
        print("Digite 'help' para ver os comandos disponíveis")

if __name__ == '__main__':
    def run():
        socketio.run(app, debug=False, port=5000)
        
    if len(sys.argv) > 1 and sys.argv[1] == "-x":
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
    
        AdminShell().cmdloop()
    else:
        run()