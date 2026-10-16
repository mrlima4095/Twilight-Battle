/*
 * Twilight Battle — Modo História
 * Módulo de sistemas: encontros, masmorra, habilidades, bestiário,
 * conquistas, clima e diário de missões.
 * ------------------------------------------------------------------
 * Carregado DEPOIS do script principal de story.html. Ele NÃO reescreve
 * o jogo: apenas estende os objetos globais (CREATURES, ITEMS, LOCATIONS,
 * NPC_DEFINITIONS, QUESTS) e envolve (wrap) algumas funções existentes.
 *
 * Convenções:
 *   - Handlers usados em `onclick` do jogo são funções globais.
 *   - Helpers internos usam o prefixo `TB_`/`tb`.
 *   - Nada aqui roda na tela-título sem `gameState.character`.
 */

// ══════════════════════════════════════════════════════════════════════
// 1. DADOS NOVOS
// ══════════════════════════════════════════════════════════════════════

// Itens novos (materiais de dragão, boss e recompensas)
const TB_EXTRA_ITEMS = {
    dragon_scale: { name: 'Escama de Dragão', type: 'material', consumable: true, description: 'Escama dura como aço, ainda quente.' },
    dragon_heart: { name: 'Coração de Dragão', type: 'material', consumable: true, description: 'Prova de valor: o coração ainda pulsa levemente.' },
    twilight_crown: { name: 'Coroa do Crepúsculo', type: 'armor', slot: 'helmet', attack: 0, defense: 90, durability: 300, maxDurability: 300, description: 'A coroa do Mago Negro. Pesa mais do que parece — e não só em metal.' },
    black_grimoire: { name: 'Grimório Negro', type: 'tool', consumable: false, description: 'Conhecimento proibido do Crepúsculo. Use com cuidado.' },
};

// Criaturas novas + rebalanceio do dragão para tornar a caçada viável
const TB_EXTRA_CREATURES = {
    goblin: { id: 'goblin', name: 'Goblin', life: 120, attack: 35, defense: 10, exp: 25, gold: 8, drops: ['bone', 'dagger'], emoji: '👺' },
    orc: { id: 'orc', name: 'Orc', life: 320, attack: 70, defense: 30, exp: 60, gold: 20, drops: ['raw_meat', 'iron_hemlet'], emoji: '👹' },
    skeleton: { id: 'skeleton', name: 'Esqueleto', life: 180, attack: 55, defense: 20, exp: 45, gold: 12, drops: ['bone', 'paper'], emoji: '💀' },
    bat: { id: 'bat', name: 'Morcego Sombrio', life: 70, attack: 25, defense: 5, exp: 15, gold: 3, drops: ['leather'], emoji: '🦇' },
    cemetery_lord: { id: 'cemetery_lord', name: 'Senhor do Mausoléu', life: 900, attack: 130, defense: 55, exp: 500, gold: 250, drops: ['bone_meal', 'iron_shield'], emoji: '☠️' },
    black_mage: { id: 'black_mage', name: 'Mago Negro', life: 2600, attack: 200, defense: 80, exp: 5000, gold: 1000, drops: ['black_grimoire'], emoji: '🧙‍♂️' },
};

// Tabelas de encontro por localização. `chance` é a chance base de um combate.
const TB_ENCOUNTERS = {
    dark_forest: { chance: 0.65, table: ['wolf', 'wolf', 'goblin', 'orc', 'bat'] },
    ancient_ruins: { chance: 0.55, table: ['goblin', 'goblin', 'bat', 'skeleton'] },
    east_ruins_path: { chance: 0.6, table: ['goblin', 'goblin', 'orc', 'bat'] },
    north_forest_edge: { chance: 0.7, table: ['wolf', 'orc', 'orc', 'goblin'] },
    abandoned_cemetery: { chance: 0.6, table: ['skeleton', 'skeleton', 'bat'] },
    cemetery_graves: { chance: 0.75, table: ['skeleton', 'skeleton', 'bat', 'cemetery_lord'] },
    east_wilds: { chance: 0.6, table: ['goblin', 'orc', 'bat', 'wolf'] },
    north_trail_middle: { chance: 0.3, table: ['wolf', 'bat'] },
    south_trade_route: { chance: 0.25, table: ['goblin', 'bat'] },
};

// Clima: muda a cada amanhecer conforme a estação.
const TB_WEATHERS = {
    clear: { id: 'clear', name: 'Céu Limpo', icon: '🌤️', encounterBonus: 0.0, damageMult: 1.0 },
    rain: { id: 'rain', name: 'Chuva', icon: '🌧️', encounterBonus: 0.1, damageMult: 1.0 },
    fog: { id: 'fog', name: 'Neblina', icon: '🌫️', encounterBonus: 0.25, damageMult: 1.0 },
    storm: { id: 'storm', name: 'Tempestade', icon: '⛈️', encounterBonus: 0.15, damageMult: 1.1 },
    snow: { id: 'snow', name: 'Neve', icon: '🌨️', encounterBonus: 0.05, damageMult: 1.0 },
};

// Habilidades por raça (usam mana).
const TB_SKILLS = {
    esquiva: { name: 'Esquiva', icon: '💨', cost: 25, use: TB_skillEsquiva, desc: 'Anula o próximo golpe recebido.' },
    magia: { name: 'Bola de Fogo', icon: '🔥', cost: 40, use: TB_skillMagia, desc: 'Dano mágico pesado instantâneo.' },
    carga: { name: 'Carga', icon: '🐎', cost: 30, use: TB_skillCarga, desc: 'Investida com o dobro do ataque.' },
    cura: { name: 'Bênção da Ninfa', icon: '🌿', cost: 35, use: TB_skillCura, desc: 'Recupera bastante vida.' },
};

