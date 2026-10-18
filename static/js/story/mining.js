/* ══════════════════════════════════════════════════════════════════════
   MINIGAMES DE COLETA + MINA LABIRINTO
   Carregado depois de story.html (script inline) e survival.js.
   Expõe: tbMinigame, enterMine, mine*, tbChopTree.
   ══════════════════════════════════════════════════════════════════════ */

/* ------------------------------------------------------------------ */
/*  Minigame genérico: um marcador percorre uma pista e o jogador deve */
/*  pará-lo dentro da zona-alvo. Resolve com { success, precision }.   */
/* ------------------------------------------------------------------ */
let _mgState = null;

function tbMinigame(opts) {
    opts = opts || {};
    const overlay = document.getElementById('minigame-overlay');
    const titleEl = document.getElementById('minigame-title');
    const subEl = document.getElementById('minigame-subtitle');
    const targetEl = document.getElementById('minigame-target');
    const markerEl = document.getElementById('minigame-marker');
    const feedbackEl = document.getElementById('minigame-feedback');
    const strikeBtn = document.getElementById('minigame-strike');
    const cancelBtn = document.getElementById('minigame-cancel');

    // Encerra um minigame anterior, se houver.
    if (_mgState && typeof _mgState.finish === 'function') _mgState.finish(false, 0);

    const speed = opts.speed || 0.85;            // fração da pista por segundo
    const zoneWidth = Math.max(8, Math.min(40, opts.zoneWidth || 18));
    const zoneStart = opts.zoneStart != null ? opts.zoneStart : (8 + Math.random() * (84 - zoneWidth));

    titleEl.textContent = opts.title || 'Minigame';
    subEl.textContent = opts.subtitle || 'Acerte a zona verde!';
    feedbackEl.textContent = '\u00a0';
    feedbackEl.className = 'minigame-feedback';
    targetEl.style.left = zoneStart + '%';
    targetEl.style.width = zoneWidth + '%';
    overlay.classList.add('active');

    const center = zoneStart + zoneWidth / 2;
    let pos = 0, dir = 1, last = performance.now(), raf = 0, done = false;

    function frame(now) {
        if (done) return;
        const dt = Math.min(0.05, (now - last) / 1000);
        last = now;
        pos += dir * speed * 100 * dt;
        if (pos > 100) { pos = 100; dir = -1; }
        if (pos < 0) { pos = 0; dir = 1; }
        markerEl.style.left = pos + '%';
        raf = requestAnimationFrame(frame);
    }

    function cleanup() {
        done = true;
        cancelAnimationFrame(raf);
        overlay.classList.remove('active');
        strikeBtn.removeEventListener('click', onStrike);
        cancelBtn.removeEventListener('click', onCancel);
        document.removeEventListener('keydown', onKey);
    }

    function finish(success, precision) {
        if (done) return;
        cleanup();
        _mgState = null;
        if (opts.onDone) opts.onDone(success, precision);
        if (opts.resolve) opts.resolve({ success, precision });
    }

    function onStrike() {
        if (done) return;
        const dentro = pos >= zoneStart && pos <= zoneStart + zoneWidth;
        const distancia = Math.abs(pos - center);
        const precision = Math.max(0, 1 - (distancia / 50)); // 1 = no centro
        finish(dentro, dentro ? precision : 0);
    }
    function onCancel() { finish(false, 0); }
    function onKey(e) {
        if (e.key === ' ' || e.key === 'Enter' || e.code === 'Space') { e.preventDefault(); onStrike(); }
        else if (e.key === 'Escape') { onCancel(); }
    }

    strikeBtn.addEventListener('click', onStrike);
    cancelBtn.addEventListener('click', onCancel);
    document.addEventListener('keydown', onKey);
    _mgState = { finish: (ok) => finish(ok, 0) };
    raf = requestAnimationFrame(frame);

    return new Promise(resolve => { opts.resolve = resolve; });
}

/* ------------------------------------------------------------------ */
/*  Ferramentas: localizar e gastar durabilidade                       */
/* ------------------------------------------------------------------ */
function tbFindTool(kind) {
    if (!gameState || !gameState.equipment) return null;
    const eq = gameState.equipment.mainhand;
    if (eq && eq.toolType === kind && (eq.durability === undefined || eq.durability > 0)) {
        return { item: eq, source: 'equipment', index: -1 };
    }
    for (let i = 0; i < gameState.inventory.length; i++) {
        const it = gameState.inventory[i];
        if (it && it.toolType === kind && (it.durability === undefined || it.durability > 0)) {
            return { item: it, source: 'inventory', index: i };
        }
    }
    return null;
}

