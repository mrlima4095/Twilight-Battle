/*
 * Twilight Battle — Modo História
 * Módulo de sobrevivência: FOME e SEDE.
 * ------------------------------------------------------------------
 * Carregado DEPOIS de systems.js. Assim como ele, este módulo NÃO
 * reescreve o jogo: apenas estende o estado (gameState), o HUD e
 * envolve (wrap) algumas funções existentes.
 *
 * Regras:
 *   - Fome (🍗) e Sede (💧) vão de 0 a 100.
 *   - Caem com o tempo (tick), ao viajar, ao lutar e a cada virada de
 *     dia/noite (dormir acelera isso, pois avança ciclos).
 *   - Comer restaura Fome; beber restaura Sede.
 *   - Fome em 0 causa dano de inanição; Sede em 0 causa dano de
 *     desidratação. Fome/Sede baixas aparecem em vermelho no HUD.
 */

// ══════════════════════════════════════════════════════════════════════
// 1. CONSTANTES / AJUSTES
// ══════════════════════════════════════════════════════════════════════

const SV_MAX = 100;
const SV_TICK_MS = 5000;
const SV_HUNGER_PER_TICK = 0.12;   // ~3,5 dias de jogo do cheio ao vazio
const SV_THIRST_PER_TICK = 0.16;   // ~2,6 dias de jogo do cheio ao vazio
const SV_TRAVEL_COST = { hunger: 0.5, thirst: 0.7 };
const SV_TRAVEL_MANA = 0.5;        // mana acumulada por passo (1 mana a cada 2 passos)
const SV_COMBAT_COST = { hunger: 0.4, thirst: 0.5 };
const SV_NIGHT_COST = { hunger: 5, thirst: 6 };
const SV_STARVE_DAMAGE = 0.015;    // fração da vida máxima por tick com fome 0
const SV_DEHYDRATE_DAMAGE = 0.02;  // fração da vida máxima por tick com sede 0

// Sanidade (🧠): 0–100. Cai com bebidas alcoólicas e turva a mente —
// magias podem falhar e o desempenho em combate piora.
const SV_SANITY_REGEN_PER_TICK = 0.06;   // recuperação lenta com o tempo
const SV_SANITY_DAWN = 10;               // clareia a mente a cada virada de dia
const SV_SANITY_FUMBLE_AT = 70;          // abaixo disso, magias podem falhar
const SV_SANITY_MAX_FUMBLE = 0.6;        // chance de falha com sanidade 0
const SV_SANITY_MIN_DAMAGE = 0.55;       // multiplicador de dano com sanidade 0
const SV_ALCOHOL = { beer: 9, wine: 14 };

// A sede baixa e a falta de sono também desgastam a mente:
const SV_THIRST_SANITY_AT = 40;          // sede abaixo disso começa a turvar a mente
const SV_THIRST_SANITY_MAX = 0.22;       // dreno máximo de sanidade por tick (sede 0)
const SV_SLEEP_FLIPS_LIMIT = 2;          // viradas de dia/noite sem dormir até pesar
const SV_SLEEP_SANITY_STEP = 0.10;       // dreno por tick, por virada além do limite
const SV_SLEEP_SANITY_MAX = 0.40;        // teto do dreno por falta de sono

// Quanto cada comida/bebida devolve de Fome e Sede.
// Itens fora da tabela usam uma estimativa pelo tipo (comida/bebida) e cura.
const SV_NUTRITION = {
    apple: { hunger: 12, thirst: 2 },
    bread: { hunger: 25 },
    fish: { hunger: 15, thirst: 4 },
    cooked_fish: { hunger: 32, thirst: 3 },
    cenoura: { hunger: 10, thirst: 5 },
    wheat_flour: { hunger: 4 },
    bread_dough: { hunger: 6 },
    salt: { thirst: 4 },
    sugar: { hunger: 8 },
    lemon: { hunger: 3, thirst: 16 },
    meat: { hunger: 42 },
    raw_meat: { hunger: 18, thirst: 2 },
    chicken: { hunger: 16 },
    cooked_chicken: { hunger: 36 },
    beer: { hunger: 6, thirst: 26 },
    wine: { hunger: 8, thirst: 22 },
    coffee: { thirst: 32 },
    water_bottle: { thirst: 45 },
};