// Conquistas (baseadas no ROADMAP.md)
const TB_ACHIEVEMENTS = [
    { id: 'primeira_missao', name: 'Primeira Missão', icon: '📜', desc: 'Complete sua primeira missão.', check: s => s.questsCompleted >= 1 },
    { id: 'heroi_do_reino', name: 'Herói do Reino', icon: '👑', desc: 'Conclua a campanha "A Sombra de Duas Coroas".', check: s => (gameState.completedQuests || []).includes('main_two_crowns') },
    { id: 'cacador_de_lobos', name: 'Caçador de Lobos', icon: '🐺', desc: 'Derrote 25 lobos.', check: s => (s.killsByType.wolf || 0) >= 25 },
    { id: 'matador_de_dragoes', name: 'Matador de Dragões', icon: '🐉', desc: 'Derrote um dragão.', check: s => (s.killsByType.dragon || 0) >= 1 },
    { id: 'acougueiro', name: 'Açougueiro da Aurora', icon: '🪓', desc: 'Derrote 50 criaturas.', check: s => s.kills >= 50 },
    { id: 'andarilho', name: 'Andarilho', icon: '🥾', desc: 'Visite 10 locais diferentes.', check: s => Object.keys(s.locations || {}).length >= 10 },
    { id: 'viajante', name: 'Viajante', icon: '🧭', desc: 'Visite 20 locais diferentes.', check: s => Object.keys(s.locations || {}).length >= 20 },
    { id: 'aguas_sagradas', name: 'Águas Sagradas', icon: '💧', desc: 'Visite o Lago Sagrado.', check: s => !!(s.locations || {}).sacred_lake },
    { id: 'terras_selvagens', name: 'Terras Selvagens', icon: '🌲', desc: 'Visite a Floresta Sombria.', check: s => !!(s.locations || {}).dark_forest },
    { id: 'atravessando_fronteiras', name: 'Atravessando Fronteiras', icon: '🌑', desc: 'Chegue ao Portão do Crepúsculo.', check: s => !!(s.locations || {}).twilight_gate },
    { id: 'mestre_dos_mapas', name: 'Mestre dos Mapas', icon: '🗺️', desc: 'Complete a missão do cartógrafo Pedro.', check: s => (gameState.completedQuests || []).includes('pedro_map') },
    { id: 'fortuna_modesta', name: 'Fortuna Modesta', icon: '💰', desc: 'Tenha 250 de ouro.', check: s => gameState.character && gameState.character.gold >= 250 },
    { id: 'magnata', name: 'Magnata da Aurora', icon: '💎', desc: 'Tenha 1000 de ouro.', check: s => gameState.character && gameState.character.gold >= 1000 },
    { id: 'tesouro_real', name: 'Tesouro Real', icon: '👑', desc: 'Tenha 5000 de ouro.', check: s => gameState.character && gameState.character.gold >= 5000 },
    { id: 'comerciante', name: 'Comerciante', icon: '🤝', desc: 'Faça 10 compras.', check: s => (s.purchases || 0) >= 10 },
    { id: 'artesao', name: 'Artesão Iniciante', icon: '🔨', desc: 'Crie 10 itens.', check: s => (s.crafted || 0) >= 10 },
    { id: 'faz_tudo', name: 'Faz-tudo', icon: '🧰', desc: 'Crie 5 receitas diferentes.', check: s => Object.keys(s.recipes || {}).length >= 5 },
    { id: 'estomago_de_aco', name: 'Estômago de Aço', icon: '🍖', desc: 'Consuma 25 comidas.', check: s => (s.foods || 0) >= 25 },
    { id: 'engenheiro', name: 'Engenheiro Amador', icon: '⚙️', desc: 'Monte 3 estações de trabalho.', check: s => (s.stations || 0) >= 3 },
    { id: 'amigos_de_todos', name: 'Amigos de Todos', icon: '💬', desc: 'Converse com 8 NPCs diferentes.', check: s => Object.keys(s.npcs || {}).length >= 8 },
    { id: 'leitor_registrado', name: 'Leitor Registrado', icon: '📖', desc: 'Leia um livro.', check: s => (s.books || 0) >= 1 },
    { id: 'devorador_de_livros', name: 'Devorador de Livros', icon: '📚', desc: 'Leia 5 livros.', check: s => (s.books || 0) >= 5 },
    { id: 'reputacao_exemplar', name: 'Reputação Exemplar', icon: '⭐', desc: 'Alcance reputação 80 na Biblioteca.', check: s => (gameState.library && gameState.library.reputation || 0) >= 80 },
    { id: 'bestiario', name: 'Bestiário Iniciante', icon: '📕', desc: 'Registre 6 criaturas no bestiário.', check: s => Object.keys(s.killsByType || {}).length >= 6 },
    { id: 'ano_novo', name: 'Ano Novo', icon: '🎉', desc: 'Viva a virada de um ano.', check: s => (s.years || 1) >= (gameState.yearCount || 1540) && (s.yearAdvances || 0) >= 1 },
    { id: 'madrugador', name: 'Madrugador', icon: '🌅', desc: 'Durma e acorde de manhã.', check: s => (s.sleeps || 0) >= 1 },
];

// ══════════════════════════════════════════════════════════════════════
// 2. INICIALIZAÇÃO DE ESTADO
// ══════════════════════════════════════════════════════════════════════

function TB_ensureState() {
    if (typeof gameState === 'undefined' || !gameState) return;

    if (!gameState.stats || typeof gameState.stats !== 'object') {
        gameState.stats = {
            kills: 0, killsByType: {}, questsCompleted: 0, crafted: 0, recipes: {},
            foods: 0, books: 0, npcs: {}, locations: {}, purchases: 0, stations: 0,
            sleeps: 0, years: 1, yearAdvances: 0,
        };
    }
    const s = gameState.stats;
    s.killsByType = s.killsByType || {};
    s.recipes = s.recipes || {};
    s.npcs = s.npcs || {};
    s.locations = s.locations || {};
    if (typeof s.kills !== 'number') s.kills = 0;
    if (typeof s.questsCompleted !== 'number') s.questsCompleted = 0;
    if (typeof s.crafted !== 'number') s.crafted = 0;
    if (typeof s.foods !== 'number') s.foods = 0;
    if (typeof s.books !== 'number') s.books = 0;
    if (typeof s.purchases !== 'number') s.purchases = 0;
    if (typeof s.stations !== 'number') s.stations = 0;
    if (typeof s.sleeps !== 'number') s.sleeps = 0;
    if (typeof s.yearAdvances !== 'number') s.yearAdvances = 0;

    if (!gameState.achievements || typeof gameState.achievements !== 'object') gameState.achievements = {};
    if (!gameState.bestiary || typeof gameState.bestiary !== 'object') gameState.bestiary = {};
    if (typeof gameState._evasionActive !== 'boolean') gameState._evasionActive = false;

    // Clima: garante um valor válido.
    if (!gameState.weather || !TB_WEATHERS[gameState.weather.id]) {
        gameState.weather = TB_rollWeather();
    }
    if (!gameState.weather.id) gameState.weather = TB_WEATHERS.clear;

    // Marca o local atual como visitado.
    if (gameState.location) {
        gameState.stats.locations[gameState.location] = true;
    }

    TB_recordDiscoveredBestiary();
}

function TB_rollWeather() {
    const season = (gameState && gameState.seasonCount) || 1;
    const roll = Math.random();
    let id = 'clear';
    if (season === 1) id = roll < 0.55 ? 'clear' : (roll < 0.8 ? 'rain' : 'fog');
    else if (season === 2) id = roll < 0.8 ? 'clear' : 'storm';
    else if (season === 3) id = roll < 0.7 ? 'clear' : (roll < 0.9 ? 'fog' : 'rain');
    else id = roll < 0.4 ? 'snow' : (roll < 0.75 ? 'fog' : 'clear');
    return { ...TB_WEATHERS[id] };
}

