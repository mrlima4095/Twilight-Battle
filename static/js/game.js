const socket = io();
let currentRoom = null;
let playerId = null;
let playerName = '';
let currentPlayerId = null;
let gameState = {
    players: {},
    currentTurn: null,
    timeOfDay: 'day'
};

// Conecta ao servidor
socket.on('connect', () => {
    console.log('Conectado ao servidor');
    playerId = socket.id;
    loadRooms();
});

// Carrega salas disponíveis
async function loadRooms() {
    try {
        const response = await fetch('/api/rooms');
        const rooms = await response.json();
        displayRooms(rooms);
    } catch (error) {
        console.error('Erro ao carregar salas:', error);
    }
}

function displayRooms(rooms) {
    const roomsList = document.getElementById('rooms-list');
    roomsList.innerHTML = '';
    
    if (rooms.length === 0) {
        roomsList.innerHTML = '<p>Nenhuma sala disponível</p>';
        return;
    }
    
    rooms.forEach(room => {
        const roomElement = document.createElement('div');
        roomElement.className = 'room-item';
        roomElement.innerHTML = `
            <span>Sala ${room.id}</span>
            <span>${room.players}/${room.max_players} jogadores</span>
            <button onclick="joinRoom('${room.id}')">Entrar</button>
        `;
        roomsList.appendChild(roomElement);
    });
}

async function createRoom() {
    const name = document.getElementById('player-name').value.trim();
    if (!name) {
        alert('Digite seu nome');
        return;
    }
    
    playerName = name;
    
    try {
        const response = await fetch('/api/create_room', {
            method: 'POST'
        });
        const data = await response.json();
        joinRoom(data.room_id);
    } catch (error) {
        console.error('Erro ao criar sala:', error);
    }
}

function joinRoom(roomId) {
    const name = document.getElementById('player-name').value.trim();
    if (!name && !playerName) {
        alert('Digite seu nome');
        return;
    }
    
    playerName = playerName || name;
    currentRoom = roomId;
    
    socket.emit('join', {
        room_id: roomId,
        player_name: playerName
    });
}

// Eventos do Socket
socket.on('player_joined', (data) => {
    showScreen('waiting-room');
    document.getElementById('room-id').textContent = currentRoom;
    updatePlayersList(data.players);
});

socket.on('update_players', (data) => {
    document.getElementById('player-count').textContent = data.count;
    updatePlayersList(data.players);
    
    // Mostra botão de iniciar para o host (primeiro jogador)
    if (data.players.length > 0 && data.players[0][0] === playerId) {
        document.getElementById('start-game-btn').style.display = 'block';
    }
});

socket.on('game_started', (data) => {
    showScreen('game-screen');
    gameState.players = Object.fromEntries(data.players);
    gameState.currentTurn = data.current_turn;
    gameState.timeOfDay = data.time_of_day;
    
    updateGameUI();
});

socket.on('card_played', (data) => {
    // Atualiza UI com a carta jogada
    if (data.player_id === playerId) {
        // Remove da mão e adiciona ao campo
        updatePlayerField(data.card, data.position);
    } else {
        // Adiciona carta ao campo do oponente
        updateOpponentField(data.player_id, data.card, data.position);
    }
});

socket.on('card_drawn', (data) => {
    if (data.player_id === playerId) {
        addCardToHand(data.card);
    }
});

socket.on('attack_result', (data) => {
    showNotification(`Ataque realizado! Dano: ${data.damage}`);
    
    if (data.defender_id === playerId) {
        // Atualiza vida do jogador
        document.getElementById('player-life').textContent = data.defender_life;
        // Atualiza campo do defensor
        updateDefenderField(data.defender_field);
    }
});

socket.on('player_defeated', (data) => {
    showNotification(`${data.player_name} foi derrotado!`);
    removePlayerFromGame(data.player_id);
});

socket.on('game_over', (data) => {
    if (data.winner_id === playerId) {
        alert('Parabéns! Você venceu o jogo!');
    } else {
        alert(`${data.winner_name} venceu o jogo!`);
    }
    showScreen('login-screen');
});

socket.on('turn_changed', (data) => {
    gameState.currentTurn = data.current_player;
    gameState.timeOfDay = data.time_of_day;
    
    document.getElementById('time-of-day').textContent = 
        data.time_of_day === 'day' ? 'Dia ☀️' : 'Noite 🌙';
    
    const isMyTurn = data.current_player === playerId;
    document.getElementById('turn-indicator').textContent = 
        isMyTurn ? 'Sua vez!' : `Vez de ${getPlayerName(data.current_player)}`;
    
    // Habilita/desabilita botões de ação
    document.getElementById('draw-btn').disabled = !isMyTurn;
    
    // Atualiza destaque do jogador atual
    highlightCurrentPlayer(data.current_player);
});

socket.on('turn_timeout', (data) => {
    if (data.player_id === playerId) {
        showNotification('Tempo esgotado! Passando a vez...');
    }
});

