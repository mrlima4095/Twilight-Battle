-- Estações de trabalho: bancada, tear, moinho, fornalha e bigorna.
local DB = require('src.data.init')
local State = require('src.game.state')
local Inventory = require('src.game.inventory')
local Achievements = require('src.game.achievements')

local Craft = {}

local function G() return State.G end

Craft.STATIONS = {
    crafting_table = { name = 'Bancada de Trabalho', icon = '🔨' },
    loom = { name = 'Tear', icon = '🧵' },
    mill = { name = 'Moinho', icon = '🌾' },
    furnace = { name = 'Fornalha', icon = '🔥' },
    anvil = { name = 'Bigorna', icon = '⚒️' },
    alchemy = { name = 'Mesa de Alquimia', icon = '⚗️' },
    sleeping_bag = { name = 'Saco de Dormir', icon = '🛏️' },
}

function Craft.stationInfo(stationType)
    return Craft.STATIONS[stationType] or { name = stationType or 'Estação', icon = '🔧' }
end

function Craft.recipesFor(stationType)
    local out = {}
    for key, r in pairs(DB.recipes.crafting) do
        if r.station == stationType then
            out[#out + 1] = { key = key, def = r }
        end
    end
    table.sort(out, function(a, b) return (a.def.name or a.key) < (b.def.name or b.key) end)
    return out
end

function Craft.materialsText(recipe)
    local parts = {}
    for _, m in ipairs(recipe.materials or {}) do
        local item = DB.items[m.id]
        parts[#parts + 1] = string.format('%s x%d', item and item.name or m.id, m.quantity or 1)
    end
    return table.concat(parts, ' · ')
end

function Craft.canCraft(recipe)
    for _, m in ipairs(recipe.materials or {}) do
        if Inventory.count(G().inventory, m.id) < (m.quantity or 1) then
            return false, DB.items[m.id] and DB.items[m.id].name or m.id
        end
    end
    if recipe.requires_learn then
        if not G().learnedRecipes[recipe.result] then
            return false, 'Receita não aprendida'
        end
    end
    return true
end

function Craft.craft(key)
    local recipe = DB.recipes.crafting[key]
    if not recipe then return false end
    local ok, missing = Craft.canCraft(recipe)
    if not ok then
        State.addLog(string.format('❌ Faltam materiais: %s.', missing))
        return false
    end
    for _, m in ipairs(recipe.materials or {}) do
        Inventory.removeById(G().inventory, m.id, m.quantity or 1)
    end
    Inventory.add(recipe.result, recipe.quantity or 1)
    local resultItem = DB.items[recipe.result]
    State.addLog(string.format('🔨 Você criou %s x%d!', resultItem and resultItem.name or recipe.result, recipe.quantity or 1))
    G().stats.crafted = (G().stats.crafted or 0) + 1
    G().stats.recipes[recipe.result] = true
    Achievements.check()
    return true
end

-- ───────────────────────────────────────────────────────── fornalha
function Craft.furnaceRecipes()
    local out = {}
    for key, r in pairs(DB.recipes.furnace) do
        out[#out + 1] = { key = key, def = r }
    end
    table.sort(out, function(a, b) return (a.def.resultName or a.key) < (b.def.resultName or b.key) end)
    return out
end

function Craft.startSmelt(key)
    local r = DB.recipes.furnace[key]
    if not r then return false, 'Receita inválida.' end
    if Inventory.count(G().inventory, r.input) < 1 then
        return false, 'Sem ' .. (DB.items[r.input] and DB.items[r.input].name or r.input) .. '.'
    end
    local fuelId, fuel
    for id in pairs(DB.FUEL) do
        if Inventory.count(G().inventory, id) > 0 then fuelId = id fuel = DB.FUEL[id] break end
    end
    if not fuelId then
        return false, 'Sem combustível (madeira, papel ou carvão).'
    end
    Inventory.removeById(G().inventory, r.input, 1)
    Inventory.removeById(G().inventory, fuelId, 1)
    table.insert(G().furnaceJobs, {
        input = r.input, result = r.result, resultName = r.resultName,
        cookTime = r.cookTime or 5, elapsed = 0, fuel = fuelId,
    })
    State.addLog(string.format('🔥 %s começou a assar/fundir.', DB.items[r.input] and DB.items[r.input].name or r.input))
    return true
end

function Craft.collectSmelt(index)
    local job = G().furnaceJobs[index]
    if not job then return false end
    if job.elapsed < job.cookTime then
        return false, 'Ainda está no fogo.'
    end
    table.remove(G().furnaceJobs, index)
    Inventory.add(job.result, 1)
    State.addLog(string.format('✅ %s está pronto: %s!', job.resultName or 'Item', DB.items[job.result] and DB.items[job.result].name or job.result))
    return true
end

-- ───────────────────────────────────────────────────────── moinho
function Craft.millRecipes()
    local out = {}
    for key, r in pairs(DB.recipes.crafting) do
        if r.station == 'mill' then out[#out + 1] = { key = key, def = r } end
    end
    table.sort(out, function(a, b) return (a.def.name or a.key) < (b.def.name or b.key) end)
    return out
end

function Craft.startMill(key)
    local r = DB.recipes.crafting[key]
    if not r or r.station ~= 'mill' then return false, 'Receita inválida.' end
    if Inventory.count(G().inventory, r.materials[1].id) < (r.materials[1].quantity or 1) then
        return false, 'Faltam materiais.'
    end
    for _, m in ipairs(r.materials) do
        Inventory.removeById(G().inventory, m.id, m.quantity or 1)
    end
    table.insert(G().millJobs, {
        result = r.result, resultName = r.name,
        millTime = r.millTime or 3, elapsed = 0,
    })
    State.addLog('⚙️ O moinho começou a girar...')
    return true
end

function Craft.collectMill(index)
    local job = G().millJobs[index]
    if not job then return false end
    if job.elapsed < job.millTime then return false, 'Ainda está moendo.' end
    table.remove(G().millJobs, index)
    Inventory.add(job.result, 1)
    State.addLog(string.format('✅ Moagem concluída: %s!', DB.items[job.result] and DB.items[job.result].name or job.result))
    return true
end

function Craft.update(dt)
    local G_ = G()
    if not G_ then return end
    for _, job in ipairs(G_.furnaceJobs or {}) do
        if job.elapsed < job.cookTime then
            job.elapsed = math.min(job.cookTime, job.elapsed + dt)
        end
    end
    for _, job in ipairs(G_.millJobs or {}) do
        if job.elapsed < job.millTime then
            job.elapsed = math.min(job.millTime, job.elapsed + dt)
        end
    end
end

-- ───────────────────────────────────────────────────────── bigorna
function Craft.repairCost(item)
    local max = item.maxDurability or 0
    local cur = item.durability or 0
    return math.max(1, (max - cur) * 2)
end

function Craft.repair(item)
    if not item or not item.maxDurability then return false, 'Este item não pode ser reparado.' end
    local cost = Craft.repairCost(item)
    if G().character.gold < cost then
        return false, string.format('Faltam %d moedas.', cost - G().character.gold)
    end
    if (item.durability or 0) >= item.maxDurability then
        return false, 'Já está em ótimo estado.'
    end
    G().character.gold = G().character.gold - cost
    item.durability = item.maxDurability
    State.addLog(string.format('⚒️ %s reparado por %d moedas.', item.name, cost))
    return true
end

function Craft.enhanceCost(item)
    local n = item.enhance or 0
    return 40 + n * 35
end

function Craft.enhance(item)
    if not item then return false end
    if (item.enhance or 0) >= 5 then return false, 'Já está no reforço máximo (+5).' end
    local cost = Craft.enhanceCost(item)
    if G().character.gold < cost then
        return false, string.format('Faltam %d moedas.', cost - G().character.gold)
    end
    G().character.gold = G().character.gold - cost
    item.enhance = (item.enhance or 0) + 1
    if (item.attack or 0) > 0 then
        item.attack = item.attack + 2
    elseif (item.defense or 0) > 0 then
        item.defense = item.defense + 2
    else
        item.attack = (item.attack or 0) + 1
        item.defense = (item.defense or 0) + 1
    end
    State.addLog(string.format('✨ %s reforçado para +%d!', item.name, item.enhance))
    return true
end

-- Itens reparáveis/ reforçáveis: equipados + inventário.
function Craft.repairableItems()
    local out = {}
    for slot, item in pairs(G().equipment) do
        if item and item.maxDurability then
            out[#out + 1] = { item = item, where = 'Equipado (' .. slot .. ')' }
        end
    end
    for i = 1, Inventory.SLOTS do
        local it = G().inventory[i]
        if it and it.maxDurability then
            out[#out + 1] = { item = it, where = 'Inventário' }
        end
    end
    return out
end

return Craft