function TB_weather() {
    if (gameState && gameState.weather && TB_WEATHERS[gameState.weather.id]) return TB_WEATHERS[gameState.weather.id];
    return TB_WEATHERS.clear;
}

// ══════════════════════════════════════════════════════════════════════
// 3. ESTENDER OS OBJETOS DO JOGO (mutação — não reatribuição)
// ══════════════════════════════════════════════════════════════════════

if (typeof ITEMS !== 'undefined') Object.assign(ITEMS, TB_EXTRA_ITEMS);
if (typeof CREATURES !== 'undefined') {
    Object.assign(CREATURES, TB_EXTRA_CREATURES);
    // Rebalanceia o dragão para a caçada da campanha.
    if (CREATURES.dragon) {
        CREATURES.dragon.life = 1500;
        CREATURES.dragon.attack = 180;
        CREATURES.dragon.defense = 60;
        CREATURES.dragon.exp = 1200;
        CREATURES.dragon.drops = ['dragon_scale', 'dragon_heart'];
        CREATURES.dragon.emoji = '🐉';
    }
}

// Localizações novas
if (typeof LOCATIONS !== 'undefined') {
    LOCATIONS.dragon_peak = {
        name: 'Pico do Dragão',
        description: 'O ar é rarefeito e quente. Ossos antigos salpicam a pedra e o chão treme a cada rugido que ecoa das nuvens.',
        allowsStations: true,
        actions: [
            { name: '🐉 Enfrentar o Dragão', action: 'exploreDragonPeak' },
            { name: '🔙 Descer para a Floresta', action: 'goNorthForestEdge' },
        ],
    };
    LOCATIONS.east_wilds = {
        name: 'Terras Selvagens do Leste',
        description: 'A planície dá lugar a um descampado pedregoso. Fogueiras apagadas e ossos indicam que bandos passaram por aqui.',
        allowsStations: true,
        actions: [
            { name: '⚔️ Explorar as Terras Selvagens', action: 'exploreEastWilds' },
            { name: '🔙 Voltar para a Planície Leste', action: 'goEastPlains' },
        ],
    };
    LOCATIONS.east_ruins_camp = {
        name: 'Acampamento em Ruínas',
        description: 'Restos de um acampamento abandonado às pressas. Uma fogueira ainda fumega e caixas foram deixadas para trás.',
        allowsStations: true,
        actions: [
            { name: '🔍 Vasculhar o Acampamento', action: 'searchEastCamp' },
            { name: '🔙 Voltar para o Caminho Leste', action: 'goEastRuinsPath' },
        ],
    };
    LOCATIONS.cemetery_mausoleum = {
        name: 'Mausoléu do Clã',
        description: 'Portas de pedra pesadas rangem ao abrir. No centro, um sarcófago selado pulsa com uma energia fria e errada.',
        allowsStations: false,
        actions: [
            { name: '🪦 Abrir o Sarcófago', action: 'searchMausoleum' },
            { name: '🔙 Sair do Mausoléu', action: 'goCemetery' },
        ],
    };
    LOCATIONS.cemetery_graves = {
        name: 'As Covas',
        description: 'Fileiras de covas rasas se perdem na névoa. O chão está revirado — algo se levantou daqui, e não foi sozinho.',
        allowsStations: false,
        actions: [
            { name: '⚔️ Investigar as Covas', action: 'searchGraves' },
            { name: '🔙 Voltar ao Cemitério', action: 'goCemetery' },
        ],
    };
    LOCATIONS.twilight_gate = {
        name: 'Portão do Crepúsculo',
        description: 'A fronteira do Reino do Crepúsculo. Estradas queimadas, estandartes escuros e um sol que parece nunca aquecer de verdade.',
        allowsStations: true,
        actions: [
            { name: '🌑 Avançar até a Cidadela', action: 'enterTwilightCitadel' },
            { name: '🔙 Voltar para as Aldeias do Sul', action: 'goSouthVillages' },
        ],
    };
    LOCATIONS.twilight_citadel = {
        name: 'Cidadela do Crepúsculo',
        description: 'A fortaleza do Mago Negro. Sombra escorre pelas paredes como água suja, e a própria luz parece pedir licença para entrar.',
        allowsStations: false,
        actions: [
            { name: '🧙‍♂️ Desafiar o Mago Negro', action: 'challengeBlackMage' },
            { name: '🔙 Recuar para o Portão', action: 'goTwilightGate' },
        ],
    };

    // Corrige (antes vazias) e enriquece ações dos locais existentes.
    if (LOCATIONS.abandoned_cemetery) {
        LOCATIONS.abandoned_cemetery.actions = [
            { name: '⚰️ Mausoléu do Clã', action: 'openMausoleum' },
            { name: '🛣️ Seguir para as Covas', action: 'goCemeteryGraves' },
            { name: '🔙 Sair do Cemitério', action: 'exitAbandonedCemetery' },
        ];
    }
    if (LOCATIONS.north_forest_edge) {
        LOCATIONS.north_forest_edge.actions = [
            { name: '🌲 Entrar na Floresta Sombria', action: 'goDarkForest' },
            { name: '🐉 Subir ao Pico do Dragão', action: 'goDragonPeak' },
            { name: '🔙 Voltar para as Ruínas', action: 'goAcrossBridge' },
        ];
    }
    if (LOCATIONS.south_villages) {
        LOCATIONS.south_villages.actions = [
            { name: '🌑 Seguir para o Portão do Crepúsculo', action: 'goTwilightGate' },
            { name: '🔙 Voltar para a Estrada Comercial', action: 'goSouthTradeRoute' },
        ];
    }
    if (LOCATIONS.great_hall && LOCATIONS.great_hall.actions) {
        // Adiciona atalho para o diário no castelo (além do quadro de missões).
        if (!LOCATIONS.great_hall.actions.some(a => a.action === 'showJournalModal')) {
            LOCATIONS.great_hall.actions.push({ name: '📖 Abrir Diário de Missões', action: 'showJournalModal' });
        }
    }
}

// NPCs: liga o Capitão e o Rei às missões (antes só escreviam no log).
if (typeof NPC_DEFINITIONS !== 'undefined') {
    if (NPC_DEFINITIONS.captain && Array.isArray(NPC_DEFINITIONS.captain.topics)) {
        const t = NPC_DEFINITIONS.captain.topics.find(t => (t.name || '').includes('Missões'));
        if (t) {
            t.message = '"Temos missões de sobra. Veja o quadro — e ande bem armado."';
            t.action = () => showQuestBoard();
        }
    }
    if (NPC_DEFINITIONS.king && Array.isArray(NPC_DEFINITIONS.king.topics)) {
        if (!NPC_DEFINITIONS.king.topics.some(t => (t.name || '').includes('Missão'))) {
            NPC_DEFINITIONS.king.topics.unshift({
                name: '📜 Missões do Reino',
                message: '"Falei que precisava de heróis vivos, não de estátuas. Veja o que temos."',
                action: () => showQuestBoard(),
            });
        }
    }
}

