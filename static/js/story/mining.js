/* ══════════════════════════════════════════════════════════════════════
   MINIGAMES DE COLETA + MINA LABIRINTO
   Carregado depois de story.html (script inline) e survival.js.
   Expõe: tbMinigame, enterMine, mine*, tbChopTree.
   ══════════════════════════════════════════════════════════════════════ */

/* ------------------------------------------------------------------ */
/*  MINIGAME 3D (canvas, SEM bibliotecas)                              */
/*  Cena em perspectiva real: a rocha/árvore gira num "prato" e um     */
/*  anel 3D serve de medidor. Pare o marcador na faixa verde e a       */
/*  ferramenta desce no golpe. Resolve com { success, precision }.     */
/* ------------------------------------------------------------------ */
let _mgState = null;

/* ---- álgebra 3D mínima ---- */
function mg3dVec(x, y, z) { return { x: x, y: y, z: z }; }
function mg3dSub(a, b) { return mg3dVec(a.x - b.x, a.y - b.y, a.z - b.z); }
function mg3dCross(a, b) { return mg3dVec(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x); }
function mg3dNorm(v) { const l = Math.hypot(v.x, v.y, v.z) || 1; return mg3dVec(v.x / l, v.y / l, v.z / l); }
function mg3dRotX(p, a) { const c = Math.cos(a), s = Math.sin(a); return mg3dVec(p.x, p.y * c - p.z * s, p.y * s + p.z * c); }
function mg3dRotY(p, a) { const c = Math.cos(a), s = Math.sin(a); return mg3dVec(p.x * c - p.z * s, p.y, p.x * s + p.z * c); }
function mg3dShade(hex, k) {
    const n = parseInt(hex.slice(1), 16);
    const r = Math.min(255, Math.round(((n >> 16) & 255) * k));
    const g = Math.min(255, Math.round(((n >> 8) & 255) * k));
    const b = Math.min(255, Math.round((n & 255) * k));
    return 'rgb(' + r + ',' + g + ',' + b + ')';
}

/* Faces de um cubo com normais para fora (anti-horário visto de fora). */
const MG3D_BOX_FACES = [[4, 5, 6, 7], [1, 0, 3, 2], [5, 1, 2, 6], [0, 4, 7, 3], [3, 7, 6, 2], [0, 1, 5, 4]];

function mg3dBoxMesh(cx, cy, cz, sx, sy, sz, color) {
    const hx = sx / 2, hy = sy / 2, hz = sz / 2;
    return {
        color: color,
        verts: [
            mg3dVec(cx - hx, cy - hy, cz - hz), mg3dVec(cx + hx, cy - hy, cz - hz),
            mg3dVec(cx + hx, cy + hy, cz - hz), mg3dVec(cx - hx, cy + hy, cz - hz),
            mg3dVec(cx - hx, cy - hy, cz + hz), mg3dVec(cx + hx, cy - hy, cz + hz),
            mg3dVec(cx + hx, cy + hy, cz + hz), mg3dVec(cx - hx, cy + hy, cz + hz)
        ],
        faces: MG3D_BOX_FACES
    };
}

/* ---- cenas ---- */
function mg3dSceneMeshes(kind) {
    if (kind === 'tree') {
        return [
            mg3dBoxMesh(0, -0.15, 0, 1.35, 3.30, 1.35, '#7a5230'),
            mg3dBoxMesh(0, -0.15, 0.70, 0.72, 1.15, 0.08, '#c8a06a'),
            mg3dBoxMesh(0, 2.05, 0, 3.00, 1.60, 3.00, '#3f8f4a'),
            mg3dBoxMesh(-1.00, 1.25, 0.50, 1.70, 1.10, 1.70, '#357b3f'),
            mg3dBoxMesh(1.00, 1.35, -0.50, 1.60, 1.00, 1.60, '#4aa257')
        ];
    }
    return [
        mg3dBoxMesh(0, -0.35, 0, 3.20, 2.30, 2.60, '#6b6157'),
        mg3dBoxMesh(-1.75, -1.05, 0.55, 1.15, 1.05, 1.15, '#5a5148'),
        mg3dBoxMesh(1.75, -1.15, -0.45, 1.25, 0.95, 1.25, '#5a5148'),
        mg3dBoxMesh(0.95, 0.35, 1.33, 0.62, 0.52, 0.08, '#e0a63c'),
        mg3dBoxMesh(-0.85, -0.55, 1.33, 0.85, 0.42, 0.08, '#e0a63c'),
        mg3dBoxMesh(0.15, -1.00, 1.33, 0.50, 0.32, 0.08, '#b9c7d6')
    ];
}

