-- Combate por turnos: golpes, habilidades, esquiva, armadura e recompensas.
local DB = require('src.data.init')
local State = require('src.game.state')
local Inventory = require('src.game.inventory')
local Survival = require('src.game.survival')
local Quests = require('src.game.quests')
local Achievements = require('src.game.achievements')
local U = require('src.core.util')

local Combat = {}

local function G() return State.G end
local function rnd(n) return (love and love.math.random(n) or math.random(n)) end
local function rndf() return (love and love.math.random() or math.random()) end
-- Inteiro em [0, n-1], equivalente a Math.floor(Math.random() * n).
local function rnd0(n) return math.floor(rndf() * n) end

-- Habilidades raciais (TB_SKILLS do systems.js).
Combat.skills = {
    esquiva = { id = 'esquiva', name = 'Esquiva', icon = '💨', cost = 25, desc = 'Anula o próximo golpe recebido.' },
    magia   = { id = 'magia',   name = 'Bola de Fogo', icon = '🔥', cost = 40, desc = 'Dano mágico pesado instantâneo.' },
    carga   = { id = 'carga',   name = 'Carga', icon = '🐎', cost = 30, desc = 'Investida com o dobro do ataque.' },
    cura    = { id = 'cura',    name = 'Bênção da Ninfa', icon = '🌿', cost = 35, desc = 'Recupera bastante vida.' },
}

function Combat.active()
    return G() and G().enemy or nil
end

function Combat.start(enemyId, opt)
    local G_ = G()
    if not G_ or G_.isDead then return false end
    if G_.enemy then return false end
    local base = DB.creatures[enemyId]
    if not base then return false end
    local enemy = U.deepcopy(base)
    enemy.id = enemyId
    enemy.maxLife = enemy.life
    G_.enemy = enemy
    G_.combatPanel = nil
    State.addLog(string.format('⚔️ Um %s bloqueia seu caminho!', enemy.name))
    return true
end