// Gasta durabilidade; retorna false se a ferramenta quebrou.
function tbDamageTool(ref, n) {
    if (!ref || !ref.item || ref.item.durability === undefined) return true;
    ref.item.durability = Math.max(0, ref.item.durability - (n || 1));
    if (ref.item.durability <= 0) {
        addLog(`💥 ${ref.item.name} quebrou pelo desgaste!`);
        if (ref.source === 'equipment') gameState.equipment.mainhand = null;
        else if (ref.source === 'inventory' && ref.index >= 0) gameState.inventory[ref.index] = null;
        return false;
    }
    return true;
}

/* ------------------------------------------------------------------ */
/*  MINA LABIRINTO                                                     */
/* ------------------------------------------------------------------ */
const TB_MINE_W = 6;
const TB_MINE_H = 5;
const TB_MINE_TORCH_STEPS = 26;
const TB_MINE_ENTRANCE = '0_2';
const TB_MINE_DIRS = { n: [0, -1], s: [0, 1], e: [1, 0], w: [-1, 0] };
const TB_MINE_OPP = { n: 's', s: 'n', e: 'w', w: 'e' };
const TB_MINE_DIR_NAME = { n: '⬆️ Seguir ao Norte', s: '⬇️ Seguir ao Sul', e: '➡️ Seguir ao Leste', w: '⬅️ Seguir ao Oeste' };

const TB_MINE_ROOM_NAMES = [
    'Entrada da Galeria', 'Túnel Úmido', 'Galeria Baixa', 'Veio Escondido', 'Câmara de Pedra',
    'Túnel Tortuoso', 'Poço Fundo', 'Galeria do Carvão', 'Câmara Rachada', 'Corredor Estreito',
    'Salão de Rocha', 'Túnel do Fundo', 'Câmara Profunda', 'Galeria Abandonada', 'Veio Profundo',
    'Antro Escuro', 'Câmara Selada', 'Túnel sem Fim'
];

function tbMineKey(x, y) { return `${x}_${y}`; }

function tbMineEnsure() {
    if (!gameState.mine || !gameState.mine.generated || gameState.mine.w !== TB_MINE_W) {
        tbMineGenerate();
    }
    return gameState.mine;
}

function tbMineOreForDepth(depth) {
    const r = Math.random();
    if (depth >= 6 && r < 0.10) return { type: 'amethyst', hp: 3, maxHp: 3, yield: 1 };
    if (depth >= 3 && r < 0.42) return { type: 'iron_ore', hp: 2, maxHp: 2, yield: 1 };
    if (r < 0.62) return { type: 'coal', hp: 2, maxHp: 2, yield: Math.random() < 0.4 ? 2 : 1 };
    return { type: 'stone', hp: 1, maxHp: 1, yield: 1 };
}

