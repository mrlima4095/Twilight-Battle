package.path = './?.lua;' .. package.path
local function fontObj(size)
    return {
        getWidth = function(_, s) return #tostring(s or '') * 7 end,
        getHeight = function() return size or 12 end,
        getWrap = function(_, str, limit) return limit or 1000, { tostring(str or '') } end,
    }
end
love = {
    math = { random = function(a) if a == nil then return 0.5 end return math.random(a) end, setRandomSeed = function() end },
    timer = { getTime = function() return os.clock() end },
    graphics = {
        newFont = function(a, b) if type(a) == 'number' then return fontObj(a) end return fontObj(b or 12) end,
        setDefaultFilter = function() end, setColor = function() end, setFont = function() end,
        setLineWidth = function() end, rectangle = function() end, circle = function() end,
        line = function() end, polygon = function() end, print = function() end, printf = function() end,
        push = function() end, pop = function() end, translate = function() end, scale = function() end,
        setScissor = function() end, clear = function() end, getDimensions = function() return 1280, 720 end,
    },
    filesystem = { read = function() return nil end, write = function() return true end, getInfo = function() return nil end, remove = function() return true end },
    window = { getFullscreen = function() return false end, setFullscreen = function() end },
    mouse = { getPosition = function() return 0, 0 end, isDown = function() return false end },
    event = { quit = function() end },
}

local State = require('src.game.state')
local Inventory = require('src.game.inventory')
local Actions = require('src.game.actions')
local DB = require('src.data.init')
local Theme = require('src.core.theme')
Theme.load()

local G = State.startNew('Cover', 'elf', 'feminino', 30, '')
G.character.life = G.character.maxLife
G.character.gold = 5000
G.timeOfDay = 'day'
Inventory.add('bottle', 2)
Inventory.add('tocha', 4)
Inventory.add('wood', 20)
Inventory.add('picareta_ferro', 1)
Inventory.add('machado_ferro', 1)
local pi = Inventory.find(G.inventory, 'picareta_ferro')
Inventory.equip(pi)

local unported = {}
local seen = {}
for locId, loc in pairs(DB.locations) do
    for _, a in ipairs(loc.actions or {}) do
        if not seen[a.action] then
            seen[a.action] = true
            G.location = locId
            G.enemy = nil
            G.isDead = false
            G.character.life = G.character.maxLife
            G.character.mana = G.character.maxMana
            G.combatLog = {}
            Actions.perform(a.action)
            for _, line in ipairs(G.combatLog) do
                if line:find('não portada', 1, true) then
                    unported[#unported + 1] = string.format('%s em %s', a.action, locId)
                end
            end
        end
    end
end
print('Ações distintas testadas: ' .. (function() local n = 0 for _ in pairs(seen) do n = n + 1 end return n end)())
if #unported == 0 then
    print('Todas as ações de localização estão implementadas.')
else
    print('NÃO PORTADAS (' .. #unported .. '):')
    for _, u in ipairs(unported) do print('  ' .. u) end
end
