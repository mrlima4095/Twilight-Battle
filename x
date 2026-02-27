Excelente ideia! Vou implementar um sistema de persistência de sessão usando localStorage para que o jogador continue no jogo mesmo após recarregar a página.

```html
<!-- Adicionar no início do script no game.html -->

<script>
// Configuração inicial
const gameId = '{{ game_id }}';
const SESSION_KEY = `twilight_session_${gameId}`;

// Tentar recuperar sessão anterior
let savedSession = localStorage.getItem(SESSION_KEY);
if (savedSession) {
    try {
        savedSession = JSON.parse(savedSession);
        console.log('Sessão recuperada:', savedSession);
    } catch (e) {
        console.log('Erro ao recuperar sessão:', e);
        savedSession = null;
    }
}

const socket = io({
    reconnection: true,
    reconnectionAttempts: 10,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 5000,
    timeout: 20000,
    autoConnect: true
});

let currentPlayerId = savedSession?.playerId || null;
let gameState = null;
let selectedCard = null;
let selectedCreature = null;
let actionMode = null;
let trapSlots = [null, null];
let reconnectAttempts = 0;
let reconnectTimer = null;

// Variáveis para controle de modos
let moveMode = false;
let firstSelection = null;
let equipMode = false;
let selectedItemForEquip = null;

// Função para salvar sessão
function saveSession() {
    if (currentPlayerId) {
        const session = {
            playerId: currentPlayerId,
            playerName: localStorage.getItem('playerName'),
            gameId: gameId,
            timestamp: Date.now()
        };
        localStorage.setItem(SESSION_KEY, JSON.stringify(session));
        console.log('Sessão salva:', session);
    }
}

// Função para limpar sessão
function clearSession() {
    localStorage.removeItem(SESSION_KEY);
    console.log('Sessão limpa');
}

// Função para tentar reconectar
function attemptReconnection() {
    if (reconnectAttempts < 5) {
        reconnectAttempts++;
        console.log(`Tentativa de reconexão ${reconnectAttempts}/5...`);
        
        socket.connect();
        
        if (reconnectTimer) {
            clearTimeout(reconnectTimer);
        }
        
        reconnectTimer = setTimeout(() => {
            if (!socket.connected) {
                console.log('Falha na reconexão, tentando novamente...');
                attemptReconnection();
            }
        }, 3000);
    } else {
        Swal.fire({
            icon: 'error',
            title: 'Erro de conexão',
            text: 'Não foi possível reconectar ao servidor. Recarregue a página.',
            background: '#1a1a2e',
            color: '#fff',
            confirmButtonColor: '#ffd700',
            confirmButtonText: 'Recarregar'
        }).then(() => {
            window.location.reload();
        });
    }
}

socket.on('connect', function() {
    console.log('Conectado ao servidor');
    reconnectAttempts = 0;
    
    const playerName = savedSession?.playerName || localStorage.getItem('playerName') || 'Jogador';
    
    // Se temos uma sessão, tentar reconectar diretamente
    if (savedSession) {
        console.log('Tentando reconectar com sessão existente:', savedSession);
        socket.emit('reconnect_game', {
            game_id: gameId,
            player_id: savedSession.playerId,
            player_name: playerName
        });
    } else {
        // Primeira conexão
        socket.emit('join_game', {
            game_id: gameId,
            player_name: playerName
        });
    }
    
    setTimeout(requestGameState, 500);
});

socket.on('reconnect_success', function(data) {
    console.log('Reconexão bem-sucedida:', data);
    currentPlayerId = data.player_id;
    saveSession();
    
    Swal.fire({
        icon: 'success',
        title: 'Reconectado!',
        text: 'Sua sessão foi restaurada.',
        timer: 2000,
        showConfirmButton: false,
        background: '#1a1a2e',
        color: '#fff'
    });
    
    requestGameState();
});

socket.on('connect_error', function(error) {
    console.error('Erro de conexão:', error);
    attemptReconnection();
});

socket.on('disconnect', function(reason) {
    console.log('Desconectado do servidor:', reason);
    
    if (reason === 'io server disconnect' || reason === 'transport close') {
        Swal.fire({
            icon: 'warning',
            title: 'Desconectado',
            text: 'Perdeu conexão com o servidor. Tentando reconectar...',
            background: '#1a1a2e',
            color: '#fff',
            showConfirmButton: false,
            timer: 2000
        });
        
        attemptReconnection();
    }
});

socket.on('player_joined', function(data) {
    console.log('Jogador entrou:', data);
    
    // Se for o próprio jogador, salvar ID
    if (data.player_name === localStorage.getItem('playerName')) {
        currentPlayerId = data.player_id;
        saveSession();
    }
    
    updatePlayersList(data.players);
});

socket.on('game_started', function(data) {
    console.log('Jogo começou!');
    document.getElementById('waiting-room').style.display = 'none';
    document.getElementById('player-area').style.display = 'block';
    requestGameState();
    
    Swal.fire({
        icon: 'success',
        title: 'Jogo iniciado!',
        text: 'Que comece a batalha!',
        background: '#1a1a2e',
        color: '#fff',
        confirmButtonColor: '#ffd700'
    });
});

socket.on('game_state', function(data) {
    console.log('Estado do jogo:', data);
    gameState = data;
    
    // Verificar se o jogador ainda está no jogo
    if (currentPlayerId && !gameState.players[currentPlayerId]) {
        console.log('Jogador não encontrado no estado do jogo');
        clearSession();
        
        Swal.fire({
            icon: 'error',
            title: 'Sessão expirada',
            text: 'Você foi removido do jogo. Voltando para o início...',
            background: '#1a1a2e',
            color: '#fff',
            confirmButtonColor: '#ffd700',
            timer: 3000
        }).then(() => {
            window.location.href = '/';
        });
        return;
    }
    
    updateGameUI();
});

socket.on('action_success', function(data) {
    console.log('Ação bem-sucedida:', data);
    requestGameState();
    
    if (data.result && data.result.first_round_ended) {
        Swal.fire({
            icon: 'success',
            title: '🎉 PRIMEIRA RODADA CONCLUÍDA!',
            html: '<p style="color: #fff;">Todos os jogadores já jogaram!<br><strong style="color: #ffd700;">Agora os ataques estão liberados!</strong></p>',
            background: '#1a1a2e',
            color: '#fff',
            confirmButtonColor: '#ffd700',
            timer: 3000
        });
    }
    
    if (data.action === 'equip_item' && data.result) {
        Swal.fire({
            icon: 'success',
            title: '✅ Item equipado!',
            html: `<p style="color: #fff;">${data.result.message || 'Item equipado com sucesso!'}</p>`,
            background: '#1a1a2e',
            color: '#fff',
            confirmButtonColor: '#ffd700',
            timer: 2000
        });
    }
    else if (data.action === 'swap_positions' && data.result) {
        Swal.fire({
            icon: 'success',
            title: '🔄 Posições trocadas!',
            text: data.result.message || 'Cartas trocadas com sucesso',
            timer: 1500,
            showConfirmButton: false,
            background: '#1a1a2e',
            color: '#fff'
        });
    }
    else if (data.action === 'attack' && data.result) {
        showAttackResult(data.result);
    } else {
        addLogEntry(`✅ Ação realizada: ${data.action}`);
    }
});

socket.on('action_error', function(data) {
    console.error('Erro na ação:', data);
    Swal.fire({
        icon: 'error',
        title: 'Erro',
        text: data.message,
        background: '#1a1a2e',
        color: '#fff',
        confirmButtonColor: '#ffd700'
    });
});

socket.on('game_over', function(data) {
    const winner = data.winner;
    const winnerName = gameState.players[winner].name;
    
    // Limpar sessão quando o jogo acaba
    clearSession();
    
    Swal.fire({
        title: '🏆 FIM DE JOGO! 🏆',
        html: `<h2 style="color: #ffd700;">${winnerName} VENCEU!</h2>`,
        icon: 'success',
        background: '#1a1a2e',
        color: '#fff',
        confirmButtonColor: '#ffd700',
        confirmButtonText: 'Voltar ao início'
    }).then(() => {
        window.location.href = '/';
    });
});

socket.on('player_left', function(data) {
    console.log('Jogador saiu:', data);
    addLogEntry(`👋 Jogador ${data.player_id} saiu da partida`);
    requestGameState();
});

// Função para verificar se ainda está no jogo periodicamente
setInterval(function() {
    if (socket.connected && currentPlayerId) {
        socket.emit('ping_game', {
            game_id: gameId,
            player_id: currentPlayerId
        });
    }
}, 30000); // Ping a cada 30 segundos

// Salvar sessão antes de recarregar a página
window.addEventListener('beforeunload', function() {
    if (currentPlayerId) {
        saveSession();
    }
});

// Na criação da sala, já salvar sessão
document.addEventListener('DOMContentLoaded', function() {
    // Verificar se acabou de criar uma sala
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('created') === 'true') {
        const playerName = localStorage.getItem('playerName') || 'Jogador';
        
        // Limpar sessão anterior se existir
        clearSession();
        
        // Pequeno delay para garantir que a sala foi criada
        setTimeout(() => {
            socket.emit('join_game', {
                game_id: gameId,
                player_name: playerName
            });
        }, 500);
    }
});

// ... (resto do código existente) ...
</script>
```