const SV_LEVELS = [
    { value: 50, flag: 'warn50', icon: '⚠️' },
    { value: 25, flag: 'warn25', icon: '🟠' },
    { value: 10, flag: 'warn10', icon: '🔴' },
    { value: 0, flag: 'warn0', icon: '💀' },
];

// ══════════════════════════════════════════════════════════════════════
// 2. ESTADO
// ══════════════════════════════════════════════════════════════════════

function SV_ensureState() {
    if (typeof gameState === 'undefined' || !gameState) return;
    if (!gameState.survival || typeof gameState.survival !== 'object') {
        gameState.survival = { hunger: SV_MAX, thirst: SV_MAX, sanity: SV_MAX, manaDebt: 0, flipsSinceSleep: 0 };
    }
    const s = gameState.survival;
    if (typeof s.hunger !== 'number' || !isFinite(s.hunger)) s.hunger = SV_MAX;
    if (typeof s.thirst !== 'number' || !isFinite(s.thirst)) s.thirst = SV_MAX;
    if (typeof s.sanity !== 'number' || !isFinite(s.sanity)) s.sanity = SV_MAX;
    if (typeof s.flipsSinceSleep !== 'number' || !isFinite(s.flipsSinceSleep)) s.flipsSinceSleep = 0;
    s.hunger = Math.max(0, Math.min(SV_MAX, s.hunger));
    s.thirst = Math.max(0, Math.min(SV_MAX, s.thirst));
    s.sanity = Math.max(0, Math.min(SV_MAX, s.sanity));
    if (!s.flags || typeof s.flags !== 'object') {
        s.flags = { hunger: {}, thirst: {}, sanity: {} };
        SV_seedFlags('hunger', s);
        SV_seedFlags('thirst', s);
        SV_seedFlags('sanity', s);
    }
    s.flags.hunger = s.flags.hunger || {};
    s.flags.thirst = s.flags.thirst || {};
    s.flags.sanity = s.flags.sanity || {};
    s.flags.extra = s.flags.extra || {};
}

// Marca (em silêncio) os limites que o valor atual já cruzou — evita uma
// enxurrada de avisos ao carregar um save com fome/sede baixas.
function SV_seedFlags(key, s) {
    for (const lvl of SV_LEVELS) {
        if (s[key] <= lvl.value) s.flags[key][lvl.flag] = true;
    }
}

function SV_reset() {
    if (typeof gameState === 'undefined' || !gameState) return;
    gameState.survival = { hunger: SV_MAX, thirst: SV_MAX, sanity: SV_MAX, manaDebt: 0, flipsSinceSleep: 0, flags: { hunger: {}, thirst: {}, sanity: {}, extra: {} } };
}

// ══════════════════════════════════════════════════════════════════════
// 3. NÚCLEO (aplicar/consumir)
// ══════════════════════════════════════════════════════════════════════

// Aplica deltas (positivos = recupera, negativos = gasta) e atualiza HUD.
function SV_apply(hungerDelta, thirstDelta, opts) {
    SV_ensureState();
    if (!gameState.character || gameState.isDead) return;
    const s = gameState.survival;
    const beforeH = s.hunger;
    const beforeT = s.thirst;
    s.hunger = Math.max(0, Math.min(SV_MAX, s.hunger + (hungerDelta || 0)));
    s.thirst = Math.max(0, Math.min(SV_MAX, s.thirst + (thirstDelta || 0)));
    SV_checkThresholds();
    SV_updateHud();
    return { hunger: s.hunger - beforeH, thirst: s.thirst - beforeT };
}

function SV_spend(hunger, thirst) {
    if (typeof gameState === 'undefined' || !gameState || !gameState.character || gameState.isDead) return;
    SV_apply(-(hunger || 0), -(thirst || 0));
}

// Aplica um delta de sanidade (+ recupera, - gasta) e atualiza HUD/avisos.
function SV_applySanity(delta) {
    SV_ensureState();
    if (!gameState.character || gameState.isDead) return;
    const s = gameState.survival;
    s.sanity = Math.max(0, Math.min(SV_MAX, s.sanity + (delta || 0)));
    SV_checkThresholds();
    SV_updateHud();
}