function mg3dToolMeshes(kind) {
    const handle = mg3dBoxMesh(0, 0.85, 0, 0.18, 1.70, 0.18, '#8a5a34');
    if (kind === 'tree') {
        return [handle,
            mg3dBoxMesh(0.60, 1.80, 0, 1.05, 0.62, 0.20, '#c9ced6'),
            mg3dBoxMesh(1.10, 1.80, 0, 0.22, 0.70, 0.24, '#eef2f6')];
    }
    return [handle,
        mg3dBoxMesh(0, 1.82, 0, 1.70, 0.30, 0.32, '#cfd4da'),
        mg3dBoxMesh(-0.95, 1.82, 0, 0.34, 0.20, 0.20, '#aab0b8'),
        mg3dBoxMesh(0.95, 1.82, 0, 0.34, 0.20, 0.20, '#aab0b8')];
}

/* ---- desenho da cena (pintor: face mais distante primeiro) ---- */
function mg3dRender(ctx, W, H, o) {
    const TILT = -0.42, CAMZ = 7.2, FOCAL = Math.min(W * 1.2, 300);
    const CX = W / 2, CY = H * 0.58;
    const light = mg3dNorm(mg3dVec(-0.42, 0.8, -0.55));
    const kind = o.kind, spin = o.spin;

    ctx.clearRect(0, 0, W, H);
    const bg = ctx.createRadialGradient(CX, CY * 0.55, 12, CX, CY, Math.max(W, H));
    bg.addColorStop(0, '#251b3f');
    bg.addColorStop(1, '#0a0712');
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, W, H);

    function toCam(p, withSpin) {
        let q = mg3dRotX(p, TILT);
        if (withSpin) q = mg3dRotY(q, spin);
        return mg3dVec(q.x, q.y, q.z + CAMZ);
    }
    function proj(cp) {
        if (cp.z <= 0.25) return null;
        const s = FOCAL / cp.z;
        return { x: CX + cp.x * s, y: CY - cp.y * s, s: s, z: cp.z };
    }

    /* ---- medidor: anel 3D fixo (HUD) ---- */
    const R = 2.45, RY = -1.85;
    function gaugeProj(v) {
        const a = -Math.PI / 2 + (v / 100) * Math.PI * 2;
        return proj(toCam(mg3dVec(Math.cos(a) * R, RY, Math.sin(a) * R), false));
    }
    ctx.lineCap = 'round';
    ctx.beginPath();
    for (let i = 0; i <= 72; i++) {
        const p = gaugeProj((i / 72) * 100);
        if (!p) continue;
        i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y);
    }
    ctx.lineWidth = 3.5;
    ctx.strokeStyle = 'rgba(255,255,255,.16)';
    ctx.stroke();

    // faixa-alvo
    ctx.beginPath();
    let first = true;
    for (let v = o.zoneStart; v <= o.zoneStart + o.zoneWidth + 0.01; v += 1.2) {
        const p = gaugeProj(Math.min(v, o.zoneStart + o.zoneWidth));
        if (!p) continue;
        first ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y);
        first = false;
    }
    ctx.lineWidth = 9;
    ctx.strokeStyle = 'rgba(76,175,80,.8)';
    ctx.stroke();

    // marcador
    const mp = gaugeProj(o.pos);
    if (mp) {
        const r = Math.max(4.5, mp.s * 0.14);
        const gg = ctx.createRadialGradient(mp.x, mp.y, 0, mp.x, mp.y, r * 3.2);
        gg.addColorStop(0, 'rgba(255,215,0,.95)');
        gg.addColorStop(1, 'rgba(255,215,0,0)');
        ctx.fillStyle = gg;
        ctx.beginPath(); ctx.arc(mp.x, mp.y, r * 3.2, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = '#ffd700';
        ctx.beginPath(); ctx.arc(mp.x, mp.y, r, 0, Math.PI * 2); ctx.fill();
    }

    /* ---- pose da ferramenta (idle / golpe) ---- */
    const st = o.strike;
    const raw = st ? Math.min(1, st.t / 0.55) : 0;
    const ease = raw * raw * (3 - 2 * raw);
    const amt = st ? (st.success ? 1 : 0.55) : 0;
    const k = ease * amt;
    const idle = st ? 0 : Math.sin(spin * 1.6) * 0.05;
    const px = 2.55 + (1.62 - 2.55) * k;
    const py = -0.95 + (-0.50 + 0.95) * k;
    const pz = 0.55 + 0.15 * k;
    const ang = (-0.55 + (0.62 + 0.55) * k) + idle;
    const ca = Math.cos(ang), sa = Math.sin(ang);
    const toolXf = (v) => mg3dVec(px + v.x * ca - v.y * sa, py + v.x * sa + v.y * ca, pz + v.z);

    /* ---- faces de todos os meshes ---- */
    const meshes = mg3dSceneMeshes(kind).map(m => ({ mesh: m, xf: null }))
        .concat(mg3dToolMeshes(kind).map(m => ({ mesh: m, xf: toolXf })));

    const faces = [];
    for (const item of meshes) {
        const cam = item.mesh.verts.map(v => toCam(item.xf ? item.xf(v) : v, true));
        for (const f of item.mesh.faces) {
            const a0 = cam[f[0]], a1 = cam[f[1]], a2 = cam[f[2]], a3 = cam[f[3]];
            const n = mg3dNorm(mg3dCross(mg3dSub(a1, a0), mg3dSub(a2, a1)));
            const cxx = (a0.x + a1.x + a2.x + a3.x) / 4;
            const cyy = (a0.y + a1.y + a2.y + a3.y) / 4;
            const czz = (a0.z + a1.z + a2.z + a3.z) / 4;
            if (n.x * cxx + n.y * cyy + n.z * czz >= 0) continue; // face virada para trás
            const p0 = proj(a0), p1 = proj(a1), p2 = proj(a2), p3 = proj(a3);
            if (!p0 || !p1 || !p2 || !p3) continue;
            const lum = 0.30 + 0.70 * Math.max(0, n.x * light.x + n.y * light.y + n.z * light.z);
            faces.push({ z: czz, pts: [p0, p1, p2, p3], color: mg3dShade(item.mesh.color, lum) });
        }
    }
    faces.sort((a, b) => b.z - a.z);
    for (const f of faces) {
        ctx.beginPath();
        f.pts.forEach((p, i) => i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y));
        ctx.closePath();
        ctx.fillStyle = f.color;
        ctx.fill();
        ctx.strokeStyle = 'rgba(0,0,0,.25)';
        ctx.lineWidth = 1;
        ctx.stroke();
    }

    /* ---- faíscas / estilhaços no impacto ---- */
    if (st && st.t > 0.5) {
        const t2 = Math.min(1, (st.t - 0.5) / 0.5);
        const ip = proj(toCam(mg3dVec(0.4, 0.2, 1.2), true));
        if (ip) {
            if (st.success) {
                const rad = 60 * (1 - t2) + 8;
                const glow = ctx.createRadialGradient(ip.x, ip.y, 0, ip.x, ip.y, rad);
                glow.addColorStop(0, 'rgba(255,236,180,' + (0.85 * (1 - t2)) + ')');
                glow.addColorStop(1, 'rgba(255,200,80,0)');
                ctx.fillStyle = glow;
                ctx.beginPath(); ctx.arc(ip.x, ip.y, rad, 0, Math.PI * 2); ctx.fill();
                for (let i = 0; i < 10; i++) {
                    const a = (i / 10) * Math.PI * 2 + 0.3;
                    const d = 6 + t2 * 62;
                    ctx.globalAlpha = 1 - t2;
                    ctx.fillStyle = i % 3 === 0 ? '#e0a63c' : (kind === 'tree' ? '#8a5a34' : '#9a9186');
                    ctx.beginPath();
                    ctx.arc(ip.x + Math.cos(a) * d, ip.y + Math.sin(a) * d * 0.72 + t2 * t2 * 26, 3.4 - t2 * 1.8, 0, Math.PI * 2);
                    ctx.fill();
                }
                ctx.globalAlpha = 1;
            } else {
                ctx.globalAlpha = 1 - t2;
                ctx.strokeStyle = 'rgba(255,255,255,.5)';
                ctx.lineWidth = 2;
                ctx.beginPath(); ctx.arc(ip.x, ip.y, 10 + t2 * 26, 0, Math.PI * 2); ctx.stroke();
                ctx.globalAlpha = 1;
            }
        }
    }
}

