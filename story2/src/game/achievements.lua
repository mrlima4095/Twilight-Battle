-- Conquistas: mesmas condições de static/js/story/systems.js (TB_ACHIEVEMENTS).
local DB = require('src.data.init')
local State = require('src.game.state')

local A = {}

local function G() return State.G end

local function locationsCount()
    local n = 0
    for _ in pairs(G().stats.locations or {}) do n = n + 1 end
    return n
end

local function recipesCount()
    local n = 0
    for _ in pairs(G().stats.recipes or {}) do n = n + 1 end
    return n
end

local function npcsCount()
    local n = 0
    for _ in pairs(G().stats.npcs or {}) do n = n + 1 end
    return n
end

local function bestiaryCount()
    local n = 0
    for _ in pairs(G().bestiary or {}) do n = n + 1 end
    return n
end

local function completed(id)
    for _, q in ipairs(G().completedQuests or {}) do
        if q == id then return true end
    end
    return false
end

A.checks = {
    primeira_missao = function(s) return (s.questsCompleted or 0) >= 1 end,
    heroi_do_reino = function() return completed('main_two_crowns') end,
    cacador_de_lobos = function(s) return (s.killsByType.wolf or 0) >= 25 end,
    matador_de_dragoes = function(s) return (s.killsByType.dragon or 0) >= 1 end,
    acougueiro = function(s) return (s.kills or 0) >= 50 end,
    andarilho = function() return locationsCount() >= 10 end,
    viajante = function() return locationsCount() >= 20 end,
    aguas_sagradas = function(s) return (s.locations or {}).sacred_lake == true end,
    terras_selvagens = function(s) return (s.locations or {}).dark_forest == true end,
    atravessando_fronteiras = function(s) return (s.locations or {}).twilight_gate == true end,
    mestre_dos_mapas = function() return completed('pedro_map') end,
    fortuna_modesta = function() return G().character and G().character.gold >= 250 end,
    magnata = function() return G().character and G().character.gold >= 1000 end,
    tesouro_real = function() return G().character and G().character.gold >= 5000 end,
    comerciante = function(s) return (s.purchases or 0) >= 10 end,
    artesao = function(s) return (s.crafted or 0) >= 10 end,
    faz_tudo = function() return recipesCount() >= 5 end,
    estomago_de_aco = function(s) return (s.foods or 0) >= 25 end,
    engenheiro = function(s) return (s.stations or 0) >= 3 end,
    amigos_de_todos = function() return npcsCount() >= 8 end,
    leitor_registrado = function(s) return (s.books or 0) >= 1 end,
    devorador_de_livros = function(s) return (s.books or 0) >= 5 end,
    reputacao_exemplar = function() return (G().library and G().library.reputation or 0) >= 80 end,
    bestiario = function() return bestiaryCount() >= 6 end,
    ano_novo = function(s) return (s.years or 1) >= (G().yearCount or 1540) and (s.yearAdvances or 0) >= 1 end,
    madrugador = function(s) return (s.sleeps or 0) >= 1 end,
}

function A.unlock(id)
    local G_ = G()
    local def
    for _, a in ipairs(DB.achievements) do
        if a.id == id then def = a break end
    end
    if not def then return end
    G_.achievements[id] = true
    State.addLog(string.format('🏆 CONQUISTA DESBLOQUEADA: %s', def.name))
    local UI = require('src.core.ui')
    UI.toast(string.format('🏆 Conquista: %s — %s', def.name, def.desc or ''), 4.5)
end

function A.check()
    local G_ = G()
    if not G_ or not G_.character then return end
    G_.achievements = G_.achievements or {}
    local s = G_.stats or {}
    for _, ach in ipairs(DB.achievements) do
        if not G_.achievements[ach.id] then
            local fn = A.checks[ach.id]
            local ok = false
            if fn then
                local success, res = pcall(fn, s)
                ok = success and res == true
            end
            if ok then A.unlock(ach.id) end
        end
    end
end

function A.count()
    local n = 0
    local total = 0
    for _ in pairs(G().achievements or {}) do n = n + 1 end
    for _ in ipairs(DB.achievements) do total = total + 1 end
    return n, total
end

function A.list()
    local out = {}
    for _, a in ipairs(DB.achievements) do
        out[#out + 1] = {
            id = a.id, name = a.name, icon = a.icon, desc = a.desc,
            unlocked = G().achievements[a.id] == true,
        }
    end
    return out
end

return A
