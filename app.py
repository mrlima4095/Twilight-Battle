from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO, emit, join_room, leave_room
import uuid
from game_logic import Game, Player, Card, TimeOfDay
import threading
import time
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = 'twilight_battle_secret'
socketio = SocketIO(app, cors_allowed_origins="*", ping_timeout=60, ping_interval=25)

# Armazenamento dos jogos
games = {}
waiting_players = {}

class GameRoom:
    def __init__(self, room_id):
        self.room_id = room_id
        self.game = Game()
        self.players = {}
        self.started = False
        self.max_players = 6
        self.current_turn = 0
        self.turn_timer = None
        
    def add_player(self, player_id, player_name):
        if len(self.players) < self.max_players and not self.started:
            player = Player(player_id, player_name)
            self.players[player_id] = player
            self.game.add_player(player)
            return True
        return False
    
    def remove_player(self, player_id):
        if player_id in self.players:
            del self.players[player_id]
            self.game.remove_player(player_id)
            
    def start_game(self):
        if len(self.players) >= 2 and not self.started:
            self.started = True
            self.game.initialize_game()
            self.current_turn = 0
            return True
        return False
    
    def next_turn(self):
        self.current_turn = (self.current_turn + 1) % len(self.players)
        self.game.update_time_of_day()
        return list(self.players.keys())[self.current_turn]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/rooms')
def get_rooms():
    available_rooms = []
    for room_id, room in games.items():
        if not room.started and len(room.players) < room.max_players:
            available_rooms.append({
                'id': room_id,
                'players': len(room.players),
                'max_players': room.max_players
            })
    return jsonify(available_rooms)

@app.route('/api/create_room', methods=['POST'])
def create_room():
    room_id = str(uuid.uuid4())[:8]
    games[room_id] = GameRoom(room_id)
    return jsonify({'room_id': room_id})

@socketio.on('connect')
def handle_connect():
    print(f'Cliente conectado: {request.sid}')

@socketio.on('disconnect')
def handle_disconnect():
    print(f'Cliente desconectado: {request.sid}')
    player_id = request.sid
    for room_id, room in list(games.items()):
        if player_id in room.players:
            room.remove_player(player_id)
            emit('player_left', {
                'player_id': player_id
            }, room=room_id)
            
            if len(room.players) == 0:
                if room.turn_timer:
                    room.turn_timer.cancel()
                del games[room_id]

@socketio.on('join')
def handle_join(data):
    room_id = data['room_id']
    player_name = data['player_name']
    player_id = request.sid
    
    print(f"Jogador {player_name} tentando entrar na sala {room_id}")
    
    if room_id in games:
        room = games[room_id]
        if room.add_player(player_id, player_name):
            join_room(room_id)
            
            # Prepara lista de jogadores para enviar
            players_list = []
            for pid, p in room.players.items():
                players_list.append({
                    'id': pid,
                    'name': p.name
                })
            
            emit('player_joined', {
                'player_id': player_id,
                'player_name': player_name,
                'players': players_list
            }, room=room_id)
            
            # Atualiza lista de jogadores para todos
            emit('update_players', {
                'players': players_list,
                'count': len(room.players)
            }, room=room_id)
        else:
            emit('join_error', {'message': 'Não foi possível entrar na sala'})

@socketio.on('start_game')
def handle_start_game(data):
    room_id = data['room_id']
    player_id = request.sid
    
    print(f"Tentativa de iniciar jogo na sala {room_id} pelo jogador {player_id}")
    
    if room_id in games:
        room = games[room_id]
        if player_id in room.players and room.start_game():
            # Distribui cartas iniciais
            for pid in room.players:
                player = room.players[pid]
                player.draw_initial_hand()
            
            # Prepara dados dos jogadores
            players_data = []
            for pid, p in room.players.items():
                players_data.append({
                    'id': pid,
                    'name': p.name,
                    'life': p.life
                })
            
            emit('game_started', {
                'players': players_data,
                'current_turn': list(room.players.keys())[room.current_turn],
                'time_of_day': room.game.time_of_day.value  # Usa .value para serializar
            }, room=room_id)
            
            # Inicia timer do turno
            start_turn_timer(room_id)