/* ------------------------------------------------------------------ */
/*  Controle do minigame                                               */
/* ------------------------------------------------------------------ */
function tbMinigame(opts) {
    opts = opts || {};
    const overlay = document.getElementById('minigame-overlay');
    const canvas = document.getElementById('minigame-canvas');
    const titleEl = document.getElementById('minigame-title');
    const subEl = document.getElementById('minigame-subtitle');
    const feedbackEl = document.getElementById('minigame-feedback');
    const strikeBtn = document.getElementById('minigame-strike');
    const cancelBtn = document.getElementById('minigame-cancel');
    const ctx = (canvas && canvas.getContext) ? canvas.getContext('2d') : null;

    // Encerra um minigame anterior, se houver.
    if (_mgState && typeof _mgState.cancel === 'function') _mgState.cancel();

    const kind = opts.scene === 'tree' ? 'tree' : 'rock';
    const speed = opts.speed || 0.85;            // fração do anel por segundo
    const zoneWidth = Math.max(8, Math.min(40, opts.zoneWidth || 18));
    const zoneStart = opts.zoneStart != null ? opts.zoneStart : (8 + Math.random() * (84 - zoneWidth));
    const center = zoneStart + zoneWidth / 2;

    titleEl.textContent = opts.title || 'Minigame';
    subEl.textContent = opts.subtitle || 'Pare o marcador na faixa verde.';
    strikeBtn.textContent = kind === 'tree' ? '🪓 Golpear!' : '⛏️ Picar!';
    strikeBtn.disabled = false;
    cancelBtn.disabled = false;
    feedbackEl.textContent = '\u00a0';
    feedbackEl.className = 'minigame-feedback';
    overlay.classList.add('active');

    // Canvas nítido em telas HiDPI.
    let W = 380, H = 236;
    if (ctx) {
        const cssW = canvas.clientWidth || 380;
        const cssH = canvas.clientHeight || Math.round(cssW * 0.62);
        const dpr = Math.min(2, window.devicePixelRatio || 1);
        canvas.width = Math.round(cssW * dpr);
        canvas.height = Math.round(cssH * dpr);
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        W = cssW; H = cssH;
    }

    let pos = 0, dir = 1, spin = 0.55, last = performance.now(), raf = 0;
    let done = false, strike = null, settled = false, resolveGame = null;

    function settle(success, precision) {
        if (settled) return;
        settled = true;
        if (opts.onDone) opts.onDone(success, precision);
        if (resolveGame) resolveGame({ success: success, precision: precision });
    }

    function closeOverlay() {
        cancelAnimationFrame(raf);
        overlay.classList.remove('active');
        strikeBtn.removeEventListener('click', onStrike);
        cancelBtn.removeEventListener('click', onCancel);
        if (ctx) canvas.removeEventListener('click', onStrike);
        document.removeEventListener('keydown', onKey);
        if (_mgState === api) _mgState = null;
    }

    function frame(now) {
        const dt = Math.min(0.05, (now - last) / 1000);
        last = now;
        if (!done) {
            pos += dir * speed * 100 * dt;
            if (pos > 100) { pos = 100; dir = -1; }
            if (pos < 0) { pos = 0; dir = 1; }
        }
        spin += dt * 0.9;
        if (strike) strike.t = Math.min(1.1, strike.t + dt / 0.55);
        if (ctx) mg3dRender(ctx, W, H, { kind: kind, spin: spin, pos: pos, zoneStart: zoneStart, zoneWidth: zoneWidth, strike: strike });
        if (strike && strike.t >= 1) {
            settle(strike.success, strike.precision);
            closeOverlay();
            return;
        }
        raf = requestAnimationFrame(frame);
    }

    function strikeNow(success, precision) {
        if (done || strike) return;
        done = true;
        strike = { t: 0, success: !!success, precision: success ? precision : 0 };
        strikeBtn.disabled = true;
        cancelBtn.disabled = true;
        feedbackEl.textContent = success ? '💥 Bom golpe!' : '💨 O golpe resvalou…';
        feedbackEl.className = 'minigame-feedback ' + (success ? 'ok' : 'bad');
    }

    function onStrike(e) {
        if (e && e.preventDefault) e.preventDefault();
        if (done || strike) return;
        const dentro = pos >= zoneStart && pos <= zoneStart + zoneWidth;
        const distancia = Math.abs(pos - center);
        const precision = Math.max(0, 1 - (distancia / 50)); // 1 = no centro
        strikeNow(dentro, dentro ? precision : 0);
    }
    function onCancel(e) {
        if (e && e.preventDefault) e.preventDefault();
        if (done) return;
        done = true;
        settle(false, 0);
        closeOverlay();
    }
    function onKey(e) {
        if (e.key === ' ' || e.key === 'Enter' || e.code === 'Space') onStrike(e);
        else if (e.key === 'Escape') onCancel(e);
    }

    strikeBtn.addEventListener('click', onStrike);
    cancelBtn.addEventListener('click', onCancel);
    if (ctx) canvas.addEventListener('click', onStrike);
    document.addEventListener('keydown', onKey);

    const api = { cancel: function () { onCancel(); } };
    _mgState = api;
    raf = requestAnimationFrame(frame);

    return new Promise(resolve => { resolveGame = resolve; });
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

// Ferramenta EQUIPADA NA MÃO PRINCIPAL (obrigatório para minerar/cortar).
// Retorna { item, source, index } como tbDamageTool espera, ou null.
function tbMainhandTool(kind) {
    const eq = gameState && gameState.equipment && gameState.equipment.mainhand;
    if (eq && eq.toolType === kind && (eq.durability === undefined || eq.durability > 0)) {
        return { item: eq, source: 'equipment', index: -1 };
    }
    return null;
}

// Dano autoinfligido (bater com as mãos nuas na rocha/tronco).
function tbHurtSelf(amount, reason) {
    if (!gameState || !gameState.character) return;
    gameState.character.life = Math.max(0, gameState.character.life - amount);
    addLog(`🩸 ${reason} (-${amount} de vida)`);
    if (gameState.character.life <= 0 && typeof playerDeath === 'function') playerDeath();
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
    // Aviso (não bloqueia a entrada): minerar exige picareta NA MÃO PRINCIPAL.
    if (!tbMainhandTool('pickaxe')) {
        const esp = tbFindTool('pickaxe');
        addLog(esp
            ? '⚠️ Sua picareta está guardada. Equipe-a na MÃO PRINCIPAL (clique nela no inventário) para arrancar veios.'
            : '⚠️ Você não tem picareta — dá para explorar os túneis, mas bater na rocha com as mãos nuas só machuca.');
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

    const tool = tbMainhandTool('pickaxe');
    if (!tool) {
        // Sem picareta NA MÃO: socar a rocha machuca as mãos.
        if (typeof SV_spend === 'function') SV_spend(1.5, 1.5);
        if (typeof SV_spendMana === 'function') SV_spendMana(0.5);
        tbHurtSelf(4 + Math.floor(Math.random() * 4), 'Você soca a rocha com as mãos nuas e a pedra corta seus dedos!');
        const esp = tbFindTool('pickaxe');
        addLog(esp
            ? '⛏️ Sua picareta está na mochila — equipe na MÃO PRINCIPAL (clique nela) para minerar.'
            : '⛏️ Você precisa de uma picareta. Compre com Bruno na Forja ou crafte uma na bancada.');
        tbMineSync();
        return;
    }
    const power = tool.item.minePower || 1;
    const dificuldade = { stone: 0.7, coal: 0.95, iron_ore: 1.05, amethyst: 1.4 }[vein.type] || 1;
    const zoneWidth = vein.type === 'amethyst' ? 12 : (vein.type === 'iron_ore' ? 15 : 18);

    tbMinigame({
        title: '⛏️ Minerando',
        subtitle: 'Pare o marcador na faixa verde para lascar a rocha!',
        scene: 'rock',
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
    const tool = tbMainhandTool('axe');
    if (!tool) {
        // Sem machado NA MÃO: bater no tronco com as mãos nuas machuca.
        if (typeof SV_spend === 'function') SV_spend(1.5, 1.2);
        tbHurtSelf(3 + Math.floor(Math.random() * 3), 'Você bate no tronco com as mãos nuas e lasca a pele!');
        const esp = tbFindTool('axe');
        addLog(esp
            ? '🪓 Seu machado está na mochila — equipe na MÃO PRINCIPAL (clique nele) para derrubar a árvore.'
            : '🪓 Você precisa de um machado. Compre com Bruno na Forja ou crafte um na bancada.');
        if (typeof updateUI === 'function') updateUI();
        return;
    }
    const power = tool.item.chopPower || 1;
    const zoneWidth = power >= 2 ? TB_CHOP_ZONE.ferro : TB_CHOP_ZONE.pedra;

    tbMinigame({
        title: '🪓 Cortando lenha',
        subtitle: 'Ritmo firme! Pare o marcador na faixa verde.',
        scene: 'tree',
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
/* Atenção: NÃO usar o nome TB_origUpdateUI aqui — ele já existe em
   systems.js. Como scripts clássicos compartilham o mesmo escopo lexical
   global, redeclarar um `const` top-level derruba o arquivo inteiro
   (SyntaxError) e nenhuma função da mina fica disponível. */
const TB_MINE_origUpdateUI = (typeof updateUI === 'function') ? updateUI : null;
if (TB_MINE_origUpdateUI) {
    updateUI = function () {
        try {
            if (gameState && gameState.mine && gameState.mine.generated
                && typeof LOCATIONS !== 'undefined' && gameState.mine.pos
                && !LOCATIONS['mine_' + gameState.mine.pos]) {
                tbMineRegisterLocations();
            }
        } catch (e) { /* ignora */ }
        return TB_MINE_origUpdateUI.apply(this, arguments);
    };
}