// Efeitos da sanidade no combate: chance de falha em magias e multiplicador de dano.
function SV_sanityEffects() {
    SV_ensureState();
    const sanity = (gameState.survival && gameState.survival.sanity) || 0;
    const fumbleChance = sanity >= SV_SANITY_FUMBLE_AT
        ? 0
        : Math.min(SV_SANITY_MAX_FUMBLE, ((SV_SANITY_FUMBLE_AT - sanity) / SV_SANITY_FUMBLE_AT) * SV_SANITY_MAX_FUMBLE);
    const damageMult = Math.max(SV_SANITY_MIN_DAMAGE, Math.min(1, SV_SANITY_MIN_DAMAGE + sanity * ((1 - SV_SANITY_MIN_DAMAGE) / SV_MAX)));
    return { sanity, fumbleChance, damageMult };
}

// Gasta mana em frações acumuladas (ex.: andar 0,5 por passo → 1 a cada 2 passos),
// mantendo o valor de mana sempre inteiro no HUD.
function SV_spendMana(amount) {
    if (typeof gameState === 'undefined' || !gameState || !gameState.character || gameState.isDead) return;
    if (typeof gameState.character.mana !== 'number' || amount <= 0) return;
    SV_ensureState();
    const s = gameState.survival;
    if (typeof s.manaDebt !== 'number' || !isFinite(s.manaDebt)) s.manaDebt = 0;
    s.manaDebt += amount;
    const whole = Math.floor(s.manaDebt);
    if (whole <= 0) return;
    s.manaDebt -= whole;
    const before = gameState.character.mana;
    gameState.character.mana = Math.max(0, before - whole);
    if (gameState.character.mana !== before) {
        const el = document.getElementById('player-mana');
        if (el) el.textContent = `${gameState.character.mana}/${gameState.character.maxMana}`;
    }
}

// Restaura Fome/Sede a partir de um item consumível.
function SV_applyNutrition(item) {
    if (!item) return;
    const table = SV_NUTRITION[item.id];
    let hunger = 0;
    let thirst = 0;

    if (table) {
        hunger = table.hunger || 0;
        thirst = table.thirst || 0;
    } else if (item.type === 'drink') {
        thirst = Math.max(12, Math.round((item.mana || 0) * 1.5));
    } else if (item.type === 'food') {
        hunger = Math.max(3, Math.round((item.heal || 0) / 3));
    }

    if (!hunger && !thirst) return;
    SV_apply(hunger, thirst);
    if (hunger > 0 && thirst > 0) addLog(`🍗 Fome +${hunger} · 💧 Sede +${thirst}`);
    else if (hunger > 0) addLog(`🍗 Fome +${hunger}`);
    else addLog(`💧 Sede +${thirst}`);
}

// Avisos por faixa (uma vez cada) quando Fome/Sede/Sanidade cruzam os limites.
function SV_checkThresholds() {
    const s = gameState.survival;
    if (!s) return;
    SV_warnFor('hunger', '🍗 Sua fome', s, { zero: 'Você está faminto e perde vida.', hint: 'Coma algo!' });
    SV_warnFor('thirst', '💧 Sua sede', s, { zero: 'Você está desidratado e perde vida.', hint: 'Beba algo!' });
    SV_warnFor('sanity', '🧠 Sua sanidade', s, { zero: 'Sua mente se perde: magias falham e o combate fica instável.', hint: 'Durma ou evite bebidas alcoólicas!' });
}

function SV_warnFor(key, label, s, msgs) {
    const value = s[key];
    const flags = s.flags[key];
    for (const lvl of SV_LEVELS) {
        if (value <= lvl.value) {
            if (!flags[lvl.flag]) {
                flags[lvl.flag] = true;
                if (lvl.value === 0) {
                    addLog(`${lvl.icon} ${label} chegou a ZERO! ${msgs.zero}`);
                } else {
                    addLog(`${lvl.icon} ${label} está em ${Math.floor(value)}/100. ${msgs.hint}`);
                }
            }
        } else {
            // Volta a "armar" o aviso quando sobe acima do limite novamente.
            flags[lvl.flag] = false;
        }
    }
}

