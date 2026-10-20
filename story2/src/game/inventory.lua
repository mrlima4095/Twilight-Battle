-- Inventário, equipamento, baú, empilhamento e uso de itens.
local DB = require('src.data.init')
local State = require('src.game.state')
local U = require('src.core.util')

local Inventory = {}

Inventory.SLOTS = 18
Inventory.MAX_STACK = 64

local function G() return State.G end

function Inventory.copyItem(id)
    local base = DB.items[id]
    if not base then return nil end
    local item = U.deepcopy(base)
    item.id = id
    item.quantity = 1
    return item
end

function Inventory.stackable(item)
    if not item then return false end
    if item.slot then return false end
    local t = item.type
    if t == 'weapon' or t == 'armor' or t == 'shield' or t == 'tool' or t == 'station' then return false end
    if t == 'book' then return false end
    return true
end

local function stackKey(item)
    if not item then return nil end
    if item.type == 'book' then
        return table.concat({ item.id or '', item.title or '', item.content or '', tostring(item.signed) }, '|')
    end
    return item.id or ''
end

-- Coloca qty unidades em arr; devolve quantas sobraram.
function Inventory.addItem(arr, id, qty)
    local base = Inventory.copyItem(id)
    if not base then
        State.addLog('⚠️ Item desconhecido: ' .. tostring(id))
        return qty or 1
    end
    qty = qty or 1
    local leftover = qty
    if Inventory.stackable(base) then
        local key = stackKey(base)
        for i = 1, Inventory.SLOTS do
            local it = arr[i]
            if it and stackKey(it) == key then
                local space = (it.maxStack or Inventory.MAX_STACK) - (it.quantity or 1)
                local move = math.min(space, leftover)
                if move > 0 then
                    it.quantity = (it.quantity or 1) + move
                    leftover = leftover - move
                end
            end
        end
        if leftover > 0 then
            for i = 1, Inventory.SLOTS do
                if not arr[i] then
                    local move = math.min(Inventory.MAX_STACK, leftover)
                    local copy = U.deepcopy(base)
                    copy.quantity = move
                    arr[i] = copy
                    leftover = leftover - move
                    if leftover <= 0 then break end
                end
            end
        end
    else
        for i = 1, Inventory.SLOTS do
            if not arr[i] and leftover > 0 then
                local copy = U.deepcopy(base)
                copy.quantity = 1
                arr[i] = copy
                leftover = leftover - 1
            end
        end
    end
    if leftover > 0 then
        State.addLog(string.format('⚠️ Inventário cheio: %s ficou para trás.', DB.items[id] and DB.items[id].name or id))
    end
    return leftover
end

function Inventory.add(id, qty)
    local leftover = Inventory.addItem(G().inventory, id, qty)
    local Q = require('src.game.quests')
    if leftover < (qty or 1) then
        Q.trigger('item_acquired', { itemId = id })
    end
    return leftover
end

function Inventory.addToChest(id, qty)
    return Inventory.addItem(G().chest, id, qty)
end

function Inventory.count(arr, id)
    local n = 0
    for i = 1, Inventory.SLOTS do
        local it = arr[i]
        if it and it.id == id then n = n + (it.quantity or 1) end
    end
    return n
end

function Inventory.find(arr, id)
    for i = 1, Inventory.SLOTS do
        local it = arr[i]
        if it and it.id == id then return i end
    end
    return nil
end

function Inventory.removeAt(arr, index, qty)
    local it = arr[index]
    if not it then return 0 end
    qty = qty or 1
    local have = it.quantity or 1
    local taken = math.min(have, qty)
    if taken >= have then arr[index] = nil else it.quantity = have - taken end
    return taken
end

function Inventory.removeById(arr, id, qty)
    qty = qty or 1
    local removed = 0
    for i = 1, Inventory.SLOTS do
        if qty <= 0 then break end
        local it = arr[i]
        if it and it.id == id then
            removed = removed + Inventory.removeAt(arr, i, qty - removed)
        end
    end
    return removed
end

function Inventory.move(fromArr, fi, toArr, ti)
    if fi == ti and fromArr == toArr then return false end
    local from = fromArr[fi]
    if not from then return false end
    local to = toArr[ti]
    if to and Inventory.stackable(from) and Inventory.stackable(to) and stackKey(from) == stackKey(to) then
        local space = (to.maxStack or Inventory.MAX_STACK) - (to.quantity or 1)
        local move = math.min(space, from.quantity or 1)
        if move > 0 then
            to.quantity = (to.quantity or 1) + move
            from.quantity = (from.quantity or 1) - move
            if from.quantity <= 0 then fromArr[fi] = nil end
            return true
        end
    end
    if not to then
        toArr[ti] = from
        fromArr[fi] = nil
        return true
    end
    toArr[ti] = from
    fromArr[fi] = to
    return true
