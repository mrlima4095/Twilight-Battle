-- Minigame de timing (picareta / machado).
-- Uma barra horizontal com um marcador em movimento; acerte a zona para
-- progredir. Três acertos concluem a coleta; erros custam tempo/sanidade.
local State = require('src.game.state')
local Survival = require('src.game.survival')
local U = require('src.core.util')

local MG = {}

MG.active = nil

local function rndf() return (love and love.math.random() or math.random()) end
local function rnd(a, b) return (love and love.math.random(a, b) or math.random(a, b)) end

-- opts.kind: 'mine' | 'tree'
-- opts.label, opts.difficulty (1.0 normal), opts.needed (acertos), opts.onSuccess, opts.onFail
function MG.start(opts)
    opts = opts or {}
    local needed = opts.needed or 3
    local diff = opts.difficulty or 1.0
    MG.active = {
        kind = opts.kind or 'mine',
        label = opts.label or (opts.kind == 'tree' and 'Derrubar a árvore' or 'Minerar o veio'),
        pos = 0,
        dir = 1,
        speed = 0.62 * diff,
        zoneW = math.max(0.12, 0.26 - (diff - 1) * 0.06),
        zoneC = 0.5,
        hits = 0,
        needed = needed,
        onSuccess = opts.onSuccess,
        onFail = opts.onFail,
        lastResult = nil,
        flash = 0,
        shake = 0,
        countdown = 0,
    }
    MG.randomizeZone()
end

function MG.randomizeZone()
    local a = MG.active
    if not a then return end
    a.zoneC = 0.22 + rndf() * 0.56
end

function MG.update(dt)
    local a = MG.active
    if not a then return end
    a.flash = math.max(0, (a.flash or 0) - dt)
    a.shake = math.max(0, (a.shake or 0) - dt)
    a.pos = a.pos + a.dir * a.speed * dt
    if a.pos >= 1 then a.pos = 1 a.dir = -1 end
    if a.pos <= 0 then a.pos = 0 a.dir = 1 end
    if a.countdown > 0 then
        a.countdown = a.countdown - dt
        if a.countdown <= 0 then
            MG.active = nil
            if a.onFail then a.onFail('Tempo esgotado.') end
        end
    end
end

function MG.inZone()
    local a = MG.active
    if not a then return false end
    return math.abs(a.pos - a.zoneC) <= a.zoneW * 0.5
end

-- Retorna {hit=, done=, success=, progress=}
function MG.strike()
    local a = MG.active
    if not a then return { done = true, success = false } end
    local hit = MG.inZone()
    a.flash = 0.25
    if hit then
        a.hits = a.hits + 1
        a.speed = math.min(1.7, a.speed + 0.1)
        MG.randomizeZone()
        if a.hits >= a.needed then
            MG.active = nil
            State.addLog(string.format('✨ %s concluído!', a.label))
            if a.onSuccess then a.onSuccess() end
            return { hit = true, done = true, success = true }
        end
        State.addLog(string.format('⛏️ Golpe certeiro! (%d/%d)', a.hits, a.needed))
        return { hit = true, done = false, progress = a.hits }
    end
    a.shake = 0.25
    Survival.addSanity(-1)
    State.addLog(string.format('❌ Golpe na rocha! (%d/%d) A vibração incomoda.', a.hits, a.needed))
    return { hit = false, done = false, progress = a.hits }
end

function MG.cancel()
    local a = MG.active
    MG.active = nil
    if a and a.onFail then a.onFail('Você desistiu.') end
end

return MG