// ══════════════════════════════════════════════════════════════════════
// 4. BESTIÁRIO / CONQUISTAS
// ══════════════════════════════════════════════════════════════════════

function TB_recordDiscoveredBestiary() {
    if (!gameState || !gameState.bestiary) return;
    if (typeof CREATURES === 'undefined') return;
    for (const id in gameState.stats.killsByType) {
        if (gameState.stats.killsByType[id] > 0) gameState.bestiary[id] = gameState.bestiary[id] || gameState.stats.killsByType[id];
    }
}

function TB_onKill(creatureId) {
    if (!creatureId || !gameState || !gameState.stats) return;
    gameState.stats.kills++;
    gameState.stats.killsByType[creatureId] = (gameState.stats.killsByType[creatureId] || 0) + 1;
    gameState.bestiary[creatureId] = (gameState.bestiary[creatureId] || 0) + 1;
    TB_checkAchievements();
}

function TB_unlock(id) {
    const def = TB_ACHIEVEMENTS.find(a => a.id === id);
    if (!def) return;
    gameState.achievements[id] = true;
    addLog(`🏆 CONQUISTA DESBLOQUEADA: ${def.icon} ${def.name}`);
    if (typeof StoryModal !== 'undefined') {
        StoryModal.fire({
            title: '🏆 Conquista!',
            html: `<div style="text-align:center"><div style="font-size:42px">${def.icon}</div><p><strong>${def.name}</strong></p><p style="color:#a39bb8">${def.desc}</p></div>`,
            icon: 'success', toast: true, timer: 3500, timerProgressBar: true,
            showConfirmButton: false, position: 'top-end',
        });
    }
}

function TB_checkAchievements() {
    if (!gameState || !gameState.character) return;
    gameState.achievements = gameState.achievements || {};
    const s = gameState.stats || {};
    for (const ach of TB_ACHIEVEMENTS) {
        if (gameState.achievements[ach.id]) continue;
        let ok = false;
        try { ok = !!ach.check(s); } catch (e) { ok = false; }
        if (ok) TB_unlock(ach.id);
    }
}

// ══════════════════════════════════════════════════════════════════════
// 5. ENCONTROS
// ══════════════════════════════════════════════════════════════════════

function TB_spawnEncounterFor(locationId) {
    const cfg = TB_ENCOUNTERS[locationId];
    if (!cfg) return false;
    const bonus = TB_weather().encounterBonus;
    if (Math.random() > Math.min(0.95, cfg.chance + bonus)) return false;
    const enemyId = cfg.table[Math.floor(Math.random() * cfg.table.length)];
    const base = CREATURES[enemyId];
    if (!base) return false;
    gameState.currentEnemy = JSON.parse(JSON.stringify(base));
    addLog(`⚔️ ${base.emoji || '❗'} Um ${base.name} bloqueia seu caminho!`);
    return true;
}

// ══════════════════════════════════════════════════════════════════════
// 6. MORTAIS / MORTE DE INIMIGO
// ══════════════════════════════════════════════════════════════════════

function TB_resolveKill(enemy) {
    if (!enemy) return;
    addLog(`✨ Você derrotou ${enemy.name}!`);
    gameState.character.exp += enemy.exp;
    gameState.character.gold += enemy.gold;
    addLog(`💰 Ganhou ${enemy.exp} EXP e ${enemy.gold} moedas!`);
    if (Math.random() < 0.4 && enemy.drops && enemy.drops.length) {
        const drop = enemy.drops[Math.floor(Math.random() * enemy.drops.length)];
        if (typeof ITEMS !== 'undefined' && ITEMS[drop]) {
            addItemToInventory(drop);
            addLog(`🎁 Você pegou ${ITEMS[drop].name} de ${enemy.name}!`);
        }
    }
    try { trigger('kill', { creatureId: enemy.id }); } catch (e) { /* sem missão ativa */ }
    gameState.currentEnemy = null;
    TB_onKill(enemy.id);
    checkAndApplyLevelUp();
    updateUI();
}

// ══════════════════════════════════════════════════════════════════════
// 7. HABILIDADES (combate)
// ══════════════════════════════════════════════════════════════════════

function TB_skillOf(race) {
    const raceDef = (typeof RACES !== 'undefined' && RACES[race]) ? RACES[race] : null;
    const key = raceDef ? raceDef.skill : null;
    return TB_SKILLS[key] || null;
}

function TB_skillEsquiva() {
    gameState._evasionActive = true;
    addLog('💨 Você se prepara para esquivar do próximo golpe!');
}
function TB_skillMagia() {
    const enemy = gameState.currentEnemy;
    const lvl = gameState.character.level || 1;
    const dmg = 80 + lvl * 15 + Math.floor(Math.random() * 25);
    enemy.life -= dmg;
    addLog(`🔥 Bola de Fogo causou ${dmg} de dano em ${enemy.name}!`);
}
function TB_skillCarga() {
    const enemy = gameState.currentEnemy;
    const race = RACES[gameState.character.race];
    const bonuses = calculateEquipmentBonuses();
    const dmg = Math.max(1, (race.baseAttack + bonuses.attackBonus) * 2 - enemy.defense);
    enemy.life -= dmg;
    addLog(`🐎 Carga devastadora: ${dmg} de dano em ${enemy.name}!`);
}
function TB_skillCura() {
    const lvl = gameState.character.level || 1;
    const heal = 120 + lvl * 10;
    const before = gameState.character.life;
    gameState.character.life = Math.min(gameState.character.maxLife, gameState.character.life + heal);
    addLog(`🌿 Bênção da Ninfa recuperou ${gameState.character.life - before} de vida!`);
}

function useSkill() {
    if (gameState.isDead) return;
    if (!gameState.currentEnemy) { addLog('💡 Você só pode usar habilidades em combate.'); return; }
    const skill = TB_skillOf(gameState.character.race);
    if (!skill) { addLog('❌ Sua raça não possui habilidade.'); return; }
    if (gameState.character.mana < skill.cost) {
        addLog(`🔮 Mana insuficiente para ${skill.name} (precisa de ${skill.cost}).`);
        return;
    }
    gameState.character.mana -= skill.cost;
    addLog(`${skill.icon} Você usa ${skill.name}!`);
    try { skill.use(); } catch (e) { addLog('⚠️ A habilidade falhou.'); }
    if (gameState.currentEnemy && gameState.currentEnemy.life <= 0) {
        TB_resolveKill(gameState.currentEnemy);
    } else {
        updateUI();
    }
}

