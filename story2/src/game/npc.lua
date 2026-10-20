-- NPCs: conversa, tópicos, lojas e venda.
local DB = require('src.data.init')
local State = require('src.game.state')
local Inventory = require('src.game.inventory')
local Quests = require('src.game.quests')
local Achievements = require('src.game.achievements')

local NPC = {}

local function G() return State.G end

function NPC.get(id)
    return DB.npcs[id]
end

function NPC.listAt(locationId)
    local out = {}
    for _, npc in pairs(DB.npcs) do
        if npc.location == locationId then out[#out + 1] = npc end
    end
    table.sort(out, function(a, b) return (a.name or '') < (b.name or '') end)
    return out
end

function NPC.greeting(npc)
    if not npc then return '' end
    local G_ = G()
    local pronoun = G_.character.gender == 'masculino' and 'o' or 'a'
    local base
    if npc.title and npc.title ~= '' then
        base = string.format('Bem-vind%s! Sou %s, %s por aqui.', pronoun, npc.name, npc.title)
    else
        base = string.format('Olá, %s! Sou %s.', G_.character.name, npc.name)
    end
    if G_.timeOfDay == 'night' and npc.sleepingMessage then
        return base .. ' A esta hora, já deveria estar descansando... mas posso falar um pouco.'
    end
    return base
end

function NPC.farewell(npc)
    if npc and npc.farewell then return npc.farewell end
    return string.format('Até a próxima, %s!', G().character.name)
end

function NPC.talk(npcId)
    local npc = DB.npcs[npcId]
    if not npc then return false end
    local G_ = G()
    G_.stats.npcs[npcId] = true
    Quests.trigger('npc_talk', { npcId = npcId })
    Achievements.check()
    State.addLog(string.format('💬 Você conversa com %s (%s).', npc.name, npc.title or 'morador'))
    return true
end

function NPC.say(npcId, message)
    local npc = DB.npcs[npcId]
    if npc then
        State.addLog(string.format('💬 %s: %s', npc.name, message))
    end
end

-- ───────────────────────────────────────────────────────── loja
function NPC.buy(npcId, itemId)
    local npc = DB.npcs[npcId]
    if not npc then return false, 'NPC inválido.' end
    local entry
    for _, s in ipairs(npc.shopItems or {}) do
        if s.id == itemId then entry = s break end
    end
    if not entry then return false, 'Este NPC não vende este item.' end
    local price = entry.price or 1
    local G_ = G()
    if G_.character.gold < price then
        return false, string.format('Ouro insuficiente (precisa de %d).', price)
    end
    if not DB.items[itemId] then return false, 'Item desconhecido.' end
    G_.character.gold = G_.character.gold - price
    Inventory.add(itemId, entry.quantity or 1)
    G_.stats.purchases = (G_.stats.purchases or 0) + 1
    State.addLog(string.format('🛒 Você comprou %s por %d moedas.', DB.items[itemId].name, price))
    Achievements.check()
    return true
end

function NPC.sellValue(item)
    return math.max(1, math.floor(Inventory.itemValue(item) * 0.5))
end

function NPC.sell(npcId, index)
    local npc = DB.npcs[npcId]
    if not npc then return false end
    if not npc.canSellToNPC then
        return false, string.format('%s não compra itens.', npc.name)
    end
    local item = G().inventory[index]
    if not item then return false end
    local price = NPC.sellValue(item)
    G().character.gold = G().character.gold + price
    State.addLog(string.format('💰 Você vendeu %s por %d moedas.', item.name, price))
    Inventory.removeAt(G().inventory, index, 1)
    return true
end

function NPC.shopItems(npcId)
    local npc = DB.npcs[npcId]
    if not npc then return {} end
    return npc.shopItems or {}
end

return NPC
