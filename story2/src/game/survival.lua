-- Sobrevivência: fome, sede e sanidade (port de static/js/story/survival.js).
local DB = require('src.data.init')
local State = require('src.game.state')
local U = require('src.core.util')

local SV = {}

SV.MAX = 100
SV.TICK = 5
SV.HUNGER_PER_TICK = 0.12
SV.THIRST_PER_TICK = 0.16
SV.TRAVEL_COST = { hunger = 0.5, thirst = 0.7 }
SV.TRAVEL_MANA = 0.5
SV.COMBAT_COST = { hunger = 0.4, thirst = 0.5 }
SV.NIGHT_COST = { hunger = 5, thirst = 6 }
SV.STARVE_DAMAGE = 0.015
SV.DEHYDRATE_DAMAGE = 0.02

SV.SANITY_REGEN_PER_TICK = 0.06
SV.SANITY_DAWN = 10
SV.SANITY_FUMBLE_AT = 70
SV.SANITY_MAX_FUMBLE = 0.6
SV.SANITY_MIN_DAMAGE = 0.55
SV.THIRST_SANITY_AT = 40
SV.THIRST_SANITY_MAX = 0.22
SV.SLEEP_FLIPS_LIMIT = 2
SV.SLEEP_SANITY_STEP = 0.10
SV.SLEEP_SANITY_MAX = 0.40

SV.LEVELS = {
    { value = 50, flag = 'warn50' },
    { value = 25, flag = 'warn25' },
    { value = 10, flag = 'warn10' },
    { value = 0, flag = 'warn0' },
}

local function G() return State.G end

function SV.ensure()
    local G_ = G()
    if not G_ then return end
    local s = G_.survival
    if type(s) ~= 'table' then
        s = { hunger = 100, thirst = 100, sanity = 100, manaDebt = 0, flipsSinceSleep = 0,
              flags = { hunger = {}, thirst = {}, sanity = {}, extra = {} } }
        G_.survival = s
    end
    s.hunger = U.clamp(tonumber(s.hunger) or 100, 0, SV.MAX)
    s.thirst = U.clamp(tonumber(s.thirst) or 100, 0, SV.MAX)
    s.sanity = U.clamp(tonumber(s.sanity) or 100, 0, SV.MAX)
    s.manaDebt = tonumber(s.manaDebt) or 0
    s.flipsSinceSleep = tonumber(s.flipsSinceSleep) or 0
    s.tickAcc = tonumber(s.tickAcc) or 0
    s.flags = s.flags or {}
    s.flags.hunger = s.flags.hunger or {}
    s.flags.thirst = s.flags.thirst or {}
    s.flags.sanity = s.flags.sanity or {}
    s.flags.extra = s.flags.extra or {}
    return s
end

function SV.reset()
    local G_ = G()
    if not G_ then return end
    G_.survival = {
        hunger = 100, thirst = 100, sanity = 100,
        manaDebt = 0, flipsSinceSleep = 0, tickAcc = 0,
        flags = { hunger = {}, thirst = {}, sanity = {}, extra = {} },
    }
end

-- ───────────────────────────────────────────────────────── avisos
local function warnFor(key, label, s, zeroMsg, hint)
    local flags = s.flags[key]
    for _, lvl in ipairs(SV.LEVELS) do
        if s[key] <= lvl.value then
            if not flags[lvl.flag] then
                flags[lvl.flag] = true
                if lvl.value == 0 then
                    State.addLog(string.format('%s chegou a ZERO! %s', label, zeroMsg))
                else
                    State.addLog(string.format('%s está em %d/100. %s', label, math.floor(s[key]), hint))
                end
            end
        else
            flags[lvl.flag] = false
        end
    end
end

function SV.checkThresholds()
    local s = SV.ensure()
    if not s then return end
    warnFor('hunger', '🍗 Sua fome', s, 'Você está faminto e perde vida.', 'Coma algo!')
    warnFor('thirst', '💧 Sua sede', s, 'Você está desidratado e perde vida.', 'Beba algo!')
    warnFor('sanity', '🧠 Sua sanidade', s, 'Sua mente se perde: magias falham e o combate fica instável.', 'Durma ou evite bebidas alcoólicas!')
end

-- ───────────────────────────────────────────────────────── núcleo
function SV.apply(dh, dt)
    local s = SV.ensure()
    if not s then return end
    local G_ = G()
    if not G_.character or G_.isDead then return end
    s.hunger = U.clamp(s.hunger + (dh or 0), 0, SV.MAX)
    s.thirst = U.clamp(s.thirst + (dt or 0), 0, SV.MAX)
    SV.checkThresholds()
end

function SV.spend(hunger, thirst)
    SV.apply(-(hunger or 0), -(thirst or 0))
end

function SV.addSanity(delta)
    local s = SV.ensure()
    if not s then return end
    s.sanity = U.clamp(s.sanity + (delta or 0), 0, SV.MAX)
    SV.checkThresholds()
end

function SV.sanityEffects()
    local s = SV.ensure()
    local sanity = s and s.sanity or 0
    local fumble = 0
    if sanity < SV.SANITY_FUMBLE_AT then
        fumble = math.min(SV.SANITY_MAX_FUMBLE, ((SV.SANITY_FUMBLE_AT - sanity) / SV.SANITY_FUMBLE_AT) * SV.SANITY_MAX_FUMBLE)
    end
    local dmg = math.max(SV.SANITY_MIN_DAMAGE, math.min(1, SV.SANITY_MIN_DAMAGE + sanity * ((1 - SV.SANITY_MIN_DAMAGE) / SV.MAX)))
    return { sanity = sanity, fumbleChance = fumble, damageMult = dmg }