function tbMineGenerate() {
    const W = TB_MINE_W, H = TB_MINE_H;
    const rooms = {};
    for (let y = 0; y < H; y++) {
        for (let x = 0; x < W; x++) {
            rooms[tbMineKey(x, y)] = {
                x, y,
                edges: { n: false, s: false, e: false, w: false },
                veins: [],
                explored: false,
                name: null
            };
        }
    }

    // Labirinto: DFS aleatório (árvore geradora).
    const visited = {};
    const e = TB_MINE_ENTRANCE.split('_');
    const startKey = tbMineKey(parseInt(e[0]), parseInt(e[1]));
    const stack = [[parseInt(e[0]), parseInt(e[1])]];
    visited[startKey] = true;
    while (stack.length) {
        const cur = stack[stack.length - 1];
        const cx = cur[0], cy = cur[1];
        const opts = [];
        for (const d of ['n', 's', 'e', 'w']) {
            const nx = cx + TB_MINE_DIRS[d][0], ny = cy + TB_MINE_DIRS[d][1];
            if (nx < 0 || ny < 0 || nx >= W || ny >= H) continue;
            if (visited[tbMineKey(nx, ny)]) continue;
            opts.push([d, nx, ny]);
        }
        if (opts.length === 0) { stack.pop(); continue; }
        const [d, nx, ny] = opts[Math.floor(Math.random() * opts.length)];
        rooms[tbMineKey(cx, cy)].edges[d] = true;
        rooms[tbMineKey(nx, ny)].edges[TB_MINE_OPP[d]] = true;
        visited[tbMineKey(nx, ny)] = true;
        stack.push([nx, ny]);
    }

    // Alguns atalhos extras para criar ciclos (labirinto menos linear).
    for (let y = 0; y < H; y++) {
        for (let x = 0; x < W; x++) {
            const r = rooms[tbMineKey(x, y)];
            if (Math.random() < 0.12 && x + 1 < W && !r.edges.e) {
                r.edges.e = true; rooms[tbMineKey(x + 1, y)].edges.w = true;
            }
            if (Math.random() < 0.12 && y + 1 < H && !r.edges.s) {
                r.edges.s = true; rooms[tbMineKey(x, y + 1)].edges.n = true;
            }
        }
    }

    // Profundidade (BFS a partir da entrada) para distribuir os veios.
    const depth = {}; depth[startKey] = 0;
    const queue = [startKey];
    while (queue.length) {
        const k = queue.shift();
        const r = rooms[k];
        for (const d of ['n', 's', 'e', 'w']) {
            if (!r.edges[d]) continue;
            const nk = tbMineKey(r.x + TB_MINE_DIRS[d][0], r.y + TB_MINE_DIRS[d][1]);
            if (depth[nk] === undefined) { depth[nk] = depth[k] + 1; queue.push(nk); }
        }
    }

    // Nomes e veios.
    let nameIdx = 0;
    Object.keys(rooms).forEach(k => {
        const r = rooms[k];
        const d = depth[k] || 0;
        r.depth = d;
        r.name = (k === startKey) ? TB_MINE_ROOM_NAMES[0]
            : TB_MINE_ROOM_NAMES[1 + (nameIdx++ % (TB_MINE_ROOM_NAMES.length - 1))];
        if (k === startKey) return;
        // Salas mais fundas tendem a ter mais veios.
        const nVeins = Math.random() < (0.35 + d * 0.06) ? (Math.random() < 0.25 ? 2 : 1) : 0;
        for (let i = 0; i < nVeins; i++) r.veins.push(tbMineOreForDepth(d));
    });
    // Uma câmara secreta no canto mais distante, com uma ametista garantida.
    let farKey = startKey, farD = -1;
    Object.keys(rooms).forEach(k => { if ((depth[k] || 0) > farD) { farD = depth[k] || 0; farKey = k; } });
    rooms[farKey].veins.push({ type: 'amethyst', hp: 4, maxHp: 4, yield: 1 });
    rooms[farKey].name = 'Câmara da Ametista';

    gameState.mine = {
        generated: true, w: W, h: H,
        rooms, pos: startKey, fuel: 0, updatedAt: Date.now()
    };
    tbMineRegisterLocations();
    return gameState.mine;
}

function tbMineRoom(key) {
    const mine = tbMineEnsure();
    return mine.rooms[key];
}

function tbMineHasTorch() {
    for (let i = 0; i < gameState.inventory.length; i++) {
        const it = gameState.inventory[i];
        if (it && it.id === 'tocha') return i;
    }
    return -1;
}

function tbMineIsLit() { return (tbMineEnsure().fuel || 0) > 0; }

// Monta a descrição dinâmica de uma sala (mostra luz, saídas e veios).
function tbMineDescribe(r) {
    const mine = tbMineEnsure();
    const lit = mine.fuel > 0;
    const parts = [];
    if (!lit) {
        parts.push('🕯️ <strong>Escuridão total.</strong> Sem uma tocha acesa você mal enxerga além do próprio nariz — impossível minerar e fácil se perder nos túneis.');
    } else {
        parts.push(`🕯️ Sua tocha ilumina a rocha (${mine.fuel} passos de fogo restantes).`);
    }
    const saidas = Object.keys(r.edges).filter(d => r.edges[d]).map(d => ({ n: 'norte', s: 'sul', e: 'leste', w: 'oeste' }[d]));
    parts.push(`Saídas: ${saidas.length ? saidas.join(', ') : 'nenhuma além de voltar'}.`);
    if (lit && r.veins.length) {
        const vistos = r.veins.filter(v => v.hp > 0).map(v => (ITEMS[v.type] && ITEMS[v.type].name) || v.type);
        if (vistos.length) parts.push(`💎 Veios visíveis: ${vistos.join(', ')}.`);
    }
    if (!lit && r.veins.length) parts.push('Você sente a rocha irregular sob a mão, mas não enxerga veios.');
    return parts.join('<br>');
}