-- Rola um encontro para o local (TB_spawnEncounterFor).
function Combat.spawnFor(locationId)
    local cfg = DB.encounters[locationId]
    if not cfg then return false end
    local weather = State.weather()
    local bonus = weather and weather.encounterBonus or 0
    if rndf() > math.min(0.95, (cfg.chance or 0) + bonus) then return false end
    local table_ = cfg.table or {}
    if #table_ == 0 then return false end
    local id = table_[rnd(#table_)]
    if not DB.creatures[id] then return false end
    return Combat.start(id)
end

-- ───────────────────────────────────────────────────── golpes disponíveis
function Combat.availableStrikes()
    local list = {}
    for _, s in pairs(DB.strikes.basic) do list[#list + 1] = s end
    table.sort(list, function(a, b) return (a.min or 0) < (b.min or 0) end)
    local G_ = G()
    local racial = DB.strikes.racial[G_.character.race]
    if racial then list[#list + 1] = racial end
    local main = G_.equipment.mainhand
    local off = G_.equipment.offhand
    for _, w in ipairs({ main, off }) do
        if w and DB.strikes.weapon[w.id] then
            local s = U.deepcopy(DB.strikes.weapon[w.id])
            s.weaponId = w.id
            list[#list + 1] = s
        end
    end
    return list
end

function Combat.availableAbilities()
    local G_ = G()
    local out = {}
    for _, id in ipairs(G_.learnedAbilities or {}) do
        local a = DB.strikes.learnable[id]
        if a then out[#out + 1] = a end
    end
    return out
end

function Combat.racialSkill()
    local G_ = G()
    local race = DB.races[G_.character.race]
    return race and Combat.skills[race.skill] or nil
end

function Combat.strikeRange(strike)
    local base = Inventory.totalAttack()
    return math.max(1, U.round(base * (strike.min or 1))),
           math.max(1, U.round(base * (strike.max or 1)))
end

-- ───────────────────────────────────────────────────── dano do jogador
local function arrowSlot()
    local inv = G().inventory
    for i = 1, Inventory.SLOTS do
        local it = inv[i]
        if it and (it.type == 'ammo' or it.id == 'arrow' or it.id == 'iron_arrow' or it.id == 'flecha') then
            return i, it
        end
    end
    return nil
end

local function consumeArrow(slot)
    if slot then
        Inventory.removeAt(G().inventory, slot, 1)
    end
end

local function sanityMult()
    local eff = Survival.sanityEffects()
    return eff.damageMult or 1, eff
end

local function useMana(cost)
    local G_ = G()
    if cost <= 0 then return true end
    if G_.character.mana < cost then
        State.addLog(string.format('🔮 Mana insuficiente! Precisa de %d e você tem %d.', cost, G_.character.mana))
        return false
    end
    G_.character.mana = G_.character.mana - cost
    return true
end

-- Ataque básico (botão "Atacar").
function Combat.attack()
    local G_ = G()
    if not G_ or G_.isDead or not G_.enemy then return end
    -- O original gasta energia a cada clique em "Atacar" (SV_origAttack),
    -- mesmo quando o arco está sem flechas.
    Survival.onCombat()
    local main = G_.equipment.mainhand
    if main and main.id == 'bow' then
        local slot, arrow = arrowSlot()
        if not arrow then
            State.addLog('❌ Seu arco está sem flechas!')
            return
        end
        local mult = sanityMult()
        local dmg = math.max(1, U.round((arrow.damage or 50) * mult))
        consumeArrow(slot)
        State.addLog(string.format('🏹 Você disparou uma flecha causando %d de dano!', dmg))
        Combat.resolvePlayerStrike(dmg, '🏹 Ataque com Arco')
        return
    end
    local mult = sanityMult()
    local raw = Inventory.totalAttack() - G_.enemy.defense + rnd0(20)
    local dmg = math.max(1, U.round(raw * mult))
    Combat.resolvePlayerStrike(dmg, '⚔️ Ataque corpo a corpo')
end

function Combat.useStrike(id)
    local G_ = G()
    if not G_ or G_.isDead or not G_.enemy then return end
    local strike
    for _, s in ipairs(Combat.availableStrikes()) do
        if s.id == id then strike = s break end
    end
    if not strike then
        for _, s in ipairs(Combat.availableAbilities()) do
            if s.id == id then strike = s break end
        end
    end
    if not strike then return end

    local cost = strike.mana or 0
    if not useMana(cost) then return end
    local mult, eff = sanityMult()

    if cost > 0 and rndf() < (eff.fumbleChance or 0) then
        State.addLog(string.format('🌀 Sua mente está confusa (Sanidade %d/100) — %s se desfaz no ar! A mana foi perdida.',
            math.floor(eff.sanity or 0), strike.name))
        Combat.enemyCounter()
        return
    end

    if strike.type == 'heal' then
        local amount = U.round(G_.character.maxLife * (strike.heal or 0.25) * mult)
        local healed = State.heal(amount)
        State.addLog(string.format('🌿 %s: você recupera %d de vida!', strike.name, healed))
        Combat.enemyCounter()
        return
    end

    if strike.ranged then
        local slot, arrow = arrowSlot()
        if not arrow then
            State.addLog('❌ Seu arco está sem flechas!')
            return
        end
        consumeArrow(slot)
        Combat.resolvePlayerStrike(math.max(1, U.round((arrow.damage or 50) * mult)), '🏹 ' .. strike.name)
        return
    end

    local base = Inventory.totalAttack()
    local raw = base * ((strike.min or 1) + rndf() * ((strike.max or 1) - (strike.min or 1)))
    local dmg = math.max(1, U.round(raw * mult) - G_.enemy.defense)
    Combat.resolvePlayerStrike(dmg, strike.name)
end

function Combat.resolvePlayerStrike(damage, label)
    local G_ = G()
    if not G_ or not G_.enemy then return end
    G_.enemy.life = G_.enemy.life - damage
    State.addLog(string.format('%s: você causou %d de dano ao %s!', label, damage, G_.enemy.name))
    if G_.enemy.life <= 0 then
        Combat.onDefeat()
        return
    end
    Combat.enemyCounter()
end

-- Habilidade racial (TB_SKILLS / useSkill).
function Combat.useRacialSkill()
    local G_ = G()
    if not G_ or G_.isDead then return end
    if not G_.enemy then
        State.addLog('💡 Você só pode usar habilidades em combate.')
        return
    end
    local skill = Combat.racialSkill()
    if not skill then
        State.addLog('❌ Sua raça não possui habilidade.')
        return
    end
    if not useMana(skill.cost) then return end
    State.addLog(string.format('%s Você usa %s!', skill.icon, skill.name))

    if skill.id == 'esquiva' then
        G_.flags.evasionActive = true
        State.addLog('💨 Você se prepara para esquivar do próximo golpe!')
        Combat.enemyCounter()
        return
    elseif skill.id == 'magia' then
        local dmg = 80 + (G_.character.level or 1) * 15 + rnd0(25)
        G_.enemy.life = G_.enemy.life - dmg
        State.addLog(string.format('🔥 Bola de Fogo causou %d de dano em %s!', dmg, G_.enemy.name))
    elseif skill.id == 'carga' then
        local dmg = math.max(1, Inventory.totalAttack() * 2 - G_.enemy.defense)
        G_.enemy.life = G_.enemy.life - dmg
        State.addLog(string.format('🐎 Carga devastadora: %d de dano em %s!', dmg, G_.enemy.name))
    elseif skill.id == 'cura' then
        local heal = 120 + (G_.character.level or 1) * 10
        local healed = State.heal(heal)
        State.addLog(string.format('🌿 Bênção da Ninfa recuperou %d de vida!', healed))
    end

    if G_.enemy and G_.enemy.life <= 0 then
        Combat.onDefeat()
    else
        Combat.enemyCounter()
    end
end

-- ───────────────────────────────────────────────────── contra-ataque
function Combat.enemyCounter()
    local G_ = G()
    if not G_ or not G_.enemy or G_.isDead then return end
    if G_.flags.evasionActive then
        G_.flags.evasionActive = false
        State.addLog(string.format('💨 Você esquiva habilmente do ataque de %s!', G_.enemy.name))
        return
    end
    local base = math.max(1, G_.enemy.attack + rnd0(15))
    State.addLog(string.format('💢 %s contra-ataca causando %d de dano!', G_.enemy.name, base))
    Inventory.applyDamage(base)
    if G_.character.life <= 0 then
        State.kill(string.format('Você foi derrotado por %s.', G_.enemy.name))
    end
end

function Combat.flee()
    local G_ = G()
    if not G_ or G_.isDead or not G_.enemy then return end
    if rndf() < 0.5 then
        State.addLog(string.format('🏃 Você conseguiu fugir de %s!', G_.enemy.name))
        G_.enemy = nil
        G_.combatPanel = nil
        return true
    end
    State.addLog(string.format('❌ Não conseguiu fugir de %s!', G_.enemy.name))
    local dmg = math.max(1, G_.enemy.attack + rnd0(15))
    State.addLog(string.format('💢 %s ataca enquanto você foge causando %d de dano!', G_.enemy.name, dmg))
    Inventory.applyDamage(dmg)
    if G_.character.life <= 0 then
        State.kill(string.format('Você morreu tentando fugir de %s.', G_.enemy.name))
    end
    return false
end

-- ───────────────────────────────────────────────────── vitória
function Combat.onDefeat()
    local G_ = G()
    local enemy = G_.enemy
    if not enemy then return end
    State.addLog(string.format('✨ Você derrotou %s!', enemy.name))
    local exp = enemy.exp or 0
    local gold = enemy.gold or 0
    G_.character.gold = G_.character.gold + gold
    State.addLog(string.format('💰 Ganhou %d EXP e %d moedas!', exp, gold))
    if rndf() < 0.4 and enemy.drops and #enemy.drops > 0 then
        local dropId = enemy.drops[rnd(#enemy.drops)]
        if DB.items[dropId] then
            Inventory.add(dropId, 1)
            State.addLog(string.format('🎁 Você pegou %s de %s!', DB.items[dropId].name, enemy.name))
        end
    end
    Quests.trigger('kill', { creatureId = enemy.id })
    G_.stats.kills = (G_.stats.kills or 0) + 1
    G_.stats.killsByType[enemy.id] = (G_.stats.killsByType[enemy.id] or 0) + 1
    G_.bestiary[enemy.id] = (G_.bestiary[enemy.id] or 0) + 1
    local wasBlackMage = enemy.id == 'black_mage'
    G_.enemy = nil
    G_.combatPanel = nil
    G_.flags.evasionActive = false
    State.addExp(exp)
    Achievements.check()
    if wasBlackMage and not G_.flags.endingShown then
        G_.flags.endingPending = true
        State.addLog('👑 A escuridão se dissipa. Duas coroas repousam diante de você...')
    end
end

function Combat.forceKill()
    Combat.onDefeat()
end

return Combat