end

function SV.spendMana(amount)
    local G_ = G()
    local s = SV.ensure()
    if not G_ or not s or not G_.character or G_.isDead or amount <= 0 then return end
    s.manaDebt = (s.manaDebt or 0) + amount
    local whole = math.floor(s.manaDebt)
    if whole <= 0 then return end
    s.manaDebt = s.manaDebt - whole
    G_.character.mana = math.max(0, G_.character.mana - whole)
end

local function sanityDrain(s)
    local drain = 0
    local thirstLow = s.thirst < SV.THIRST_SANITY_AT
    if thirstLow then
        drain = drain + ((SV.THIRST_SANITY_AT - s.thirst) / SV.THIRST_SANITY_AT) * SV.THIRST_SANITY_MAX
    end
    local over = math.max(0, (s.flipsSinceSleep or 0) - SV.SLEEP_FLIPS_LIMIT)
    local noSleep = over > 0
    if noSleep then
        drain = drain + math.min(SV.SLEEP_SANITY_MAX, over * SV.SLEEP_SANITY_STEP)
    end
    local extra = s.flags.extra
    if thirstLow and not extra.thirstSanity then
        extra.thirstSanity = true
        State.addLog('🧠 A sede turva sua mente — beba água! (Sanidade caindo)')
    elseif not thirstLow then
        extra.thirstSanity = false
    end
    if noSleep and not extra.sleepSanity then
        extra.sleepSanity = true
        State.addLog('🧠 Você está há muito tempo sem dormir — a mente se desgasta.')
    elseif not noSleep then
        extra.sleepSanity = false
    end
    return drain
end

function SV.applyNutrition(item)
    if not item then return end
    local table_ = DB.NUTRITION[item.id]
    local hunger, thirst = 0, 0
    if table_ then
        hunger = table_.hunger or 0
        thirst = table_.thirst or 0
    elseif item.type == 'drink' then
        thirst = math.max(12, math.floor((item.mana or 0) * 1.5 + 0.5))
    elseif item.type == 'food' then
        hunger = math.max(3, math.floor((item.heal or 0) / 3 + 0.5))
    end
    if hunger == 0 and thirst == 0 then return end
    SV.apply(hunger, thirst)
    if hunger > 0 and thirst > 0 then
        State.addLog(string.format('🍗 Fome +%d · 💧 Sede +%d', hunger, thirst))
    elseif hunger > 0 then
        State.addLog(string.format('🍗 Fome +%d', hunger))
    else
        State.addLog(string.format('💧 Sede +%d', thirst))
    end
end

-- Chamado a cada 5 s de jogo.
function SV.tickStep()
    local G_ = G()
    local s = SV.ensure()
    if not G_ or not s or not G_.character or G_.isDead then return end
    SV.spend(SV.HUNGER_PER_TICK, SV.THIRST_PER_TICK)
    SV.addSanity(SV.SANITY_REGEN_PER_TICK - sanityDrain(s))

    local damage = 0
    if s.hunger <= 0 then damage = damage + math.ceil(G_.character.maxLife * SV.STARVE_DAMAGE) end
    if s.thirst <= 0 then damage = damage + math.ceil(G_.character.maxLife * SV.DEHYDRATE_DAMAGE) end
    if damage > 0 then
        G_.character.life = math.max(0, G_.character.life - damage)
        local cause = (s.hunger <= 0 and s.thirst <= 0) and 'fome e sede' or (s.hunger <= 0 and 'inanição' or 'desidratação')
        State.addLog(string.format('💀 Você perde %d de vida por %s!', damage, cause))
        if G_.character.life <= 0 then State.kill() end
    end
end

function SV.update(dt)
    local s = SV.ensure()
    if not s then return end
    s.tickAcc = (s.tickAcc or 0) + dt
    while s.tickAcc >= SV.TICK do
        s.tickAcc = s.tickAcc - SV.TICK
        SV.tickStep()
    end
end

function SV.onTravel()
    SV.spend(SV.TRAVEL_COST.hunger, SV.TRAVEL_COST.thirst)
    SV.spendMana(SV.TRAVEL_MANA)
end

function SV.onCombat()
    SV.spend(SV.COMBAT_COST.hunger, SV.COMBAT_COST.thirst)
end

function SV.onNightChange()
    SV.spend(SV.NIGHT_COST.hunger, SV.NIGHT_COST.thirst)
    SV.addSanity(SV.SANITY_DAWN)
    local s = SV.ensure()
    if s then s.flipsSinceSleep = (s.flipsSinceSleep or 0) + 1 end
end

function SV.onSleep()
    local s = SV.ensure()
    if s then
        s.flipsSinceSleep = 0
        s.flags.extra.sleepSanity = false
    end
    SV.addSanity(6)
end

function SV.hasWaterSource()
    local G_ = G()
    return G_ and DB.WATER_LOCATIONS[G_.location] == true
end

function SV.drinkWater()
    local G_ = G()
    if not G_ or G_.isDead then return end
    if not SV.hasWaterSource() then
        State.addLog('💧 Não há água potável por aqui.')
        return
    end
    local s = SV.ensure()
    if s.thirst >= SV.MAX then
        State.addLog('💧 Você não está com sede agora.')
        return
    end
    local before = s.thirst
    SV.apply(0, 60)
    State.addLog(string.format('💧 Você bebe água fresca e recupera %d de sede.', math.floor(s.thirst - before)))
end

return SV