// ══════════════════════════════════════════════════════════════════════
// 8. AÇÕES DE LOCALIZAÇÃO NOVAS / CORRIGIDAS
// ══════════════════════════════════════════════════════════════════════

function goNorthForestEdge() { go('north_forest_edge', '🌲 Você desce para a Entrada da Floresta Sombria.'); }
function goDragonPeak() { go('dragon_peak', '🐉 Você escala o Pico do Dragão. O rugido fica mais perto a cada passo.'); }
function goCemetery() { go('abandoned_cemetery', '🪦 Você volta para o cemitério.'); }
function goEastRuinsPath() { go('east_ruins_path', '➡️ Você retorna ao Caminho Leste das Ruínas.'); }
function goTwilightGate() { go('twilight_gate', '🌑 Você cruza a fronteira para o Reino do Crepúsculo.'); }

function openMausoleum() { go('cemetery_mausoleum', '⚰️ A porta de pedra range enquanto você entra no mausoléu.'); }
function goCemeteryGraves() { go('cemetery_graves', '🛣️ Você segue entre as covas, a névoa engolindo seus passos.'); }

function searchMausoleum() {
    if (gameState.isDead) return;
    if ((gameState.stats.killsByType.cemetery_lord || 0) > 0 && Math.random() < 0.5) {
        addLog('🪦 O sarcófago está vazio. Restam só ossos e poeira.');
        const r = Math.random();
        if (r < 0.4) { gameState.character.gold += 40; addLog('💰 Você encontra 40 moedas escondidas nas frestas!'); }
        updateUI();
        return;
    }
    addLog('☠️ O sarcófago se abre com um estalo. Algo antigo se ergue!');
    gameState.currentEnemy = JSON.parse(JSON.stringify(CREATURES.cemetery_lord));
    updateUI();
}

function searchGraves() {
    if (gameState.isDead) return;
    if (TB_spawnEncounterFor('cemetery_graves')) { updateUI(); return; }
    const r = Math.random();
    if (r < 0.35) { addItemToInventory('bone'); addLog('🦴 Você encontra um osso antigo entre as covas.'); }
    else if (r < 0.55) { const g = 5 + Math.floor(Math.random() * 25); gameState.character.gold += g; addLog(`💰 ${g} moedas perdidas entre as lápides!`); }
    else addLog('🪦 Nada além de névoa e silêncio... por enquanto.');
    updateUI();
}

function exploreDragonPeak() {
    if (gameState.isDead) return;
    if (gameState.currentEnemy) return;
    addLog('🐉 O chão treme. Asas enormes rasgam as nuvens — o dragão desce!');
    gameState.currentEnemy = JSON.parse(JSON.stringify(CREATURES.dragon));
    updateUI();
}

function exploreEastWilds() {
    if (gameState.isDead) return;
    if (TB_spawnEncounterFor('east_wilds')) { updateUI(); return; }
    const r = Math.random();
    if (r < 0.4) { addItemToInventory('wood'); addLog('🪵 Você encontra madeira entre os destroços de uma carroça.'); }
    else addLog('🌾 O descampado está silencioso. Só o vento passa.');
    updateUI();
}

function searchEastCamp() {
    if (gameState.isDead) return;
    if (Math.random() < 0.5) {
        const g = 10 + Math.floor(Math.random() * 40);
        gameState.character.gold += g;
        addLog(`💰 Você saqueia ${g} moedas do acampamento abandonado!`);
    } else if (Math.random() < 0.6) {
        const finds = ['paper', 'bone', 'cloth'];
        const f = finds[Math.floor(Math.random() * finds.length)];
        addItemToInventory(f);
        addLog(`📦 Você encontra ${ITEMS[f].name} numa caixa largada.`);
    } else {
        addLog('🔍 O acampamento foi saqueado antes de você chegar.');
    }
    updateUI();
}

function enterTwilightCitadel() { go('twilight_citadel', '🌑 Você adentra a Cidadela do Crepúsculo. A temperatura despenca.'); }

function challengeBlackMage() {
    if (gameState.isDead) return;
    if ((gameState.stats.killsByType.black_mage || 0) > 0) {
        addLog('🧙‍♂️ As sombras se aquietaram. O Mago Negro não volta tão cedo.');
        return;
    }
    StoryModal.fire({
        title: '🧙‍♂️ O Mago Negro',
        html: '<p style="text-align:center">"Então a Aurora mandou uma criança brincar de herói..."</p><p style="text-align:center;color:#a39bb8">Prepare-se: esta é a batalha final. Você tem certeza?</p>',
        icon: 'warning',
        showCancelButton: true,
        confirmButtonText: '⚔️ Enfrentar',
        cancelButtonText: 'Recuar',
    }).then(res => {
        if (!res.isConfirmed) return;
        addLog('🌑 O Mago Negro ergue a mão e a luz do mundo parece hesitar.');
        gameState.currentEnemy = JSON.parse(JSON.stringify(CREATURES.black_mage));
        updateUI();
    });
}

function twilightEndingChoice() {
    const html = `
        <p style="text-align:center">O Mago Negro caiu. O trono do Crepúsculo está vazio — e o da Aurora, velho e cansado.</p>
        <p style="text-align:center;color:#a39bb8">Nem Orion, nem Aldric, nem Alaric souberam escolher sem sangue. Agora é a sua vez.</p>
        <div style="display:flex;flex-direction:column;gap:10px;margin-top:16px">
            <button class="action-btn" onclick="tbChooseEnding('twilight')">🌑 Assumir o Reino do Crepúsculo</button>
            <button class="action-btn" onclick="tbChooseEnding('aurora')">☀️ Entregar o Crepúsculo a um amigo da Aurora</button>
            <button class="action-btn success" onclick="tbChooseEnding('unify')">🤝 Unificar os reinos</button>
        </div>`;
    StoryModal.fire({
        title: '👑 O Fim de Uma Era',
        html,
        icon: 'question',
        showConfirmButton: false,
        showCloseButton: true,
        allowOutsideClick: false,
    });
}

function tbChooseEnding(ending) {
    gameState.ending = ending;
    const texts = {
        twilight: '🌑 Você assume o trono do Crepúsculo. A sombra aprende o seu nome.',
        aurora: '☀️ Você entrega o Crepúsculo a alguém que ainda acredita em fronteiras. A Aurora respira.',
        unify: '🤝 Você derruba as muralhas. Talvez a paz de Orion possa nascer de novo — ou o mundo só saiba viver entre sol e penumbra.',
    };
    addLog(texts[ending] || 'Sua escolha ecoa pelo reino.');
    StoryModal.fire({ title: 'Fim da campanha', text: texts[ending], icon: 'success' });
    TB_checkAchievements();
}