// Funções de UI
function showScreen(screenId) {
    document.querySelectorAll('.screen').forEach(screen => {
        screen.classList.remove('active');
    });
    document.getElementById(screenId).classList.add('active');
}

function updatePlayersList(players) {
    const list = document.getElementById('players');
    list.innerHTML = '';
    players.forEach(([id, name]) => {
        const li = document.createElement('li');
        li.textContent = name + (id === playerId ? ' (você)' : '');
        list.appendChild(li);
    });
}

function startGame() {
    socket.emit('start_game', {
        room_id: currentRoom
    });
}

function drawCard() {
    if (gameState.currentTurn === playerId) {
        socket.emit('draw_card', {
            room_id: currentRoom
        });
    }
}

function endTurn() {
    socket.emit('end_turn', {
        room_id: currentRoom
    });
}

function playCard(cardIndex, position) {
    if (gameState.currentTurn === playerId) {
        socket.emit('play_card', {
            room_id: currentRoom,
            card_index: cardIndex,
            position: position
        });
    }
}

function attackPlayer(targetPlayerId) {
    if (gameState.currentTurn === playerId && targetPlayerId !== playerId) {
        socket.emit('attack', {
            room_id: currentRoom,
            target_player_id: targetPlayerId
        });
    }
}

// Funções de atualização da UI
function updateGameUI() {
    document.getElementById('time-of-day').textContent = 
        gameState.timeOfDay === 'day' ? 'Dia ☀️' : 'Noite 🌙';
    
    const isMyTurn = gameState.currentTurn === playerId;
    document.getElementById('turn-indicator').textContent = 
        isMyTurn ? 'Sua vez!' : `Vez de ${getPlayerName(gameState.currentTurn)}`;
    
    document.getElementById('draw-btn').disabled = !isMyTurn;
    
    // Cria área dos oponentes
    createOpponentsArea();
}

function createOpponentsArea() {
    const opponentsArea = document.getElementById('opponents-area');
    opponentsArea.innerHTML = '';
    
    Object.entries(gameState.players).forEach(([id, [name, life]]) => {
        if (id !== playerId) {
            const opponentDiv = document.createElement('div');
            opponentDiv.className = 'opponent-card';
            opponentDiv.innerHTML = `
                <div class="opponent-name">${name}</div>
                <div class="opponent-life">Vida: ${life}</div>
                <div class="opponent-field" id="opponent-field-${id}"></div>
                <button onclick="attackPlayer('${id}')" 
                        ${gameState.currentTurn !== playerId ? 'disabled' : ''}>
                    Atacar
                </button>
            `;
            opponentsArea.appendChild(opponentDiv);
        }
    });
}

function addCardToHand(card) {
    const handArea = document.getElementById('player-hand');
    const cardElement = createCardElement(card, handArea.children.length);
    handArea.appendChild(cardElement);
}

function createCardElement(card, index) {
    const cardDiv = document.createElement('div');
    cardDiv.className = `card ${card.position || ''}`;
    cardDiv.innerHTML = `
        <div class="card-name">${card.name}</div>
        <div class="card-description">${card.description.substring(0, 30)}...</div>
        <div class="card-stats">
            <span class="card-life">❤️ ${card.life || '-'}</span>
            <span class="card-attack">⚔️ ${card.attack || '-'}</span>
        </div>
    `;
    
    if (card.position === null) {
        // Carta na mão - pode ser jogada
        cardDiv.onclick = () => showPlayOptions(index);
    }
    
    return cardDiv;
}

function showPlayOptions(cardIndex) {
    const position = prompt('Onde jogar a carta? (ataque/defesa)');
    if (position === 'ataque' || position === 'defesa') {
        playCard(cardIndex, position);
    }
}

function updatePlayerField(card, position) {
    const fieldId = position === 'attack' ? 'player-attack-field' : 'player-defense-field';
    const field = document.getElementById(fieldId);
    const cardElement = createCardElement(card);
    field.appendChild(cardElement);
}

function updateOpponentField(playerId, card, position) {
    // Implementar atualização do campo do oponente
    console.log(`Campo do oponente ${playerId} atualizado:`, card);
}

function updateDefenderField(fieldCards) {
    // Atualiza o campo após ataque
    document.getElementById('player-attack-field').innerHTML = '';
    document.getElementById('player-defense-field').innerHTML = '';
    
    fieldCards.forEach(card => {
        updatePlayerField(card, card.position);
    });
}

function removePlayerFromGame(playerId) {
    delete gameState.players[playerId];
    createOpponentsArea();
}

function getPlayerName(playerId) {
    const player = gameState.players[playerId];
    return player ? player[0] : 'Desconhecido';
}

function highlightCurrentPlayer(playerId) {
    // Implementar destaque visual do jogador atual
}

function showNotification(message) {
    const notification = document.createElement('div');
    notification.className = 'notification';
    notification.textContent = message;
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.remove();
    }, 3000);
}

// Atualiza lista de salas a cada 5 segundos
setInterval(loadRooms, 5000);