// Quanto a sede baixa e a falta de sono drenam da sanidade a cada tick.
function SV_sanityDrain() {
    const s = gameState.survival;
    let drain = 0;

    const thirstLow = s.thirst < SV_THIRST_SANITY_AT;
    if (thirstLow) {
        drain += ((SV_THIRST_SANITY_AT - s.thirst) / SV_THIRST_SANITY_AT) * SV_THIRST_SANITY_MAX;
    }
    const flipsOver = Math.max(0, (s.flipsSinceSleep || 0) - SV_SLEEP_FLIPS_LIMIT);
    const noSleep = flipsOver > 0;
    if (noSleep) {
        drain += Math.min(SV_SLEEP_SANITY_MAX, flipsOver * SV_SLEEP_SANITY_STEP);
    }

    // Avisa apenas uma vez ao entrar em cada situação (e rearma ao sair).
    s.flags.extra = s.flags.extra || {};
    if (thirstLow && !s.flags.extra.thirstSanity) {
        s.flags.extra.thirstSanity = true;
        addLog('🧠 A sede turva sua mente — beba água! (🧠 Sanidade caindo)');
    } else if (!thirstLow) {
        s.flags.extra.thirstSanity = false;
    }
    if (noSleep && !s.flags.extra.sleepSanity) {
        s.flags.extra.sleepSanity = true;
        addLog('🧠 Você está há muito tempo sem dormir — a mente se desgasta. (🧠 Sanidade caindo)');
    } else if (!noSleep) {
        s.flags.extra.sleepSanity = false;
    }

    return drain;
}

// ══════════════════════════════════════════════════════════════════════
// 4. TICK DE TEMPO (decaimento contínuo)
// ══════════════════════════════════════════════════════════════════════

function SV_tick() {
    if (typeof gameState === 'undefined' || !gameState || !gameState.character) return;
    if (gameState.isDead) return;
    SV_ensureState();

    SV_spend(SV_HUNGER_PER_TICK, SV_THIRST_PER_TICK);
    // Sanidade: recupera devagar, mas a sede baixa e a falta de sono pesam mais.
    SV_applySanity(SV_SANITY_REGEN_PER_TICK - SV_sanityDrain());

    const s = gameState.survival;
    if (!s) return;

    let damage = 0;
    if (s.hunger <= 0) damage += Math.ceil(gameState.character.maxLife * SV_STARVE_DAMAGE);
    if (s.thirst <= 0) damage += Math.ceil(gameState.character.maxLife * SV_DEHYDRATE_DAMAGE);

    if (damage > 0) {
        gameState.character.life = Math.max(0, gameState.character.life - damage);
        addLog(`💀 Você perde ${damage} de vida por ${s.hunger <= 0 && s.thirst <= 0 ? 'fome e sede' : (s.hunger <= 0 ? 'inanição' : 'desidratação')}!`);
        if (gameState.character.life <= 0) {
            if (typeof playerDeath === 'function') playerDeath();
            return;
        }
        updateUI();
    }
}

// ══════════════════════════════════════════════════════════════════════
// 5. HUD
// ══════════════════════════════════════════════════════════════════════

function SV_injectStyle() {
    if (document.getElementById('sv-style')) return;
    const style = document.createElement('style');
    style.id = 'sv-style';
    style.textContent = `
#sv-bars {
    display:flex; flex-wrap:wrap; align-items:center; gap:8px 22px;
    width:100%; padding:9px 16px; border-radius:14px;
    background:linear-gradient(135deg, rgba(16,13,30,.9), rgba(10,8,20,.92));
    border:1px solid rgba(255,255,255,.1); box-shadow:0 8px 22px rgba(0,0,0,.25);
}
#sv-bars .sv-bar { flex:1 1 240px; display:flex; align-items:center; gap:10px; min-width:0; }
#sv-bars .sv-label { flex:0 0 auto; font-size:.72rem; color:var(--muted,#a39bb8); white-space:nowrap; }
#sv-bars .sv-pct { flex:0 0 auto; min-width:38px; text-align:right; font-size:.72rem; font-weight:700; color:var(--gold,#f0c14b); font-variant-numeric:tabular-nums; }
#sv-bars .sv-track { flex:1 1 auto; min-width:50px; height:8px; border-radius:999px; background:rgba(0,0,0,.45); border:1px solid rgba(255,255,255,.08); overflow:hidden; }
#sv-bars .sv-fill { height:100%; width:100%; border-radius:999px; background:#3ddc97; transition:width .4s ease, background .4s ease; }
#sv-bars .sv-fill.sv-mid { background:#f0c14b; }
#sv-bars .sv-fill.sv-low { background:#ff4d6d; animation:pulse 1s ease infinite; }
`;
    document.head.appendChild(style);
}