// ══════════════════════════════════════════════════════════════════════
// 9. DIÁRIO / BESTIÁRIO / CONQUISTAS (UI)
// ══════════════════════════════════════════════════════════════════════

function TB_questAvailable(id) {
    const q = QUESTS[id];
    if (!q) return { ok: false, reason: 'Missão inexistente' };
    if (gameState.activeQuest && gameState.activeQuest.id === id) return { ok: false, reason: 'Em andamento' };
    if (gameState.completedQuests && gameState.completedQuests.includes(id) && !q.repeatable) return { ok: false, reason: 'Completada' };
    const r = q.requires || {};
    const lvl = (gameState.character && gameState.character.level) || 1;
    if (r.level && lvl < r.level) return { ok: false, reason: `Requer nível ${r.level}` };
    if (r.quests) {
        for (const req of r.quests) {
            if (!(gameState.completedQuests || []).includes(req)) return { ok: false, reason: 'Requer: ' + ((QUESTS[req] && QUESTS[req].name) || req) };
        }
    }
    return { ok: true };
}

function TB_journalNav(active) {
    const tabs = [
        { id: 'quests', label: '📜 Missões' },
        { id: 'bestiary', label: '📕 Bestiário' },
        { id: 'achievements', label: '🏆 Conquistas' },
    ];
    return '<div style="display:flex;gap:8px;justify-content:center;margin-bottom:12px;flex-wrap:wrap">' +
        tabs.map(t => `<button class="action-btn ${t.id === active ? 'success' : ''}" style="padding:6px 12px;font-size:13px" onclick="showJournalTab('${t.id}')">${t.label}</button>`).join('') +
        '</div>';
}

function showJournalTab(tab) {
    if (tab === 'bestiary') return showBestiary();
    if (tab === 'achievements') return showAchievements();
    return showQuestJournal();
}

function showJournalModal() { return showQuestJournal(); }

function showQuestJournal() {
    TB_ensureState();
    let html = TB_journalNav('quests');
    const aq = gameState.activeQuest && gameState.activeQuest.id ? QUESTS[gameState.activeQuest.id] : null;
    if (aq) {
        const idx = gameState.activeQuest.currentStage || 0;
        const stage = aq.stages[idx];
        const prog = (gameState.activeQuest.stageProgress && gameState.activeQuest.stageProgress[idx]) || 0;
        html += `<div style="background:rgba(240,193,75,.12);border-left:4px solid #f0c14b;border-radius:10px;padding:12px;margin-bottom:12px;text-align:left">`;
        html += `<div style="font-weight:700;color:#f0c14b">${aq.name}</div>`;
        html += `<div style="font-size:12px;color:#a39bb8">Estágio ${idx + 1}/${aq.stages.length}: ${stage.name}</div>`;
        html += `<div style="font-size:12px;margin-top:6px">${stage.description}</div>`;
        html += `<div style="font-size:12px;color:#5ee7ff;margin-top:4px">Progresso: ${Math.min(prog, stage.required)}/${stage.required}</div>`;
        if (stage.hints) html += `<div style="font-size:11px;color:#3ddc97;margin-top:4px">💡 ${stage.hints}</div>`;
        html += `<div style="margin-top:8px"><button class="action-btn" style="padding:6px 12px" onclick="abandonCurrentQuest(); showJournalTab('quests')">Abandonar</button></div>`;
        html += `</div>`;
    } else {
        html += `<div style="text-align:center;color:#a39bb8;margin-bottom:12px">Nenhuma missão ativa. Fale com o Rei, o Capitão ou use o Quadro de Missões.</div>`;
    }
    html += `<div style="max-height:340px;overflow-y:auto;text-align:left">`;
    for (const [id, q] of Object.entries(QUESTS)) {
        const avail = TB_questAvailable(id);
        const done = (gameState.completedQuests || []).includes(id);
        const color = done ? '#3ddc97' : (gameState.activeQuest && gameState.activeQuest.id === id ? '#f0c14b' : (avail.ok ? '#5ee7ff' : '#888'));
        html += `<div style="background:rgba(0,0,0,.3);border-left:4px solid ${color};border-radius:10px;padding:10px;margin-bottom:8px">`;
        html += `<div style="font-weight:700">${q.name}</div>`;
        html += `<div style="font-size:11px;color:${color}">${done ? '✅ Completada' : (gameState.activeQuest && gameState.activeQuest.id === id ? '📌 Em andamento' : (avail.ok ? '✨ Disponível' : '🔒 ' + avail.reason))}</div>`;
        html += `<div style="font-size:11px;color:#a39bb8;margin-top:4px">${q.description}</div>`;
        if (avail.ok) html += `<div style="margin-top:6px"><button class="action-btn success" style="padding:5px 12px;font-size:12px" onclick="acceptQuest('${id}'); showJournalTab('quests')">Aceitar</button></div>`;
        html += `</div>`;
    }
    html += `</div>`;
    StoryModal.fire({ title: '📖 Diário de Missões', html, icon: 'info', showConfirmButton: false, showCloseButton: true, width: '620px' });
}

function showBestiary() {
    TB_ensureState();
    let html = TB_journalNav('bestiary');
    html += '<div style="max-height:420px;overflow-y:auto;text-align:left">';
    const ids = Object.keys(CREATURES);
    let discovered = 0;
    for (const id of ids) {
        const c = CREATURES[id];
        const kills = gameState.stats.killsByType[id] || 0;
        if (kills > 0) discovered++;
        html += `<div style="background:rgba(0,0,0,.3);border-radius:10px;padding:10px;margin-bottom:8px;${kills ? '' : 'opacity:.5'}">`;
        html += `<div style="font-weight:700">${c.emoji || '❔'} ${kills ? c.name : '???'}</div>`;
        if (kills) {
            html += `<div style="font-size:11px;color:#a39bb8">❤️ ${c.life} · ⚔️ ${c.attack} · 🛡️ ${c.defense}</div>`;
            html += `<div style="font-size:11px;color:#3ddc97">Derrotados: ${kills}</div>`;
            if (c.drops && c.drops.length) html += `<div style="font-size:11px;color:#f0c14b">Drops: ${c.drops.map(d => (ITEMS[d] && ITEMS[d].name) || d).join(', ')}</div>`;
        } else {
            html += `<div style="font-size:11px;color:#888">Ainda não registrado.</div>`;
        }
        html += `</div>`;
    }
    html += '</div>';
    StoryModal.fire({ title: `📕 Bestiário (${discovered}/${ids.length})`, html, icon: 'info', showConfirmButton: false, showCloseButton: true, width: '620px' });
}

