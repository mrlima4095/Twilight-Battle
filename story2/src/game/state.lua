-- Estado do jogo, save/load e progressão.
local DB = require('src.data.init')
local U = require('src.core.util')
local JSON = require('src.core.json')

local State = {}

State.G = nil
State.SAVE_FILE = 'save.json'
State.VERSION = 2

local function emptySlots(n)
    local t = {}
    for i = 1, n do t[i] = nil end
    return t
end
State.emptySlots = emptySlots

function State.newCharacter(name, raceId, gender, age, bio)
    local race = DB.races[raceId]
    return {
        name = U.trim(name),
        race = raceId,
        gender = gender,
        age = tonumber(age) or 25,
        bio = bio ~= '' and bio or ((gender == 'masculino') and 'Um aventureiro em busca de glória.' or 'Uma aventureira em busca de glória.'),
        life = race.baseLife,
        maxLife = race.baseLife,
        mana = race.mana,
        maxMana = race.mana,
        gold = 10,
        exp = 0,
        level = 1,
    }
end

function State.reset()
    local G = {
        version = State.VERSION,
        character = nil,
        location = 'home',
        inventory = emptySlots(18),
        chest = emptySlots(18),
        equipment = { helmet = nil, chest = nil, pants = nil, boots = nil, mainhand = nil, offhand = nil },
        combatLog = {},
        enemy = nil,
        combatPanel = nil,
        isDead = false,
        learnedAbilities = {},
        learnedRecipes = {},
        dayCount = 1,
        seasonCount = 1,
        yearCount = 1540,
        timeOfDay = 'day',
        cycleDuration = 600,
        cycleRemaining = 600,
        isSleeping = false,
        sleepTimer = 0,
        weather = { id = 'clear' },
        survival = {
            hunger = 100, thirst = 100, sanity = 100,
            manaDebt = 0, flipsSinceSleep = 0,
            flags = { hunger = {}, thirst = {}, sanity = {}, extra = {} },
            tickAcc = 0,
        },
        activeQuest = nil,
        completedQuests = {},
        placedStations = {},
        furnaceJobs = {},
        millJobs = {},
        library = { reputation = 50, hasMembership = false, loans = {} },
        stats = {
            kills = 0, killsByType = {}, questsCompleted = 0, crafted = 0,
            recipes = {}, foods = 0, books = 0, npcs = {}, locations = {},
            purchases = 0, stations = 0, sleeps = 0, years = 1, yearAdvances = 0,
            travels = 0,
        },
        achievements = {},
        bestiary = {},
        shopMode = nil,
        flags = {},
        playSeconds = 0,
    }
    State.G = G
    return G
end

function State.startNew(name, raceId, gender, age, bio)
    local Inventory = require('src.game.inventory')
    local G = State.reset()
    G.character = State.newCharacter(name, raceId, gender, age, bio)
    G.stats.locations.home = true
    G.survival = {
        hunger = 100, thirst = 100, sanity = 100,
        manaDebt = 0, flipsSinceSleep = 0,
        flags = { hunger = {}, thirst = {}, sanity = {}, extra = {} },
        tickAcc = 0,
    }
    G.weather = State.rollWeather(1)
    -- itens iniciais (mesmo kit do original)
    Inventory.addItem(G.inventory, 'apple', 3)
    Inventory.addItem(G.inventory, 'bread', 2)
    Inventory.addItem(G.chest, 'clock', 1)
    return G
end

-- ───────────────────────────────────────────────────────────── log
function State.addLog(text)
    local G = State.G
    if not G then return end
    text = tostring(text)
    table.insert(G.combatLog, 1, text)
    while #G.combatLog > 400 do table.remove(G.combatLog) end
end

-- ───────────────────────────────────────────────────────────── clima
function State.rollWeather(season)
    season = season or (State.G and State.G.seasonCount) or 1
    local roll = love and love.math.random() or math.random()
    local id
    if season == 1 then
        id = roll < 0.55 and 'clear' or (roll < 0.8 and 'rain' or 'fog')
    elseif season == 2 then
        id = roll < 0.8 and 'clear' or 'storm'
    elseif season == 3 then
        id = roll < 0.7 and 'clear' or (roll < 0.9 and 'fog' or 'rain')
    else
        id = roll < 0.4 and 'snow' or (roll < 0.75 and 'fog' or 'clear')
    end
    local w = DB.weathers[id] or DB.weathers.clear
    return { id = w.id, name = w.name, icon = w.icon, encounterBonus = w.encounterBonus, damageMult = w.damageMult }