function SV_ensureHud() {
    if (!document.body) return;
    SV_injectStyle();

    // Fome/Sede ficam numa faixa própria (largura total) logo abaixo do topo do
    // HUD, em vez de disputar espaço com os stats. Não duplicamos como "stat".
    const host = document.querySelector('#game-ui .game-header')
        || document.querySelector('#game-ui .player-info');
    if (host && !document.getElementById('sv-bars')) {
        const bars = document.createElement('div');
        bars.id = 'sv-bars';
        bars.innerHTML = SV_barHtml('hunger', '🍗 Fome') + SV_barHtml('thirst', '💧 Sede') + SV_barHtml('sanity', '🧠 Sanidade');
        host.appendChild(bars);
    }
}

function SV_barHtml(id, label) {
    return `<div class="sv-bar">
        <span class="sv-label">${label}</span>
        <div class="sv-track"><div class="sv-fill" id="sv-${id}-fill"></div></div>
        <span class="sv-pct" id="sv-${id}-pct">100%</span>
    </div>`;
}

function SV_updateHud() {
    if (typeof gameState === 'undefined' || !gameState || !gameState.character) return;
    SV_ensureHud();
    const s = gameState.survival || { hunger: SV_MAX, thirst: SV_MAX, sanity: SV_MAX };
    SV_renderStat('hunger', s.hunger);
    SV_renderStat('thirst', s.thirst);
    SV_renderStat('sanity', s.sanity);
}

function SV_renderStat(id, value) {
    const v = Math.round(value);
    const fill = document.getElementById(`sv-${id}-fill`);
    if (fill) {
        fill.style.width = `${Math.max(0, Math.min(100, value))}%`;
        fill.classList.toggle('sv-mid', value > 20 && value <= 50);
        fill.classList.toggle('sv-low', value <= 20);
    }
    const pct = document.getElementById(`sv-${id}-pct`);
    if (pct) pct.textContent = `${v}%`;
}

// ══════════════════════════════════════════════════════════════════════
// 6. WRAPPERS
// ══════════════════════════════════════════════════════════════════════

// updateUI: garante estado + atualiza o HUD de sobrevivência.
const SV_origUpdateUI = updateUI;
updateUI = function () {
    SV_ensureState();
    const r = SV_origUpdateUI.apply(this, arguments);
    try { SV_updateHud(); } catch (e) { /* noop */ }
    return r;
};

// go: viajar gasta um pouco de fome, sede e mana.
const SV_origGo = go;
go = function () {
    const r = SV_origGo.apply(this, arguments);
    try {
        SV_ensureState();
        SV_spend(SV_TRAVEL_COST.hunger, SV_TRAVEL_COST.thirst);
        SV_spendMana(SV_TRAVEL_MANA);
    } catch (e) { /* noop */ }
    return r;
};

// attack: combate consome energia.
const SV_origAttack = attack;
attack = function () {
    const r = SV_origAttack.apply(this, arguments);
    try { SV_spend(SV_COMBAT_COST.hunger, SV_COMBAT_COST.thirst); } catch (e) { /* noop */ }
    return r;
};

// useFood: aplica nutrição (fome/sede) além da cura original e, no caso de
// bebidas alcoólicas, baixa a sanidade (a mente fica confusa).
const SV_origUseFood = useFood;
useFood = function (index) {
    const item = (gameState.inventory && gameState.inventory[index]) || null;
    const r = SV_origUseFood.apply(this, arguments);
    try {
        if (item && (item.type === 'food' || item.type === 'drink')) SV_applyNutrition(item);
        if (item && SV_ALCOHOL[item.id]) {
            SV_applySanity(-SV_ALCOHOL[item.id]);
            addLog(`🍺 O álcool turva sua mente (🧠 Sanidade −${SV_ALCOHOL[item.id]}). Magias podem falhar!`);
        }
    } catch (e) { /* noop */ }
    return r;
};