function showAchievements() {
    TB_ensureState();
    let html = TB_journalNav('achievements');
    const unlocked = TB_ACHIEVEMENTS.filter(a => gameState.achievements[a.id]).length;
    html += `<div style="text-align:center;color:#a39bb8;margin-bottom:10px">${unlocked}/${TB_ACHIEVEMENTS.length} desbloqueadas</div>`;
    html += '<div style="max-height:420px;overflow-y:auto;text-align:left">';
    for (const a of TB_ACHIEVEMENTS) {
        const got = !!gameState.achievements[a.id];
        html += `<div style="background:rgba(0,0,0,.3);border-radius:10px;padding:10px;margin-bottom:8px;${got ? '' : 'opacity:.55'}">`;
        html += `<div style="font-weight:700">${got ? '🏆' : '🔒'} ${a.icon} ${a.name}</div>`;
        html += `<div style="font-size:11px;color:#a39bb8">${a.desc}</div>`;
        html += `</div>`;
    }
    html += '</div>';
    StoryModal.fire({ title: '🏆 Conquistas', html, icon: 'info', showConfirmButton: false, showCloseButton: true, width: '620px' });
}

// ══════════════════════════════════════════════════════════════════════
// 10. HUD (tracker de missão, clima, botão do diário)
// ══════════════════════════════════════════════════════════════════════

function TB_ensureHud() {
    if (!document.body) return;
    // Botão do diário no cabeçalho
    const sl = document.querySelector('.save-load-buttons');
    if (sl && !document.getElementById('tb-journal-btn')) {
        const b = document.createElement('button');
        b.id = 'tb-journal-btn';
        b.type = 'button';
        b.className = 'profile-btn';
        b.title = 'Diário (Missões, Bestiário, Conquistas)';
        b.textContent = '📖';
        b.onclick = showJournalModal;
        sl.insertBefore(b, sl.firstChild);
    }
    // Painel flutuante de missão
    if (!document.getElementById('tb-quest-tracker')) {
        const t = document.createElement('div');
        t.id = 'tb-quest-tracker';
        t.style.cssText = 'position:fixed;left:12px;bottom:12px;z-index:800;max-width:320px;padding:10px 12px;border-radius:14px;background:rgba(14,11,28,.92);border:1px solid rgba(255,215,120,.35);box-shadow:0 12px 32px rgba(0,0,0,.45);font-size:12px;color:#f4f0ff;cursor:pointer;display:none';
        t.title = 'Clique para abrir o Diário';
        t.onclick = showJournalModal;
        document.body.appendChild(t);
    }
}

function TB_updateHud() {
    if (typeof gameState === 'undefined' || !gameState.character) return;
    TB_ensureHud();

    // Clima no topo do painel "🗺️ Mundo" (junto de localização e dia)
    const weatherEl = document.getElementById('world-weather');
    if (weatherEl) {
        const weather = TB_weather();
        weatherEl.textContent = `${weather.icon} ${weather.name}`;
        weatherEl.title = weather.name;
    }

    // Tracker de missão
    const t = document.getElementById('tb-quest-tracker');
    if (!t) return;
    const aq = gameState.activeQuest && gameState.activeQuest.id ? QUESTS[gameState.activeQuest.id] : null;
    if (!aq || gameState.isDead) { t.style.display = 'none'; return; }
    const idx = gameState.activeQuest.currentStage || 0;
    const stage = aq.stages[idx];
    const prog = (gameState.activeQuest.stageProgress && gameState.activeQuest.stageProgress[idx]) || 0;
    t.style.display = 'block';
    t.innerHTML =
        `<div style="font-weight:700;color:#f0c14b">${aq.name}</div>` +
        `<div style="color:#a39bb8;margin-top:2px">${stage.name} · ${Math.min(prog, stage.required)}/${stage.required}</div>` +
        `<div style="color:#5ee7ff;font-size:11px;margin-top:4px">📖 Abrir diário</div>`;
}

// ══════════════════════════════════════════════════════════════════════
// 11. WRAPPERS (envolvem funções do script principal)
// ══════════════════════════════════════════════════════════════════════

// updateUI: garante estado + atualiza HUD
const TB_origUpdateUI = updateUI;
updateUI = function () {
    TB_ensureState();
    const r = TB_origUpdateUI.apply(this, arguments);
    try { TB_updateHud(); } catch (e) { /* noop */ }
    return r;
};

// updateGameContent: injeta botão de habilidade e emoji correto
const TB_origUpdateGameContent = updateGameContent;
updateGameContent = function () {
    const r = TB_origUpdateGameContent.apply(this, arguments);
    try { TB_injectCombatExtras(); } catch (e) { /* noop */ }
    return r;
};

function TB_injectCombatExtras() {
    const content = document.getElementById('game-content');
    if (!content || !gameState.currentEnemy) return;
    const attackBtn = content.querySelector('button[onclick="attack()"]');
    if (!attackBtn) return;
    const row = attackBtn.parentElement;
    if (!row.querySelector('.tb-skill-btn')) {
        const skill = TB_skillOf(gameState.character.race);
        if (skill) {
            const btn = document.createElement('button');
            btn.className = 'action-btn tb-skill-btn';
            btn.style.cssText = 'flex:1;padding:15px;font-size:18px;background:linear-gradient(135deg,#9b7bff,#5ee7ff);color:#120b22;border:none;';
            btn.textContent = `${skill.icon} ${skill.name} (${skill.cost}🔮)`;
            btn.onclick = useSkill;
            row.appendChild(btn);
        }
    }
    // Emoji da criatura
    const def = CREATURES[gameState.currentEnemy.id];
    if (def && def.emoji) {
        const emojiDiv = content.querySelector('div[style*="font-size: 48px"]');
        if (emojiDiv) emojiDiv.textContent = def.emoji;
    }
}

// attack: detecta abate para o bestiário/conquistas
const TB_origAttack = attack;
attack = function () {
    const enemyBefore = gameState.currentEnemy ? { id: gameState.currentEnemy.id } : null;
    const r = TB_origAttack.apply(this, arguments);
    if (enemyBefore && !gameState.currentEnemy && !gameState.isDead) {
        TB_onKill(enemyBefore.id);
    }
    return r;
};

// applyDamageWithArmor: esquiva anula o golpe; tempestade aumenta o dano
const TB_origApplyDamage = applyDamageWithArmor;
applyDamageWithArmor = function (incomingDamage) {
    if (gameState._evasionActive) {
        gameState._evasionActive = false;
        addLog(`💨 Você esquivou completamente do ataque! (${incomingDamage} de dano evitado)`);
        return { totalAbsorbed: incomingDamage, remainingDamage: 0 };
    }
    const mult = TB_weather().damageMult || 1;
    const adjusted = Math.max(1, Math.round(incomingDamage * mult));
    return TB_origApplyDamage.call(this, adjusted);
};