function tbMineRegisterLocations() {
    const mine = gameState.mine;
    if (!mine) return;
    Object.keys(mine.rooms).forEach(k => {
        LOCATIONS['mine_' + k] = {
            name: `⛏️ ${mine.rooms[k].name}`,
            description: '',
            indoor: true,
            mineRoom: true,
            allowsStations: false,
            actions: []
        };
        tbMineRefresh(k);
    });
}

// Reconstrói descrição e ações de uma sala conforme o estado atual.
function tbMineRefresh(key) {
    const mine = gameState.mine;
    if (!mine) return;
    const r = mine.rooms[key];
    if (!r) return;
    const loc = LOCATIONS['mine_' + key];
    if (!loc) return;

    loc.name = `⛏️ ${r.name}`;
    loc.description = tbMineDescribe(r);

    const lit = (mine.fuel || 0) > 0;
    const acoes = [];
    const dirFn = { n: 'mineGoNorth', s: 'mineGoSouth', e: 'mineGoEast', w: 'mineGoWest' };
    for (const d of ['n', 's', 'e', 'w']) {
        if (r.edges[d]) acoes.push({ name: TB_MINE_DIR_NAME[d], action: dirFn[d], mineDir: d });
    }
    if (lit) {
        r.veins.forEach((v, i) => {
            if (v.hp > 0) {
                const oreName = (ITEMS[v.type] && ITEMS[v.type].name) || v.type;
                acoes.push({ name: `⛏️ Minerar ${oreName}`, action: 'mineDig' + i, mineDig: i });
            }
        });
    }
    if (!lit) {
        if (tbMineHasTorch() >= 0) acoes.push({ name: '🔥 Acender uma tocha', action: 'mineLightTorch' });
    } else {
        acoes.push({ name: '🔥 Acender outra tocha', action: 'mineLightTorch' });
    }
    acoes.push({ name: '🗺️ Voltar à entrada', action: 'mineReturnToEntrance' });
    acoes.push({ name: '🧗 Subir à superfície', action: 'mineClimbOut' });
    loc.actions = acoes;
}

// Atualiza a sala atual e re-renderiza.
function tbMineSync() {
    if (!gameState.mine) return;
    tbMineRefresh(gameState.mine.pos);
    if (typeof updateUI === 'function') updateUI();
}

function tbMineGoTo(key, opts) {
    opts = opts || {};
    const mine = tbMineEnsure();
    const r = mine.rooms[key];
    if (!r) return;
    mine.pos = key;
    r.explored = true;
    const locId = 'mine_' + key;
    if (!LOCATIONS[locId]) tbMineRegisterLocations();
    tbMineRefresh(key);
    if (typeof go === 'function') {
        go(locId, opts.message || `⛏️ Você avança na escuridão até ${r.name}.`);
    }
}

// Consome combustível de tocha a cada passo/ação dentro da mina.
function tbMineBurnFuel(n) {
    const mine = tbMineEnsure();
    mine.fuel = Math.max(0, (mine.fuel || 0) - (n || 1));
}

function enterMine() {
    if (gameState.isDead) return;
    const mine = tbMineEnsure();
    // Verifica ferramenta de mineração (aviso, não bloqueio).
    if (!tbFindTool('pickaxe')) {
        addLog('⚠️ Sem picareta, você poderá explorar os túneis, mas não conseguirá arrancar veio nenhum.');
    }
    tbMineGoTo(TB_MINE_ENTRANCE, { message: '🕳️ Você desce à galeria da mina. O ar é frio e úmido.' });
    if ((mine.fuel || 0) <= 0) {
        addLog('🕯️ Está escuro como breu. Acenda uma tocha (botão na sala) para enxergar, minerar e não se perder.');
    }
}

function mineLightTorch() {
    if (gameState.isDead) return;
    const idx = tbMineHasTorch();
    if (idx < 0) { addLog('🕯️ Você não tem nenhuma Tocha.'); return; }
    removeItemFromInventory(idx);
    const mine = tbMineEnsure();
    mine.fuel = (mine.fuel || 0) + TB_MINE_TORCH_STEPS;
    addLog(`🔥 Você acende uma tocha. (${mine.fuel} passos de fogo)`);
    tbMineSync();
}

