-- Ciclo dia/noite, calendário, estações, clima e sono.
local State = require('src.game.state')
local DB = require('src.data.init')
local Survival = require('src.game.survival')
local U = require('src.core.util')

local Time = {}

local function G() return State.G end

Time.SLEEP_SECONDS = 10

function Time.update(dt)
    local G_ = G()
    if not G_ or not G_.character then return end
    G_.playSeconds = (G_.playSeconds or 0) + dt
    if G_.isSleeping then
        G_.sleepTimer = math.max(0, (G_.sleepTimer or 0) - dt)
        if G_.sleepTimer <= 0 then
            Time.completeSleep(false, Time.SLEEP_SECONDS)
        end
        return
    end
    if G_.isDead then return end
    G_.cycleRemaining = (G_.cycleRemaining or G_.cycleDuration) - dt
    if G_.cycleRemaining <= 0 then
        G_.cycleRemaining = G_.cycleDuration
        Time.toggleDayNight()
    end
end

function Time.toggleDayNight()
    local G_ = G()
    G_.timeOfDay = (G_.timeOfDay == 'day') and 'night' or 'day'
    State.addLog(G_.timeOfDay == 'day' and '☀️ Amanheceu!' or '🌙 Anoiteceu!')

    if G_.timeOfDay == 'day' then
        G_.dayCount = G_.dayCount + 1
        if G_.dayCount > 60 then
            G_.dayCount = 1
            G_.seasonCount = G_.seasonCount + 1
            if G_.seasonCount > 4 then
                G_.seasonCount = 1
                G_.yearCount = G_.yearCount + 1
                G_.stats.years = G_.yearCount
                G_.stats.yearAdvances = (G_.stats.yearAdvances or 0) + 1
                State.addLog(string.format('🎉 ANO NOVO! Bem-vindo ao Ano %d do Reino da Aurora!', G_.yearCount))
            else
                local s = State.season()
                State.addLog(string.format('🍃 %s começou! %s', s.name, s.effect))
            end
        end
        G_.weather = State.rollWeather(G_.seasonCount)
        State.addLog(string.format('%s Clima: %s', G_.weather.icon or '', G_.weather.name or ''))
    end
    Survival.onNightChange()
end

function Time.advance(seconds)
    local G_ = G()
    if not G_ then return end
    local remaining = seconds
    while remaining > 0 do
        local inCycle = G_.cycleRemaining or 0
        if remaining < inCycle then
            G_.cycleRemaining = inCycle - remaining
            remaining = 0
        else
            remaining = remaining - inCycle
            G_.cycleRemaining = G_.cycleDuration
            Time.toggleDayNight()
        end
    end
end

function Time.canSleep()
    local G_ = G()
    if not G_ or G_.isDead or G_.isSleeping then return false, 'Não é possível dormir agora.' end
    if G_.timeOfDay == 'day' then
        local manaPct = G_.character.maxMana > 0 and (G_.character.mana / G_.character.maxMana) or 0
        if manaPct >= 0.5 then
            return false, 'Você não está cansado o suficiente para dormir durante o dia! Sua mana está acima de 50%.'
        end
    end
    return true
end

function Time.sleepMessage()
    local G_ = G()
    if G_.timeOfDay == 'day' then
        return 'Dormir durante o dia... Você acordará à noite, mas recuperará apenas 20% da mana.'
    end
    return 'Dormir durante a noite... Você acordará de dia e recuperará toda sua mana!'
end

function Time.startSleep()
    local G_ = G()
    local ok, msg = Time.canSleep()
    if not ok then
        State.addLog('⚠️ ' .. msg)
        return false, msg
    end
    G_.isSleeping = true
    G_.sleepTimer = Time.SLEEP_SECONDS
    State.addLog('😴 Você foi dormir...')
    return true
end

function Time.completeSleep(early, secondsSlept)
    local G_ = G()
    if not G_ then return end
    local wasDay = G_.timeOfDay == 'day'
    local gameTime = (secondsSlept or 0) * 60
    State.addLog(string.format('⏱️ Você dormiu por %d minutos de jogo.', math.floor(gameTime / 60)))
    Time.advance(gameTime)

    if wasDay then
        local restored = math.floor(G_.character.maxMana * 0.2)
        G_.character.mana = math.min(G_.character.maxMana, G_.character.mana + restored)
        State.addLog(string.format('😴 Você dormiu durante o dia. Recuperou %d de mana (20%%).', restored))
    else
        local restored = G_.character.maxMana - G_.character.mana
        G_.character.mana = G_.character.maxMana
        State.addLog(string.format('😴 Você dormiu durante a noite. Recuperou toda sua mana! (+%d)', restored))
    end
    local lifeRestored = State.heal(math.floor(G_.character.maxLife * 0.2))
    State.addLog(string.format('❤️ Você recuperou %d de vida ao descansar.', lifeRestored))

    G_.isSleeping = false
    G_.sleepTimer = 0
    G_.stats.sleeps = (G_.stats.sleeps or 0) + 1
    Survival.onSleep()
    if early then
        State.addLog(string.format('⚠️ Você acordou cedo! O tempo avançou %d minutos.', math.floor(gameTime / 60)))
    end
end

function Time.wakeUp()
    local G_ = G()
    if not G_ or not G_.isSleeping then return end
    local slept = Time.SLEEP_SECONDS - (G_.sleepTimer or 0)
    State.addLog(string.format('⏰ Você acordou após %d segundo(s) de sono!', math.floor(slept)))
    Time.completeSleep(true, slept)
end

function Time.clockText()
    local G_ = G()
    local remaining = math.max(0, math.floor(G_.cycleRemaining or 0))
    return string.format('%02d:%02d', math.floor(remaining / 60), remaining % 60)
end

function Time.phaseText()
    local G_ = G()
    return G_.timeOfDay == 'day' and 'Dia' or 'Noite'
end

return Time