// toggleTimeOfDay: cada virada de dia/noite pesa na fome/sede
// (dormir avança ciclos, então descansar também custa) e conta como um
// período a mais sem dormir.
const SV_origToggleTimeOfDay = toggleTimeOfDay;
toggleTimeOfDay = function () {
    const r = SV_origToggleTimeOfDay.apply(this, arguments);
    try {
        SV_spend(SV_NIGHT_COST.hunger, SV_NIGHT_COST.thirst);
        SV_applySanity(SV_SANITY_DAWN); // uma nova virada de dia clareia a mente
        SV_ensureState();
        const s = gameState.survival;
        if (s) s.flipsSinceSleep = (s.flipsSinceSleep || 0) + 1;
    } catch (e) { /* noop */ }
    return r;
};

// completeSleep: dormir zera o "tempo sem dormir" e acalma a mente.
const SV_origCompleteSleep = completeSleep;
completeSleep = function () {
    const r = SV_origCompleteSleep.apply(this, arguments);
    try {
        SV_ensureState();
        const s = gameState.survival;
        if (s) {
            s.flipsSinceSleep = 0;
            s.flags.extra = s.flags.extra || {};
            s.flags.extra.sleepSanity = false;
        }
        SV_applySanity(6); // uma boa noite de sono clareia os pensamentos
    } catch (e) { /* noop */ }
    return r;
};

// createCharacter: um herói novo (ou recriado após morte) começa bem
// alimentado e hidratado, independentemente do save anterior.
const SV_origCreateCharacter = createCharacter;
createCharacter = function () {
    SV_reset();
    const r = SV_origCreateCharacter.apply(this, arguments);
    try { SV_ensureState(); SV_updateHud(); } catch (e) { /* noop */ }
    return r;
};

// ══════════════════════════════════════════════════════════════════════
// 7. ÁGUA POTÁVEL (beber direto da fonte, sem precisar de garrafa)
// ══════════════════════════════════════════════════════════════════════

const SV_WATER_LOCATIONS = [
    'sacred_lake', 'sacred_lake_interior', 'home', 'farmlands', 'river_bank', 'swim_in_river',
];

function SV_hasWaterSource() {
    return !!(gameState && SV_WATER_LOCATIONS.includes(gameState.location));
}

function drinkWater() {
    if (!gameState || gameState.isDead) return;
    if (!SV_hasWaterSource()) {
        addLog('💧 Não há água potável por aqui.');
        return;
    }
    SV_ensureState();
    if (gameState.survival.thirst >= SV_MAX) {
        addLog('💧 Você não está com sede agora.');
        return;
    }
    const before = gameState.survival.thirst;
    SV_apply(0, 60);
    addLog(`💧 Você bebe água fresca e recupera ${Math.round(gameState.survival.thirst - before)} de sede.`);
    updateUI();
}

// Adiciona "💧 Beber água" nas fontes (poço, rio, lago, casa…).
function SV_injectWaterActions() {
    if (typeof LOCATIONS === 'undefined') return;
    for (const id of SV_WATER_LOCATIONS) {
        const loc = LOCATIONS[id];
        if (!loc || !Array.isArray(loc.actions)) continue;
        if (loc.actions.some(a => a.action === 'drinkWater')) continue;
        const action = { name: '💧 Beber água', action: 'drinkWater' };
        const idx = loc.actions.findIndex(a => a.action === 'fillBottle');
        if (idx >= 0) loc.actions.splice(idx + 1, 0, action);
        else loc.actions.push(action);
    }
}

// ══════════════════════════════════════════════════════════════════════
// 8. BOOT
// ══════════════════════════════════════════════════════════════════════

(function SV_boot() {
    function ready() {
        try {
            SV_ensureState();
            SV_ensureHud();
            SV_injectWaterActions();
            if (gameState && gameState.character) SV_updateHud();
        } catch (e) { /* noop */ }
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', ready);
    } else {
        ready();
    }
    setInterval(SV_tick, SV_TICK_MS);
})();