function mineMove(dir) {
    if (gameState.isDead) return;
    const mine = tbMineEnsure();
    const r = mine.rooms[mine.pos];
    const lit = (mine.fuel || 0) > 0;

    if (!r.edges[dir]) { addLog('🧱 Esse caminho termina em rocha maciça.'); return; }

    let destino = tbMineKey(r.x + TB_MINE_DIRS[dir][0], r.y + TB_MINE_DIRS[dir][1]);

    // No escuro é fácil se perder: chance de parar na sala errada.
    if (!lit && Math.random() < 0.45) {
        const vizinhos = Object.keys(r.edges).filter(d => r.edges[d]);
        const d2 = vizinhos[Math.floor(Math.random() * vizinhos.length)];
        destino = tbMineKey(r.x + TB_MINE_DIRS[d2][0], r.y + TB_MINE_DIRS[d2][1]);
        addLog('🕯️ Na escuridão você perde a noção do caminho e segue às apalpadelas...');
        if (typeof SV_spend === 'function') SV_spend(0.8, 0.8);
        if (typeof SV_applySanity === 'function') SV_applySanity(-1.5);
    } else {
        if (typeof SV_spend === 'function') SV_spend(0.6, 0.6);
    }
    if (typeof SV_spendMana === 'function') SV_spendMana(0.4);
    tbMineBurnFuel(1);
    tbMineGoTo(destino, { message: `⛏️ Você avança pelo túnel. (fogo: ${mine.fuel})` });

    if (lit && mine.fuel === 0) addLog('🕯️ Sua tocha se apagou! A galeria mergulha no escuro.');
}

function mineGoNorth() { mineMove('n'); }
function mineGoSouth() { mineMove('s'); }
function mineGoEast() { mineMove('e'); }
function mineGoWest() { mineMove('w'); }

function mineDig(index) {
    if (gameState.isDead) return;
    const mine = tbMineEnsure();
    const r = mine.rooms[mine.pos];
    const vein = r.veins[index];
    if (!vein || vein.hp <= 0) return;
    if (!tbMineIsLit()) { addLog('🕯️ Está escuro demais para minerar.'); return; }

    const tool = tbFindTool('pickaxe');
    if (!tool) {
        addLog('⛏️ Você precisa de uma picareta para minerar. Compre com Bruno na Forja ou crafte uma na bancada.');
        return;
    }
    const power = tool.item.minePower || 1;
    const dificuldade = { stone: 0.7, coal: 0.95, iron_ore: 1.05, amethyst: 1.4 }[vein.type] || 1;
    const zoneWidth = vein.type === 'amethyst' ? 12 : (vein.type === 'iron_ore' ? 15 : 18);

    tbMinigame({
        title: '⛏️ Minerando',
        subtitle: 'Pare o marcador na faixa verde para lascar a rocha!',
        speed: dificuldade * 0.7,
        zoneWidth: zoneWidth
    }).then(res => {
        if (gameState.isDead) return;
        // Esforço: minerar consome MUITA energia.
        if (typeof SV_spend === 'function') SV_spend(3, 2.5);
        if (typeof SV_spendMana === 'function') SV_spendMana(1);
        tbMineBurnFuel(1);
        tbDamageTool(tool, 1);

        if (res.success) {
            const dano = power + (res.precision > 0.8 ? 1 : 0);
            vein.hp -= dano;
            if (vein.hp <= 0) {
                const qtd = vein.yield + (res.precision > 0.85 ? 1 : 0);
                addItemToInventory(vein.type, qtd);
                const nome = (ITEMS[vein.type] && ITEMS[vein.type].name) || vein.type;
                addLog(`⛏️ CRACK! O veio se rompe e você recolhe ${qtd}x ${nome}.`);
                vein.hp = 0;
            } else {
                addLog(`⛏️ Um bom golpe! A rocha racha (${vein.hp} restante${vein.hp > 1 ? 's' : ''}).`);
            }
        } else {
            addLog('⛏️ O golpe resvala na rocha e só levanta poeira. Que desperdício de energia...');
        }
        tbMineSync();
    });
}

function mineDig0() { mineDig(0); }
function mineDig1() { mineDig(1); }
function mineDig2() { mineDig(2); }