// Progressão / progresso de conquistas
const TB_origAddExperience = addExperience;
addExperience = function () {
    const r = TB_origAddExperience.apply(this, arguments);
    try { TB_checkAchievements(); } catch (e) { /* noop */ }
    return r;
};

const TB_origAddItem = addItemToInventory;
addItemToInventory = function () {
    const r = TB_origAddItem.apply(this, arguments);
    try { TB_checkAchievements(); } catch (e) { /* noop */ }
    return r;
};

const TB_origCraftItem = craftItem;
craftItem = function (recipeId) {
    const before = gameState.inventory.slice();
    const r = TB_origCraftItem.apply(this, arguments);
    try {
        if (recipeId) {
            gameState.stats.crafted = (gameState.stats.crafted || 0) + 1;
            gameState.stats.recipes[recipeId] = true;
        }
        TB_checkAchievements();
    } catch (e) { /* noop */ }
    return r;
};

const TB_origUseFood = useFood;
useFood = function () {
    const r = TB_origUseFood.apply(this, arguments);
    try { gameState.stats.foods = (gameState.stats.foods || 0) + 1; TB_checkAchievements(); } catch (e) { /* noop */ }
    return r;
};

const TB_origOpenBook = openBook;
openBook = function () {
    const r = TB_origOpenBook.apply(this, arguments);
    try { gameState.stats.books = (gameState.stats.books || 0) + 1; TB_checkAchievements(); } catch (e) { /* noop */ }
    return r;
};

const TB_origTalkToNPC = talkToNPC;
talkToNPC = function (npcId) {
    try {
        if (npcId) {
            TB_ensureState();
            gameState.stats.npcs[npcId] = true;
            // O motor escuta 'npc_talk' para missões do tipo talk_to_npc.
            // (Bug original: o evento nunca era disparado, então essas missões travavam.)
            trigger('npc_talk', { npcId: npcId });
            TB_checkAchievements();
        }
    } catch (e) { /* noop */ }
    return TB_origTalkToNPC.apply(this, arguments);
};

// getCreatureName: usa o nome/emoji real das criaturas novas (goblin, orc, esqueleto, Mago Negro...)
const TB_origGetCreatureName = getCreatureName;
getCreatureName = function (creatureId) {
    try {
        if (creatureId && typeof CREATURES !== 'undefined' && CREATURES[creatureId]) {
            const c = CREATURES[creatureId];
            return `${c.emoji || ''} ${c.name}`.trim();
        }
    } catch (e) { /* noop */ }
    return TB_origGetCreatureName.apply(this, arguments);
};

const TB_origBuyItem = buyItem;
buyItem = function () {
    const r = TB_origBuyItem.apply(this, arguments);
    try { gameState.stats.purchases = (gameState.stats.purchases || 0) + 1; TB_checkAchievements(); } catch (e) { /* noop */ }
    return r;
};

const TB_origOpenStation = openStation;
openStation = function () {
    const r = TB_origOpenStation.apply(this, arguments);
    try { TB_checkAchievements(); } catch (e) { /* noop */ }
    return r;
};

const TB_origStartSleep = startSleep;
startSleep = function () {
    const r = TB_origStartSleep.apply(this, arguments);
    try { gameState.stats.sleeps = (gameState.stats.sleeps || 0) + 1; TB_checkAchievements(); } catch (e) { /* noop */ }
    return r;
};

const TB_origCompleteQuest = completeQuest;
completeQuest = function (questId) {
    const r = TB_origCompleteQuest.apply(this, arguments);
    try {
        if (r) { gameState.stats.questsCompleted = (gameState.stats.questsCompleted || 0) + 1; TB_checkAchievements(); }
    } catch (e) { /* noop */ }
    return r;
};

// acceptQuest: respeita pré-requisitos do diário
const TB_origAcceptQuest = acceptQuest;
acceptQuest = function (questId) {
    const avail = TB_questAvailable(questId);
    if (!avail.ok && !(gameState.activeQuest && gameState.activeQuest.id === questId)) {
        addLog(`🔒 Não pode aceitar "${QUESTS[questId] ? QUESTS[questId].name : questId}": ${avail.reason}.`);
        return false;
    }
    return TB_origAcceptQuest.apply(this, arguments);
};

// showQuestBoard: usa o diário novo
showQuestBoard = function () { showQuestJournal(); };

// toggleTimeOfDay: ao amanhecer, sorteia clima e checa conquistas
const TB_origToggleTimeOfDay = toggleTimeOfDay;
toggleTimeOfDay = function () {
    const yearBefore = gameState.yearCount;
    const r = TB_origToggleTimeOfDay.apply(this, arguments);
    try {
        TB_ensureState();
        gameState.weather = TB_rollWeather();
        if (gameState.yearCount > yearBefore) {
            gameState.stats.yearAdvances = (gameState.stats.yearAdvances || 0) + 1;
            gameState.stats.years = gameState.yearCount;
        }
        TB_checkAchievements();
        TB_updateHud();
    } catch (e) { /* noop */ }
    return r;
};

// Exploração: substitui o comportamento de "beco sem saída"
exploreDarkForest = function () {
    if (gameState.isDead) return;
    if (gameState.currentEnemy) return;
    if (TB_spawnEncounterFor('dark_forest')) { updateUI(); return; }
    addLog('🌲 A floresta está silenciosa... por enquanto.');
    if (Math.random() < 0.3) {
        const finds = ['apple', 'bread', 'wood'];
        const find = finds[Math.floor(Math.random() * finds.length)];
        addItemToInventory(find);
        addLog(`🍄 Você encontrou ${ITEMS[find].name} perto de uma árvore caída!`);
    }
    updateUI();
};

continueEast = function () { go('east_wilds', '➡️ O caminho leste leva a um descampado pedregoso: as Terras Selvagens.'); };
continueEastFromRuins = function () { go('east_ruins_camp', '➡️ O caminho termina num acampamento abandonado entre as ruínas.'); };

// Encontros nos locais que já tinham ações de exploração
const TB_origSearchRuins = searchRuins;
searchRuins = function () {
    if (gameState.isDead) return;
    if (TB_spawnEncounterFor('ancient_ruins')) { updateUI(); return; }
    return TB_origSearchRuins.apply(this, arguments);
};

// ══════════════════════════════════════════════════════════════════════
// 12. BOOT
// ══════════════════════════════════════════════════════════════════════

(function TB_boot() {
    function ready() {
        try {
            TB_ensureState();
            TB_ensureHud();
            if (gameState && gameState.character) TB_updateHud();
        } catch (e) { /* noop */ }
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', ready);
    } else {
        ready();
    }
})();