end

function State.weather()
    local G = State.G
    if G and G.weather then
        local w = DB.weathers[G.weather.id]
        if w then return w end
    end
    return DB.weathers.clear
end

-- ───────────────────────────────────────────────────────────── data/hora
function State.season()
    return DB.SEASONS[State.G.seasonCount] or DB.SEASONS[1]
end

function State.shortDate()
    local G = State.G
    return string.format('%dª %s %d', G.dayCount, State.season().short, G.yearCount)
end

function State.longDate()
    local G = State.G
    return string.format('%dº dia da %s de %d', G.dayCount, State.season().name, G.yearCount)
end

-- ───────────────────────────────────────────────────────────── progressão
function State.expNeeded()
    return 100 * (State.G.character.level or 1)
end

function State.grantLevelAbilities(count)
    local G = State.G
    local pool = DB.strikes.pool[G.character.race] or {}
    for _ = 1, count do
        for _, id in ipairs(pool) do
            local has = false
            for _, owned in ipairs(G.learnedAbilities) do
                if owned == id then has = true break end
            end
            if not has and DB.strikes.learnable[id] then
                G.learnedAbilities[#G.learnedAbilities + 1] = id
                local a = DB.strikes.learnable[id]
                State.addLog(string.format('✨ Nova habilidade aprendida: %s!', a.name))
                break
            end
        end
    end
end

function State.checkLevelUp()
    local G = State.G
    local c = G.character
    local leveled, count = false, 0
    while c.exp >= State.expNeeded() do
        c.exp = c.exp - State.expNeeded()
        c.level = c.level + 1
        leveled = true
        count = count + 1
    end
    if count > 0 then
        State.grantLevelAbilities(count)
        State.addLog(string.format('🌟 Você subiu para o nível %d!', c.level))
    end
    return leveled
end

function State.addExp(amount)
    if amount <= 0 or State.G.isDead then return false end
    local G = State.G
    G.character.exp = G.character.exp + amount
    State.addLog(string.format('✨ +%d EXP!', amount))
    return State.checkLevelUp()
end

-- ───────────────────────────────────────────────────────────── morte
function State.kill(reason)
    local G = State.G
    if G.isDead then return end
    G.isDead = true
    G.character.life = 0
    State.addLog('💀 VOCÊ MORREU!')
    if reason then State.addLog(reason) end
    State.deleteSave()
end

function State.heal(amount)
    local c = State.G.character
    local before = c.life
    c.life = math.min(c.maxLife, c.life + amount)
    return c.life - before
end

function State.damage(amount)
    local G = State.G
    G.character.life = math.max(0, G.character.life - amount)
    if G.character.life <= 0 then State.kill() end
    return G.character.life
end

-- ───────────────────────────────────────────────────────────── save/load
local function normalize(G)
    if type(G) ~= 'table' or type(G.character) ~= 'table' then return nil end
    G.inventory = G.inventory or {}
    G.chest = G.chest or {}
    for i = 1, 18 do
        if G.inventory[i] == nil then G.inventory[i] = false end
        if G.chest[i] == nil then G.chest[i] = false end
    end
    local eq = G.equipment or {}
    G.equipment = {
        helmet = eq.helmet, chest = eq.chest, pants = eq.pants,
        boots = eq.boots, mainhand = eq.mainhand, offhand = eq.offhand,
    }
    local sv = G.survival or {}
    G.survival = {
        hunger = U.clamp(tonumber(sv.hunger) or 100, 0, 100),
        thirst = U.clamp(tonumber(sv.thirst) or 100, 0, 100),
        sanity = U.clamp(tonumber(sv.sanity) or 100, 0, 100),
        manaDebt = tonumber(sv.manaDebt) or 0,
        flipsSinceSleep = tonumber(sv.flipsSinceSleep) or 0,
        flags = sv.flags or { hunger = {}, thirst = {}, sanity = {}, extra = {} },
        tickAcc = 0,
    }
    -- JSON transforma chaves numéricas em strings; o progresso das missões
    -- usa índices numéricos (0 = primeira etapa).
    if type(G.activeQuest) == 'table' and type(G.activeQuest.stageProgress) == 'table' then
        local sp = {}
        for k, v in pairs(G.activeQuest.stageProgress) do
            local n = tonumber(k)
            if n then sp[n] = tonumber(v) or 0 end
        end
        G.activeQuest.stageProgress = sp
    end
    G.timeOfDay = G.timeOfDay or 'day'
    G.cycleDuration = G.cycleDuration or 600
    G.cycleRemaining = tonumber(G.cycleRemaining) or G.cycleDuration
    G.dayCount = tonumber(G.dayCount) or 1
    G.seasonCount = tonumber(G.seasonCount) or 1
    G.yearCount = tonumber(G.yearCount) or 1540
    G.weather = G.weather or { id = 'clear' }
    G.learnedAbilities = G.learnedAbilities or {}
    G.learnedRecipes = G.learnedRecipes or {}
    G.completedQuests = G.completedQuests or {}
    G.combatLog = G.combatLog or {}
    G.flags = G.flags or {}
    G.placedStations = G.placedStations or {}
    G.furnaceJobs = G.furnaceJobs or {}
    G.millJobs = G.millJobs or {}
    G.stats = G.stats or {}
    local st = G.stats
    st.kills = st.kills or 0
    st.killsByType = st.killsByType or {}
    st.questsCompleted = st.questsCompleted or 0
    st.crafted = st.crafted or 0
    st.recipes = st.recipes or {}
    st.foods = st.foods or 0
    st.books = st.books or 0
    st.npcs = st.npcs or {}
    st.locations = st.locations or {}
    st.purchases = st.purchases or 0
    st.stations = st.stations or 0
    st.sleeps = st.sleeps or 0
    st.years = st.years or 1
    st.yearAdvances = st.yearAdvances or 0
    st.travels = st.travels or 0
    G.achievements = G.achievements or {}
    G.bestiary = G.bestiary or {}
    G.library = G.library or { reputation = 50, hasMembership = false, loans = {} }
    G.character.life = U.clamp(tonumber(G.character.life) or 1, 0, tonumber(G.character.maxLife) or 1)
    G.character.mana = U.clamp(tonumber(G.character.mana) or 0, 0, tonumber(G.character.maxMana) or 0)
    G.character.level = math.max(1, tonumber(G.character.level) or 1)
    G.character.exp = math.max(0, tonumber(G.character.exp) or 0)
    G.character.gold = math.max(0, tonumber(G.character.gold) or 0)
    G.enemy = nil
    G.isDead = G.isDead == true
    G.sleepTimer = 0
    G.isSleeping = false
    -- limpa slots "false" para nil (JSON não guarda nil no meio)
    for i = 1, 18 do
        if G.inventory[i] == false then G.inventory[i] = nil end
        if G.chest[i] == false then G.chest[i] = nil end
    end
    -- garante ids dos itens (saves antigos podem não ter)
    for _, arr in ipairs({ G.inventory, G.chest }) do
        for i = 1, 18 do
            local it = arr[i]
            if type(it) == 'table' then
                it.id = it.id or nil
                if not it.name and it.id and DB.items[it.id] then it.name = DB.items[it.id].name end
                it.quantity = math.max(1, tonumber(it.quantity) or 1)
            end
        end
    end
    return G
end

function State.hasSave()
    return love.filesystem.getInfo(State.SAVE_FILE) ~= nil
end

function State.save(silent)
    local G = State.G
    if not G or not G.character or G.isDead then return false end
    local ok, encoded = pcall(JSON.encode, G)
    if not ok then
        State.addLog('⚠️ Falha ao serializar o save.')
        return false
    end
    if silent then
        local old = love.filesystem.read(State.SAVE_FILE)
        if old then love.filesystem.write('save_backup.json', old) end
    end
    local wrote, err = love.filesystem.write(State.SAVE_FILE, encoded)
    if not wrote then
        State.addLog('⚠️ Não foi possível salvar: ' .. tostring(err))
        return false
    end
    if not silent then State.addLog('💾 Jogo salvo.') end
    return true
end

function State.load()
    local data = love.filesystem.read(State.SAVE_FILE)
    if not data then return false, 'Save não encontrado.' end
    local G, err = JSON.decode(data)
    if not G then return false, 'Save corrompido: ' .. tostring(err) end
    G = normalize(G)
    if not G then return false, 'Save inválido.' end
    State.G = G
    return true
end

function State.deleteSave()
    if love.filesystem.getInfo(State.SAVE_FILE) then
        love.filesystem.remove(State.SAVE_FILE)
    end
end

-- Chamado pelo main.lua ao sair.
function State.onQuit()
    local G = State.G
    if G and G.character and not G.isDead then
        State.save(true)
    end
end

return State