// Caminho mais curto de volta à entrada (custa energia).
function tbMinePathToEntrance() {
    const mine = tbMineEnsure();
    const alvo = TB_MINE_ENTRANCE;
    const anterior = {};
    const visitados = {};
    const fila = [mine.pos];
    visitados[mine.pos] = true;
    while (fila.length) {
        const k = fila.shift();
        if (k === alvo) break;
        const r = mine.rooms[k];
        for (const d of ['n', 's', 'e', 'w']) {
            if (!r.edges[d]) continue;
            const nk = tbMineKey(r.x + TB_MINE_DIRS[d][0], r.y + TB_MINE_DIRS[d][1]);
            if (!visitados[nk]) { visitados[nk] = true; anterior[nk] = k; fila.push(nk); }
        }
    }
    let passos = 0, cur = alvo;
    while (cur && cur !== mine.pos) { cur = anterior[cur]; passos++; }
    return passos;
}

function mineReturnToEntrance() {
    if (gameState.isDead) return;
    const passos = tbMinePathToEntrance();
    if (typeof SV_spend === 'function') SV_spend(passos * 0.8, passos * 0.8);
    const mine = tbMineEnsure();
    mine.fuel = Math.max(0, (mine.fuel || 0) - passos);
    tbMineGoTo(TB_MINE_ENTRANCE, { message: '🗺️ Você refaz o caminho de volta até a entrada da galeria.' });
    if ((mine.fuel || 0) <= 0) addLog('🕯️ Sua tocha se apagou no caminho.');
}

function mineClimbOut() {
    if (gameState.isDead) return;
    if (typeof SV_spend === 'function') SV_spend(2, 2);
    if (typeof go === 'function') go('south_mine', '🧗 Você escala de volta à luz do dia, na entrada da Mina de Ferro.');
}

/* ------------------------------------------------------------------ */
/*  CORTE DE LENHA (minigame)                                          */
/* ------------------------------------------------------------------ */
const TB_CHOP_ZONE = { pedra: 16, ferro: 20 };

function tbChopTree() {
    if (gameState.isDead) return;
    const tool = tbFindTool('axe');
    if (!tool) {
        addLog('🪓 Cortar árvore exige um machado. Compre de Bruno na Forja ou crafte um na bancada.');
        return;
    }
    const power = tool.item.chopPower || 1;
    const zoneWidth = power >= 2 ? TB_CHOP_ZONE.ferro : TB_CHOP_ZONE.pedra;

    tbMinigame({
        title: '🪓 Cortando lenha',
        subtitle: 'Ritmo firme! Pare o marcador na faixa verde.',
        speed: 0.75,
        zoneWidth: zoneWidth
    }).then(res => {
        if (gameState.isDead) return;
        // Cortar lenha cansa: gasta fome, sede e mana.
        if (typeof SV_spend === 'function') SV_spend(2.2, 2.0);
        if (typeof SV_spendMana === 'function') SV_spendMana(1.5);
        tbDamageTool(tool, 1);

        if (res.success) {
            let qtd = 1 + (res.precision > 0.8 ? 1 : 0);
            if (power >= 2) qtd += 1;
            addItemToInventory('wood', qtd);
            addLog(`🪓 Você derruba o tronco e junta ${qtd}x Madeira.` + (res.precision > 0.85 ? ' Golpe perfeito!' : ''));
        } else {
            addLog('🪓 A lâmina ricocheteia e você não solta a madeira. Tente de novo.');
        }
        if (typeof updateUI === 'function') updateUI();
    });
}

/* Alias público usado pelas ações das localidades. */
function chopWoodEastPlains() { tbChopTree(); }

/* ------------------------------------------------------------------ */
/*  Re-registra as salas da mina ao carregar um save dentro dela.      */
/* ------------------------------------------------------------------ */
const TB_origUpdateUI = (typeof updateUI === 'function') ? updateUI : null;
if (TB_origUpdateUI) {
    updateUI = function () {
        try {
            if (gameState && gameState.mine && gameState.mine.generated
                && typeof LOCATIONS !== 'undefined' && gameState.mine.pos
                && !LOCATIONS['mine_' + gameState.mine.pos]) {
                tbMineRegisterLocations();
            }
        } catch (e) { /* ignora */ }
        return TB_origUpdateUI.apply(this, arguments);
    };
}