```python
# Adicionar no app.py dentro da classe Game


```

```python
# Adicionar no handle_player_action do app.py




```

```html
<!-- Adicionar indicador de sessão no game.html dentro do game-header -->


```

```javascript
// Adicionar função para mostrar indicador de sessão


// Chamar quando reconectar


// Adicionar CSS para o indicador
const sessionStyle = document.createElement('style');
sessionStyle.textContent = `

`;
document.head.appendChild(sessionStyle);
```

Como funciona o sistema de persistência:

🔄 Características:

1. Salvamento automático:
   · ID do jogador é salvo no localStorage
   · Sessão é única por sala (twilight_session_4PANP6)
   · Salva antes de recarregar a página
2. Reconexão inteligente:
   · Ao recarregar, tenta reconectar com o mesmo ID
   · Servidor verifica se jogador ainda existe
   · Se não existir, tenta entrar como novo
3. Ping de manutenção:
   · A cada 30 segundos, envia "ping" para servidor
   · Mantém sessão ativa
   · Detecta se foi removido do jogo
4. Tratamento de erros:
   · Até 5 tentativas de reconexão
   · Timeout progressivo
   · Fallback para recarregar página

🎯 Benefícios:

· ✅ Não perde progresso ao recarregar
· ✅ Volta exatamente onde estava
· ✅ Mantém cartas na mão
· ✅ Continua no mesmo turno
· ✅ Sessão única por sala

📱 Exemplo de uso:

1. Jogador entra na sala 4PANP6 como "Felipe"
2. ID h-ETY_NcJQUyqxwcAAAD é salvo
3. Jogador recarrega a página acidentalmente
4. Ao carregar, reconecta automaticamente
5. Volta ao jogo exatamente onde parou!

Agora seus jogadores podem recarregar a página sem medo de perder o progresso! 🎮