end

local TYPE_ORDER = {
    weapon = 1, armor = 2, shield = 3, tool = 4, station = 5,
    food = 6, drink = 7, material = 8, book = 9, container = 10, ammo = 11,
}

function Inventory.organize(arr)
    local items = {}
    for i = 1, Inventory.SLOTS do
        if arr[i] then items[#items + 1] = arr[i] end
    end
    table.sort(items, function(a, b)
        local oa = TYPE_ORDER[a.type] or 20
        local ob = TYPE_ORDER[b.type] or 20
        if oa ~= ob then return oa < ob end
        local na = DB.items[a.id] and DB.items[a.id].name or a.name or a.id or ''
        local nb = DB.items[b.id] and DB.items[b.id].name or b.name or b.id or ''
        return na < nb
    end)
    -- reempilha
    local merged = {}
    for _, it in ipairs(items) do
        local did = false
        if Inventory.stackable(it) then
            for _, m in ipairs(merged) do
                if stackKey(m) == stackKey(it) and (m.quantity or 1) < (m.maxStack or Inventory.MAX_STACK) then
                    local space = (m.maxStack or Inventory.MAX_STACK) - (m.quantity or 1)
                    local move = math.min(space, it.quantity or 1)
                    m.quantity = m.quantity + move
                    it.quantity = it.quantity - move
                    if it.quantity <= 0 then did = true break end
                end
            end
        end
        if not did then merged[#merged + 1] = it end
    end
    for i = 1, Inventory.SLOTS do arr[i] = merged[i] end
end

-- ───────────────────────────────────────────────────────── equipamento
function Inventory.bonuses()
    local G_ = G()
    local atk, def = 0, 0
    for _, item in pairs(G_.equipment) do
        if item then
            if (item.type == 'armor' or item.type == 'shield') and (item.durability or 1) <= 0 then
                -- quebrado: não protege
            else
                atk = atk + (item.attack or 0)
                def = def + (item.defense or 0)
            end
        end
    end
    return atk, def
end

function Inventory.totalAttack()
    local race = DB.races[G().character.race]
    local atk = Inventory.bonuses()
    return (race and race.baseAttack or 0) + atk
end

function Inventory.totalDefense()
    local race = DB.races[G().character.race]
    local _, def = Inventory.bonuses()
    return (race and race.baseDefense or 0) + def
end

function Inventory.equip(index)
    local G_ = G()
    local item = G_.inventory[index]
    if not item or not item.slot then return false, 'Este item não pode ser equipado.' end
    local slot = item.slot
    local current = G_.equipment[slot]
    G_.equipment[slot] = item
    G_.inventory[index] = nil
    if current then
        G_.inventory[index] = current
    end
    return true
end

function Inventory.unequip(slot)
    local G_ = G()
    local item = G_.equipment[slot]
    if not item then return false, 'Slot vazio.' end
    local free
    for i = 1, Inventory.SLOTS do
        if not G_.inventory[i] then free = i break end
    end
    if not free then return false, 'Inventário cheio.' end
    G_.inventory[free] = item
    G_.equipment[slot] = nil
    return true
end

function Inventory.itemValue(item)
    if not item then return 0 end
    if item.value ~= nil then return item.value end
    if item.type == 'food' then return math.max(1, math.floor((item.heal or 0) / 6 + 0.5)) end
    if item.type == 'drink' then return math.max(1, math.floor(((item.heal or 0) + (item.mana or 0)) / 8 + 0.5)) end
    if item.type == 'weapon' or item.type == 'tool' then
        return math.max(3, math.floor((item.attack or 3) * 2 + (item.maxDurability or 20) / 10 + 0.5))
    end
    if item.type == 'armor' or item.type == 'shield' then
        return math.max(3, math.floor((item.defense or 2) * 3 + (item.maxDurability or 20) / 10 + 0.5))
    end
    if item.type == 'material' then return math.max(1, math.floor((item.value or 1))) end
    return 1
end

-- ───────────────────────────────────────────────────────── uso
-- Retorna: acao, dado
function Inventory.use(index)
    local G_ = G()
    local item = G_.inventory[index]
    if not item then return nil end
    local Survival = require('src.game.survival')

    if item.type == 'food' or item.type == 'drink' then
        local healed = 0
        if item.heal and item.heal > 0 then healed = State.heal(item.heal) end
        if item.mana and item.mana > 0 then
            G_.character.mana = math.min(G_.character.maxMana, G_.character.mana + item.mana)
        end
        Survival.applyNutrition(item)
        if DB.ALCOHOL[item.id] then
            Survival.addSanity(-DB.ALCOHOL[item.id])
            State.addLog(string.format('🍺 O álcool turva sua mente (Sanidade −%d).', DB.ALCOHOL[item.id]))
        end
        G_.stats.foods = (G_.stats.foods or 0) + 1
        if healed > 0 then
            State.addLog(string.format('❤️ Você recuperou %d de vida com %s.', healed, DB.items[item.id].name))
        end
        local emptied
        if item.givesEmptyCup then emptied = item.givesEmptyCup
        elseif item.givesEmptyBottle then emptied = 'bottle' end
        Inventory.removeAt(G_.inventory, index, 1)
        if emptied then Inventory.add(emptied, 1) end
        return 'used'
    end

    if item.type == 'book' then
        return 'book', index
    end

    if item.useEffect == 'openMap' then
        return 'map'
    end

    if item.useEffect == 'showTimeRemaining' then
        return 'clock'
    end

    if item.type == 'station' then
        return 'station', item
    end

    if item.type == 'container' then
        return 'container', item
    end

    if item.slot then
        local ok, err = Inventory.equip(index)
        return ok and 'equipped' or 'error', err
    end

    return 'nothing', item
end

-- ───────────────────────────────────────────────────────── dano/armadura
-- Mesma regra do original: escudo, peitoral, calças, botas, capacete;
-- cada peça absorve até sua defesa e perde 1 de durabilidade se participou.
function Inventory.applyDamage(amount)
    local G_ = G()
    local order = {
        { slot = 'offhand', name = 'Escudo' },
        { slot = 'chest', name = 'Peitoral' },
        { slot = 'pants', name = 'Calças' },
        { slot = 'boots', name = 'Botas' },
        { slot = 'helmet', name = 'Capacete' },
    }
    local active = {}
    for _, o in ipairs(order) do
        local it = G_.equipment[o.slot]
        if it and (it.type == 'armor' or it.type == 'shield') and (it.durability or 0) > 0 then
            active[#active + 1] = { slot = o.slot, name = o.name, item = it }
        end
    end
    if #active == 0 then
        G_.character.life = math.max(0, G_.character.life - amount)
        State.addLog(string.format('💔 Sem armadura! Você perdeu %d de vida.', amount))
        if G_.character.life <= 0 then State.kill() end
        return 0, amount
    end
    local remaining = amount
    local absorbed = 0
    local took = {}
    for _, a in ipairs(active) do
        if remaining <= 0 then break end
        local take = math.min(remaining, a.item.defense or 0)
        if take > 0 then
            remaining = remaining - take
            absorbed = absorbed + take
            took[#took + 1] = a
            State.addLog(string.format('🛡️ %s (%s) absorveu %d de dano.', a.name, a.item.name, take))
        end
    end
    for _, a in ipairs(took) do
        a.item.durability = math.max(0, (a.item.durability or 1) - 1)
        if a.item.durability == 0 then
            State.addLog(string.format('⚠️ %s se quebrou e não oferece mais proteção!', a.item.name))
        end
    end
    if remaining > 0 then
        G_.character.life = math.max(0, G_.character.life - remaining)
        State.addLog(string.format('💔 Dano na vida: %d (Vida: %d/%d)', remaining, G_.character.life, G_.character.maxLife))
    elseif absorbed > 0 then
        State.addLog('✨ Todo o dano foi absorvido pelas armaduras!')
    end
    if G_.character.life <= 0 then State.kill() end
    return absorbed, remaining
end

-- Dano em ferramenta (picareta/machado): 1 por uso; quebra em 0.
function Inventory.damageTool(ref, n)
    if not ref then return end
    ref.durability = math.max(0, (ref.durability or 1) - (n or 1))
    if ref.durability == 0 then
        State.addLog(string.format('⚠️ Sua %s quebrou!', ref.name))
        Inventory.unequip('mainhand')
    end
end

function Inventory.mainhandTool(toolType)
    local it = G().equipment.mainhand
    if it and it.toolType == toolType and (it.durability or 0) > 0 then return it end
    return nil
end

function Inventory.hasItem(id)
    return Inventory.find(G().inventory, id) ~= nil
end

return Inventory