@socketio.on('play_card')
def handle_play_card(data):
    room_id = data['room_id']
    player_id = request.sid
    card_index = data['card_index']
    position = data['position']  # 'attack' ou 'defense'
    
    if room_id in games:
        room = games[room_id]
        if player_id == list(room.players.keys())[room.current_turn]:
            player = room.players[player_id]
            if player.play_card(card_index, position):
                emit('card_played', {
                    'player_id': player_id,
                    'card': player.field[-1].to_dict(),
                    'position': position
                }, room=room_id)
                
                # Verifica ações do turno
                player.actions_used['play_card'] = True
                check_turn_complete(room, player_id)

@socketio.on('attack')
def handle_attack(data):
    room_id = data['room_id']
    player_id = request.sid
    target_player_id = data['target_player_id']
    
    if room_id in games:
        room = games[room_id]
        if player_id == list(room.players.keys())[room.current_turn]:
            attacker = room.players[player_id]
            defender = room.players[target_player_id]
            
            # Calcula dano total dos atacantes
            total_attack = sum(card.attack for card in attacker.field if card.position == 'attack' and not card.tapped)
            
            # Marca cartas de ataque como usadas (viradas)
            for card in attacker.field:
                if card.position == 'attack' and not card.tapped:
                    card.tapped = True
            
            # Aplica dano na defesa do defensor
            damage_dealt = defender.take_damage(total_attack)
            
            emit('attack_result', {
                'attacker_id': player_id,
                'defender_id': target_player_id,
                'damage': damage_dealt,
                'defender_life': defender.life,
                'defender_field': [c.to_dict() for c in defender.field]
            }, room=room_id)
            
            # Verifica se jogador morreu
            if defender.life <= 0:
                emit('player_defeated', {
                    'player_id': target_player_id,
                    'player_name': defender.name
                }, room=room_id)
                room.remove_player(target_player_id)
                
                # Verifica se resta apenas um jogador
                if len(room.players) == 1:
                    winner = list(room.players.values())[0]
                    emit('game_over', {
                        'winner_id': list(room.players.keys())[0],
                        'winner_name': winner.name
                    }, room=room_id)
            
            attacker.actions_used['attack'] = True
            check_turn_complete(room, player_id)

@socketio.on('draw_card')
def handle_draw_card(data):
    room_id = data['room_id']
    player_id = request.sid
    
    if room_id in games:
        room = games[room_id]
        if player_id == list(room.players.keys())[room.current_turn]:
            player = room.players[player_id]
            if player.draw_card():
                emit('card_drawn', {
                    'player_id': player_id,
                    'card': player.hand[-1].to_dict()
                }, room=room_id)
                
                player.actions_used['draw'] = True
                check_turn_complete(room, player_id)

@socketio.on('end_turn')
def handle_end_turn(data):
    room_id = data['room_id']
    player_id = request.sid
    
    if room_id in games:
        room = games[room_id]
        if player_id == list(room.players.keys())[room.current_turn]:
            next_player_id = room.next_turn()
            
            # Reset ações do próximo jogador
            for player in room.players.values():
                player.reset_actions()
            
            emit('turn_changed', {
                'previous_player': player_id,
                'current_player': next_player_id,
                'time_of_day': room.game.time_of_day.value
            }, room=room_id)
            
            start_turn_timer(room_id)

def start_turn_timer(room_id):
    """Timer de 60 segundos por turno"""
    if room_id in games:
        room = games[room_id]
        
        def timeout():
            if room_id in games and room.started:
                current_player = list(room.players.keys())[room.current_turn]
                socketio.emit('turn_timeout', {
                    'player_id': current_player
                }, room=room_id)
                handle_end_turn({'room_id': room_id})
        
        if room.turn_timer:
            room.turn_timer.cancel()
        room.turn_timer = threading.Timer(60.0, timeout)
        room.turn_timer.start()

def check_turn_complete(room, player_id):
    """Verifica se o jogador já usou todas as ações disponíveis"""
    player = room.players[player_id]
    actions_used = sum(1 for v in player.actions_used.values() if v)
    
    if actions_used >= 3:  # Máximo de 3 ações por turno
        handle_end_turn({'room_id': room.room_id})

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)