-- Modais do jogo: NPC, baú, estações, missões, diário, mina, livro,
-- sono, perfil, menu, final e morte. A tela do jogo chama Modals.handle().
local UI = require('src.core.ui')
local Theme = require('src.core.theme')
local Text = require('src.core.text')
local DB = require('src.data.init')
local State = require('src.game.state')
local Inventory = require('src.game.inventory')
local Time = require('src.game.time')
local Survival = require('src.game.survival')
local Quests = require('src.game.quests')
local NPC = require('src.game.npc')
local Craft = require('src.game.craft')
local MG = require('src.game.minigame')
local Achievements = require('src.game.achievements')
local Actions = require('src.game.actions')
local Map = require('src.screens.map')
local Manager = require('src.screens.manager')
local U = require('src.core.util')

local Modals = {}

local function G() return State.G end

-- ───────────────────────────────────────────────────────── utilidades
local function typeLabel(item)
    local t = item.type or 'item'
    local map = {
        weapon = 'Arma', armor = 'Armadura', shield = 'Escudo', tool = 'Ferramenta',
        food = 'Comida', drink = 'Bebida', material = 'Material', book = 'Livro',
        station = 'Estação', container = 'Recipiente', ammo = 'Munição',
        library_card = 'Cartão', quest_item = 'Item de missão',
    }
    return map[t] or t
end

local function itemSummary(item)
    if not item then return '' end
    local parts = { typeLabel(item) }
    if (item.attack or 0) > 0 then parts[#parts + 1] = 'ATQ +' .. item.attack end
    if (item.defense or 0) > 0 then parts[#parts + 1] = 'DEF +' .. item.defense end
    if item.heal and item.heal > 0 then parts[#parts + 1] = 'Vida +' .. item.heal end
    if item.mana and item.mana > 0 then parts[#parts + 1] = 'Mana +' .. item.mana end
    if item.maxDurability then
        parts[#parts + 1] = string.format('Dur %d/%d', item.durability or 0, item.maxDurability)
    end
    if item.quantity and item.quantity > 1 then parts[#parts + 1] = 'x' .. item.quantity end
    return table.concat(parts, ' · ')
end

local function tooltipItem(item)
    if not item then return end
    local lines = { item.name or item.id or '?' }
    lines[#lines + 1] = itemSummary(item)
    if item.description and item.description ~= '' then lines[#lines + 1] = item.description end
    UI.tooltip(table.concat(lines, '\n'))
end

local function section(text, x, y, w, color)
    Text.draw(Theme.font.bold, text, x, y, w, 'left', color or Theme.color.gold)
    UI.divider(x, y + 19, w, 0.08)
end

local function pill(x, y, w, h, text, color)
    love.graphics.setColor(0, 0, 0, 0.30)
    love.graphics.rectangle('fill', x, y, w, h, h * 0.5, h * 0.5)
    love.graphics.setColor(color[1], color[2], color[3], 0.22)
    love.graphics.rectangle('fill', x, y, w, h, h * 0.5, h * 0.5)
    Text.draw(Theme.font.xs, text, x + 4, y + (h - Theme.font.xs:getHeight()) * 0.5 - 1, w - 8, 'center', color)
end

local function valueRow(label, value, x, y, w, color)
    Text.draw(Theme.font.sm, label, x, y, w * 0.6, 'left', Theme.color.muted)
    Text.draw(Theme.font.bold, tostring(value), x + w * 0.6, y, w * 0.4, 'right', color or Theme.color.text)
end

local function questRewardText(quest)
    local parts = {}
    for _, r in ipairs(quest.rewards or {}) do
        if r.gold then parts[#parts + 1] = r.gold .. ' moedas' end
        if r.exp then parts[#parts + 1] = r.exp .. ' EXP' end
        if r.item then
            local it = DB.items[r.item]
            parts[#parts + 1] = (it and it.name or r.item) .. (r.itemQty and (' x' .. r.itemQty) or '')
        end
    end
    return table.concat(parts, ' · ')
end

local function stageName(stage)
    return stage and (stage.name or stage.type or '?') or '?'
end

local function stageProgressText(stage, current, idx, activeIdx)
    local done = idx < activeIdx
    local currentOne = idx == activeIdx
    local p, need = 0, stage.required or 1
    if currentOne then
        p = current or 0
    elseif done then
        p, need = need, need
    end
    return string.format('%s %s (%d/%d)', done and '[x]' or (currentOne and '>' or '[ ]'),
        stageName(stage), p, need)
end

-- ───────────────────────────────────────────────────────── NPC
local npcState = { id = nil, tab = 'home', topic = nil }

function Modals.openNpc(id)
    local npc = DB.npcs[id]
    if not npc then
        UI.toast('NPC não encontrado: ' .. tostring(id))
        return
    end
    npcState = { id = id, tab = 'home', topic = nil }
    NPC.talk(id)
    UI.openModal({
        kind = 'npc',
        title = string.format('%s — %s', npc.name, npc.title or 'morador'),
        icon = '💬',
        width = 820,
        height = 590,
        body = function(x, y, w, h)
            local G_ = G()
            -- cabeçalho
            love.graphics.setColor(Theme.color.purple[1], Theme.color.purple[2], Theme.color.purple[3], 0.30)
            love.graphics.circle('fill', x + 32, y + 32, 28)
            love.graphics.circle('line', x + 32, y + 32, 28)
            Text.draw(Theme.font.xl, (npc.name or '?'):sub(1, 1), x + 12, y + 16, 40, 'center', Theme.color.gold)
            Text.draw(Theme.font.boldMd, npc.name, x + 70, y + 8, w - 80, 'left', Theme.color.text)
            Text.draw(Theme.font.sm, string.format('%s · %s', npc.title or 'Morador', npc.locationName or npc.location or ''),
                x + 70, y + 30, w - 80, 'left', Theme.color.muted)
            local greeting = NPC.greeting(npc)
            Text.draw(Theme.font.sm, greeting, x + 70, y + 50, w - 80, 'left', Theme.color.text, 1.25)

            -- abas
            local hasShop = npc.shopItems and #npc.shopItems > 0
            local tabs = { { id = 'home', label = 'Conversar' } }
            if hasShop then tabs[#tabs + 1] = { id = 'shop', label = 'Comprar' } end
            if npc.canSellToNPC then tabs[#tabs + 1] = { id = 'sell', label = 'Vender' } end
            local tx = x
            for _, t in ipairs(tabs) do
                local tw = 120
                if UI.button('npc_tab_' .. t.id, tx, y + 86, tw, 32, t.label, {
                    style = npcState.tab == t.id and 'default' or 'ghost',
                    onClick = function() npcState.tab = t.id npcState.topic = nil end,
                }) then end
                tx = tx + tw + 8
            end
            pill(x + w - 150, y + 86, 150, 32, string.format('💰 %d moedas', G_.character.gold), Theme.color.gold)

            local cy = y + 128
            local ch = h - 146
            UI.scroll('npc_' .. npcState.tab .. '_' .. id, x, cy, w, ch, function(sx, sy, sw)
                local row = 0
                if npcState.tab == 'home' then
                    Text.draw(Theme.font.sm, 'Sobre o que você quer falar?', sx, sy, sw, 'left', Theme.color.muted)
                    row = 26
                    for i, topic in ipairs(npc.topics or {}) do
                        if UI.button('topic_' .. i, sx, sy + row, sw, 34, topic.name or ('Assunto ' .. i), {
                            style = 'ghost', font = Theme.font.sm,
                            onClick = function() npcState.topic = topic.message or '' end,
                        }) then end
                        row = row + 40
                    end
                    if npcState.topic and npcState.topic ~= '' then
                        row = row + 6
                        local lines = Text.wrap(Theme.font.sm, npcState.topic, sw - 24)
                        local bh = math.max(54, #lines * Theme.font.sm:getHeight() * 1.3 + 20)
                        love.graphics.setColor(0, 0, 0, 0.30)
                        love.graphics.rectangle('fill', sx, sy + row, sw, bh, 8, 8)
                        love.graphics.setColor(Theme.color.gold[1], Theme.color.gold[2], Theme.color.gold[3], 0.35)
                        love.graphics.rectangle('fill', sx, sy + row + 6, 3, bh - 12, 2, 2)
                        Text.draw(Theme.font.sm, npc.topic, sx + 14, sy + row + 10, sw - 28, 'left', Theme.color.text, 1.3)
                        row = row + bh + 10
                    end
                    return row
                elseif npcState.tab == 'shop' then
                    Text.draw(Theme.font.xs, 'Clique em comprar para levar uma unidade.', sx, sy, sw, 'left', Theme.color.muted)
                    row = 22
                    for i, entry in ipairs(npc.shopItems or {}) do
                        local item = DB.items[entry.id]
                        local hh = 46
                        love.graphics.setColor(1, 1, 1, (i % 2 == 0) and 0.025 or 0.045)
                        love.graphics.rectangle('fill', sx, sy + row, sw - 8, hh, 6, 6)
                        Text.draw(Theme.font.sm, item and item.name or entry.id, sx + 8, sy + row + 5, sw - 130, 'left', Theme.color.text)
                        Text.draw(Theme.font.xs, item and itemSummary(item) or '', sx + 8, sy + row + 23, sw - 130, 'left', Theme.color.muted)
                        Text.draw(Theme.font.bold, string.format('%d 💰', entry.price or 1), sx + sw - 210, sy + row + 13, 80, 'right',
                            G_.character.gold >= (entry.price or 1) and Theme.color.gold or Theme.color.red)
                        if UI.button('buy_' .. i, sx + sw - 118, sy + row + 7, 102, 32, 'Comprar', {
                            style = 'gold', font = Theme.font.sm, enabled = G_.character.gold >= (entry.price or 1),
                            onClick = function()
                                local ok, err = NPC.buy(id, entry.id)
                                if not ok then UI.toast('❌ ' .. tostring(err)) end
                            end,
                        }) then end
                        row = row + hh + 5
                    end
                    return row
                elseif npcState.tab == 'sell' then
                    if not npc.canSellToNPC then
                        Text.draw(Theme.font.sm, string.format('%s não compra itens.', npc.name), sx, sy, sw, 'left', Theme.color.muted)
                        return 30
                    end
                    Text.draw(Theme.font.xs, 'Venda itens da mochila por 50% do valor.', sx, sy, sw, 'left', Theme.color.muted)
                    row = 22
                    local shown = 0
                    for i = 1, Inventory.SLOTS do
                        local item = G_.inventory[i]
                        if item then
                            shown = shown + 1
                            local price = NPC.sellValue(item)
                            local hh = 38
                            love.graphics.setColor(1, 1, 1, (shown % 2 == 0) and 0.025 or 0.045)
                            love.graphics.rectangle('fill', sx, sy + row, sw - 8, hh, 6, 6)
                            Text.draw(Theme.font.sm, string.format('%s%s', item.name or item.id,
                                (item.quantity or 1) > 1 and (' x' .. item.quantity) or ''), sx + 8, sy + row + 9, sw - 160, 'left', Theme.color.text)
                            Text.draw(Theme.font.bold, price .. ' 💰', sx + sw - 164, sy + row + 9, 60, 'right', Theme.color.gold)
                            if UI.button('sell_' .. i, sx + sw - 96, sy + row + 4, 86, 30, 'Vender', {
                                style = 'ghost', font = Theme.font.xs,
                                onClick = function()
                                    local ok, err = NPC.sell(id, i)
                                    if not ok then UI.toast('❌ ' .. tostring(err or 'Não foi possível vender.')) end
                                end,
                            }) then end
                            row = row + hh + 4
                        end
                    end
                    if shown == 0 then
                        Text.draw(Theme.font.sm, 'Sua mochila está vazia.', sx, sy + row + 6, sw, 'left', Theme.color.dim)
                        row = row + 30
                    end
                    return row
                end
                return 40
            end)

            -- Despedida no rodapé do corpo
            Text.draw(Theme.font.xs, NPC.farewell(npc), x, y + h - 16, w, 'left', Theme.color.dim)
        end,
        buttons = {
            { text = 'Despedir', style = 'ghost' },
        },
    })
end

-- ───────────────────────────────────────────────────────── baú
local function drawContainerGrid(x, y, w, arr, label, onSlot)
    section(label, x, y, w)
    local cols, rows = 3, 6
    local gap = 6
    local sw = (w - gap * (cols - 1)) / cols
    local sh = 52
    local startY = y + 26
    for i = 1, Inventory.SLOTS do
        local col = (i - 1) % cols
        local row = math.floor((i - 1) / cols)
        local sx = x + col * (sw + gap)
        local sy = startY + row * (sh + gap)
        local item = arr[i]
        local hover = UI.hover(sx, sy, sw, sh)
        love.graphics.setColor(0, 0, 0, 0.28)
        love.graphics.rectangle('fill', sx, sy, sw, sh, 7, 7)
        if item then
            love.graphics.setColor(1, 1, 1, hover and 0.13 or 0.07)
            love.graphics.rectangle('fill', sx, sy, sw, sh, 7, 7)
            Text.draw(Theme.font.xs, Text.clean(item.name or item.id), sx + 6, sy + 4, sw - 26, 'left', Theme.color.text, 1.1)
            if (item.quantity or 1) > 1 then
                Text.draw(Theme.font.xs, 'x' .. item.quantity, sx + sw - 30, sy + sh - 15, 24, 'right', Theme.color.gold)
            end
            if item.maxDurability then
                UI.bar(sx + 6, sy + sh - 8, sw - 12, 3, (item.durability or 0) / item.maxDurability, Theme.color.green)
            end
            if hover then tooltipItem(item) end
            if hover and UI.pressed and UI.pressedButton == 1 then
                UI.consumeClick()
                onSlot(i, item)
            end
        else
            love.graphics.setColor(1, 1, 1, 0.05)
            love.graphics.rectangle('line', sx + 0.5, sy + 0.5, sw - 1, sh - 1, 7, 7)
        end
    end
    return 26 + rows * sh + (rows - 1) * gap
end

function Modals.openChest()
    local G_ = G()
    UI.openModal({
        kind = 'chest',
        title = 'Baú de Sua Casa',
        icon = '📦',
        width = 940,
        height = 620,
        body = function(x, y, w, h)
            local half = (w - 24) * 0.5
            drawContainerGrid(x, y, half, G_.chest, 'Baú', function(i)
                local free
                for j = 1, Inventory.SLOTS do
                    if not G_.inventory[j] then free = j break end
                end
                if free then
                    Inventory.move(G_.chest, i, G_.inventory, free)
                else
                    UI.toast('❌ Inventário cheio!')
                end
            end)
            drawContainerGrid(x + half + 24, y, half, G_.inventory, 'Mochila', function(i)
                local free
                for j = 1, Inventory.SLOTS do
                    if not G_.chest[j] then free = j break end
                end
                if free then
                    Inventory.move(G_.inventory, i, G_.chest, free)
                else
                    UI.toast('❌ Baú cheio!')
                end
            end)
            Text.draw(Theme.font.xs, 'Clique num item para movê-lo entre o baú e a mochila.', x, y + h - 16, w, 'center', Theme.color.dim)
        end,
        buttons = {
            { text = 'Organizar mochila', style = 'ghost', close = false, onClick = function() Inventory.organize(G_.inventory) end },
            { text = 'Organizar baú', style = 'ghost', close = false, onClick = function() Inventory.organize(G_.chest) end },
            { text = 'Fechar', style = 'default' },
        },
    })
end

-- ───────────────────────────────────────────────────────── estações
local stationState = { type = nil, jobMsg = nil }

local function drawCraftingStation(x, y, w)
    local recipes = Craft.recipesFor(stationState.type)
    local row = 0
    for i, entry in ipairs(recipes) do
        local r = entry.def
        local hh = 58
        love.graphics.setColor(1, 1, 1, (i % 2 == 0) and 0.025 or 0.045)
        love.graphics.rectangle('fill', x, y + row, w - 8, hh, 7, 7)
        local result = DB.items[r.result]
        Text.draw(Theme.font.sm, result and result.name or r.name or entry.key, x + 8, y + row + 5, w - 190, 'left', Theme.color.text)
        Text.draw(Theme.font.xs, Craft.materialsText(r), x + 8, y + row + 24, w - 190, 'left', Theme.color.muted)
        local can, missing = Craft.canCraft(r)
        if not can then
            Text.draw(Theme.font.xs, 'Falta: ' .. tostring(missing), x + 8, y + row + 41, w - 190, 'left', Theme.color.red)
        else
            Text.draw(Theme.font.xs, 'Pronto para criar', x + 8, y + row + 41, w - 190, 'left', Theme.color.green)
        end
        if UI.button('craft_' .. entry.key, x + w - 166, y + row + 12, 150, 34, 'Criar', {
            style = 'gold', font = Theme.font.sm, enabled = can,
            onClick = function()
                local ok = Craft.craft(entry.key)
                if ok then UI.toast('🔨 Item criado!') end
            end,
        }) then end
        row = row + hh + 6
    end
    if #recipes == 0 then
        Text.draw(Theme.font.sm, 'Nenhuma receita disponível nesta estação.', x, y + 8, w, 'left', Theme.color.dim)
        row = 30
    end
    return row
end

local function drawJobs(x, y, w, jobs, kind)
    local row = 0
    if #jobs == 0 then
        Text.draw(Theme.font.xs, 'Nada em andamento.', x, y, w, 'left', Theme.color.dim)
        return 22
    end
    for i, job in ipairs(jobs) do
        local total = kind == 'furnace' and (job.cookTime or 5) or (job.millTime or 3)
        local pct = U.clamp((job.elapsed or 0) / math.max(0.01, total), 0, 1)
        local name = job.resultName or (DB.items[job.result] and DB.items[job.result].name) or job.result
        Text.draw(Theme.font.sm, name, x, y + row, w - 120, 'left', Theme.color.text)
        UI.bar(x, y + row + 19, w - 130, 8, pct, pct >= 1 and Theme.color.green or Theme.color.orange)
        if pct >= 1 then
            if UI.button('collect_' .. i, x + w - 116, y + row + 2, 104, 28, 'Recolher', {
                style = 'success', font = Theme.font.xs,
                onClick = function()
                    if kind == 'furnace' then
                        local ok, err = Craft.collectSmelt(i)
                        if not ok then UI.toast('❌ ' .. tostring(err)) end
                    else
                        local ok, err = Craft.collectMill(i)
                        if not ok then UI.toast('❌ ' .. tostring(err)) end
                    end
                end,
            }) then end
        else
            Text.draw(Theme.font.xs, string.format('%d%%', math.floor(pct * 100)), x + w - 116, y + row + 8, 104, 'right', Theme.color.muted)
        end
        row = row + 44
    end
    return row
end

function Modals.openStation(stationType)
    stationState.type = stationType
    local info = Craft.stationInfo(stationType)
    UI.openModal({
        kind = 'station',
        title = info.name,
        icon = info.icon,
        width = 860,
        height = 610,
        body = function(x, y, w, h)
            local G_ = G()
            if stationType == 'alchemy' then
                Text.draw(Theme.font.md, 'Mesa de Alquimia', x, y, w, 'left', Theme.color.text)
                Text.draw(Theme.font.sm, 'As receitas de alquimia ainda não foram portadas do modo original. Por enquanto, a mesa está vazia — mas o espaço está reservado.',
                    x, y + 28, w - 20, 'left', Theme.color.muted, 1.35)
                return 80
            elseif stationType == 'anvil' then
                UI.scroll('anvil_scroll', x, y, w, h, function(sx, sy, sw)
                    Text.draw(Theme.font.xs, 'Repare ou reforce equipamentos gastos. Reforço máximo: +5.', sx, sy, sw, 'left', Theme.color.muted)
                    local row = 26
                    local list = Craft.repairableItems()
                    if #list == 0 then
                        Text.draw(Theme.font.sm, 'Nenhum equipamento reparável na mochila ou equipado.', sx, sy + row, sw, 'left', Theme.color.dim)
                        return row + 26
                    end
                    for i, entry in ipairs(list) do
                        local item = entry.item
                        local hh = 50
                        love.graphics.setColor(1, 1, 1, (i % 2 == 0) and 0.025 or 0.045)
                        love.graphics.rectangle('fill', sx, sy + row, sw - 8, hh, 7, 7)
                        Text.draw(Theme.font.sm, string.format('%s  (+%d)', item.name, item.enhance or 0), sx + 8, sy + row + 5, sw - 280, 'left', Theme.color.text)
                        Text.draw(Theme.font.xs, string.format('%s · Durabilidade %d/%d', entry.where, item.durability or 0, item.maxDurability or 0),
                            sx + 8, sy + row + 24, sw - 280, 'left', Theme.color.muted)
                        local rcost = Craft.repairCost(item)
                        local ecost = Craft.enhanceCost(item)
                        if UI.button('repair_' .. i, sx + sw - 254, sy + row + 9, 118, 30, string.format('Reparar %d💰', rcost), {
                            style = 'ghost', font = Theme.font.xs, enabled = G_.character.gold >= rcost,
                            onClick = function()
                                local ok, err = Craft.repair(item)
                                if not ok then UI.toast('❌ ' .. tostring(err)) else UI.toast('⚒️ Reparado!') end
                            end,
                        }) then end
                        if UI.button('enhance_' .. i, sx + sw - 128, sy + row + 9, 112, 30, string.format('Reforçar %d💰', ecost), {
                            style = 'gold', font = Theme.font.xs, enabled = G_.character.gold >= ecost,
                            onClick = function()
                                local ok, err = Craft.enhance(item)
                                if not ok then UI.toast('❌ ' .. tostring(err)) else UI.toast('✨ Reforçado!') end
                            end,
                        }) then end
                        row = row + hh + 6
                    end
                    return row
                end)
                return h
            elseif stationType == 'furnace' then
                UI.scroll('furnace_scroll', x, y, w, h, function(sx, sy, sw)
                    section('Assar / Fundir', sx, sy, sw)
                    local row = 24
                    for i, entry in ipairs(Craft.furnaceRecipes()) do
                        local r = entry.def
                        local input = DB.items[r.input]
                        local hh = 50
                        love.graphics.setColor(1, 1, 1, (i % 2 == 0) and 0.025 or 0.045)
                        love.graphics.rectangle('fill', sx, sy + row, sw - 8, hh, 7, 7)
                        Text.draw(Theme.font.sm, r.resultName or (DB.items[r.result] and DB.items[r.result].name) or r.result,
                            sx + 8, sy + row + 5, sw - 250, 'left', Theme.color.text)
                        Text.draw(Theme.font.xs, string.format('%s · %ds · 1 combustível', input and input.name or r.input, r.cookTime or 5),
                            sx + 8, sy + row + 24, sw - 250, 'left', Theme.color.muted)
                        if UI.button('smelt_' .. entry.key, sx + sw - 160, sy + row + 9, 144, 30, 'Acender forno', {
                            style = 'warning', font = Theme.font.xs,
                            enabled = Inventory.count(G_.inventory, r.input) > 0,
                            onClick = function()
                                local ok, err = Craft.startSmelt(entry.key)
                                if not ok then UI.toast('❌ ' .. tostring(err)) else UI.toast('🔥 Forno aceso!') end
                            end,
                        }) then end
                        row = row + hh + 5
                    end
                    row = row + 12
                    section('No fogo', sx, sy + row, sw)
                    row = row + 26
                    row = row + drawJobs(sx, sy + row, sw, G_.furnaceJobs or {}, 'furnace')
                    return row
                end)
                return h
            elseif stationType == 'mill' then
                UI.scroll('mill_scroll', x, y, w, h, function(sx, sy, sw)
                    section('Moer', sx, sy, sw)
                    local row = 24
                    for i, entry in ipairs(Craft.recipesFor('mill')) do
                        local r = entry.def
                        local hh = 50
                        love.graphics.setColor(1, 1, 1, (i % 2 == 0) and 0.025 or 0.045)
                        love.graphics.rectangle('fill', sx, sy + row, sw - 8, hh, 7, 7)
                        Text.draw(Theme.font.sm, r.name or entry.key, sx + 8, sy + row + 5, sw - 250, 'left', Theme.color.text)
                        Text.draw(Theme.font.xs, Craft.materialsText(r), sx + 8, sy + row + 24, sw - 250, 'left', Theme.color.muted)
                        local can = Craft.canCraft(r)
                        if UI.button('mill_' .. entry.key, sx + sw - 160, sy + row + 9, 144, 30, 'Moer', {
                            style = 'gold', font = Theme.font.xs, enabled = can,
                            onClick = function()
                                local ok, err = Craft.startMill(entry.key)
                                if not ok then UI.toast('❌ ' .. tostring(err)) else UI.toast('⚙️ Moinho girando!') end
                            end,
                        }) then end
                        row = row + hh + 5
                    end
                    row = row + 12
                    section('Moagem em andamento', sx, sy + row, sw)
                    row = row + 26
                    row = row + drawJobs(sx, sy + row, sw, G_.millJobs or {}, 'mill')
                    return row
                end)
                return h
            elseif stationType == 'sleeping_bag' then
                Text.draw(Theme.font.md, 'Saco de Dormir', x, y, w, 'left', Theme.color.text)
                Text.draw(Theme.font.sm, Time.sleepMessage(), x, y + 28, w - 20, 'left', Theme.color.muted, 1.35)
                if UI.button('sleep_bag', x, y + 80, 220, 40, 'Deitar para dormir', {
                    style = 'gold',
                    onClick = function()
                        UI.closeModal()
                        Modals.openSleep()
                    end,
                }) then end
                return 140
            end

            -- bancada / tear
            local cy = y
            if stationType == 'crafting_table' or stationType == 'loom' then
                UI.scroll('station_' .. stationType, x, y, w, h, function(sx, sy, sw)
                    return drawCraftingStation(sx, sy, sw)
                end)
                return h
            end
            Text.draw(Theme.font.sm, 'Estação sem interface própria.', x, y, w, 'left', Theme.color.dim)
            return 30
        end,
        buttons = {
            { text = 'Fechar', style = 'ghost' },
        },
    })
end

-- ───────────────────────────────────────────────────────── quadro de missões
local function drawQuestOffer(x, y, w, id, closeOnAccept)
    local quest = DB.quests[id]
    local can, why = Quests.available(id)
    local hh = 92
    love.graphics.setColor(1, 1, 1, 0.045)
    love.graphics.rectangle('fill', x, y, w, hh, 8, 8)
    Text.draw(Theme.font.boldMd, quest.name, x + 10, y + 7, w - 220, 'left', Theme.color.text)
    Text.draw(Theme.font.xs, quest.description or '', x + 10, y + 29, w - 220, 'left', Theme.color.muted, 1.2)
    Text.draw(Theme.font.xs, 'Recompensa: ' .. questRewardText(quest), x + 10, y + 66, w - 220, 'left', Theme.color.gold)
    if not can then
        Text.draw(Theme.font.xs, why, x + 10, y + 78, w - 220, 'left', Theme.color.red)
    end
    if UI.button('accept_' .. id, x + w - 190, y + 26, 176, 36, 'Aceitar missão', {
        style = 'gold', font = Theme.font.sm, enabled = can,
        onClick = function()
            local ok = Quests.accept(id)
            if ok then
                UI.toast('📜 Missão aceita: ' .. quest.name)
                if closeOnAccept then UI.closeModal() end
            end
        end,
    }) then end
    return hh
end

function Modals.openQuestBoard()
    UI.openModal({
        kind = 'questboard',
        title = 'Quadro de Missões',
        icon = '📜',
        width = 820,
        height = 610,
        body = function(x, y, w, h)
            UI.scroll('questboard_scroll', x, y, w, h, function(sx, sy, sw)
                local row = 0
                local active = Quests.active()
                if active then
                    section('Missão ativa', sx, sy, sw)
                    row = row + 24
                    local g = G()
                    Text.draw(Theme.font.boldMd, active.name, sx, sy + row, sw, 'left', Theme.color.gold)
                    row = row + 24
                    Text.draw(Theme.font.sm, Q_stageLine(active), sx, sy + row, sw, 'left', Theme.color.text, 1.3)
                    row = row + 44
                end
                section('Missões disponíveis', sx, sy + row, sw)
                row = row + 26
                local shown = 0
                local ids = {}
                for id in pairs(DB.quests) do ids[#ids + 1] = id end
                table.sort(ids)
                for _, id in ipairs(ids) do
                    if not Quests.isCompleted(id) or DB.quests[id].repeatable then
                        shown = shown + 1
                        row = row + drawQuestOffer(sx, sy + row, sw, id, false) + 8
                    end
                end
                if shown == 0 then
                    Text.draw(Theme.font.sm, 'Não há novas missões no momento. Volte mais tarde.', sx, sy + row, sw, 'left', Theme.color.dim)
                    row = row + 28
                end
                return row
            end)
            return h
        end,
        buttons = {
            { text = 'Diário de missões', style = 'ghost', close = false, onClick = function() UI.closeModal() Modals.openJournal('quests') end },
            { text = 'Fechar', style = 'default' },
        },
    })
end

function Q_stageLine(quest)
    local stage, idx = Quests.currentStage()
    if not stage then return '' end
    local p, need = Quests.progress()
    return string.format('Estágio %d/%d — %s (%d/%d)', idx, #quest.stages, stage.name, p, need)
end

-- ───────────────────────────────────────────────────────── diário
local journalTab = 'quests'

function Modals.openJournal(tab)
    journalTab = tab or 'quests'
    UI.openModal({
        kind = 'journal',
        title = 'Diário de Jornada',
        icon = '📔',
        width = 940,
        height = 640,
        body = function(x, y, w, h)
            local tabs = {
                { id = 'quests', label = 'Missões' },
                { id = 'bestiary', label = 'Bestiário' },
                { id = 'achievements', label = 'Conquistas' },
                { id = 'stats', label = 'Estatísticas' },
            }
            local tx = x
            for _, t in ipairs(tabs) do
                if UI.button('journal_tab_' .. t.id, tx, y, 150, 32, t.label, {
                    style = journalTab == t.id and 'default' or 'ghost', font = Theme.font.sm,
                    onClick = function() journalTab = t.id end,
                }) then end
                tx = tx + 158
            end
            local cy = y + 44
            local ch = h - 44
            local G_ = G()
            if journalTab == 'quests' then
                UI.scroll('journal_quests', x, cy, w, ch, function(sx, sy, sw)
                    local row = 0
                    local active = Quests.active()
                    if active then
                        section('Missão ativa', sx, sy, sw)
                        row = row + 22
                        Text.draw(Theme.font.boldMd, active.name, sx, sy + row, sw - 120, 'left', Theme.color.gold)
                        row = row + 24
                        Text.draw(Theme.font.sm, active.description or '', sx, sy + row, sw - 20, 'left', Theme.color.muted, 1.3)
                        row = row + math.max(24, Text.height(Theme.font.sm, active.description or '', sw - 20, 1.3))
                        row = row + 8
                        local idx = G_.activeQuest.currentStage or 0
                        local prog = G_.activeQuest.stageProgress or {}
                        local current = idx + 1
                        for i, stage in ipairs(active.stages or {}) do
                            local done = i <= idx
                            local isCurrent = i == current
                            local p = (isCurrent and (prog[idx] or 0)) or 0
                            local text = stageProgressText(stage, p, i, current)
                            local col = done and Theme.color.green or (isCurrent and Theme.color.gold or Theme.color.dim)
                            Text.draw(Theme.font.sm, text, sx + 8, sy + row, sw - 180, 'left', col)
                            if isCurrent then
                                local need = stage.required or 1
                                UI.bar(sx + sw - 160, sy + row + 4, 140, 8, p / math.max(1, need), Theme.color.gold)
                            end
                            row = row + 26
                        end
                        row = row + 6
                        Text.draw(Theme.font.xs, 'Recompensa: ' .. questRewardText(active), sx, sy + row, sw - 140, 'left', Theme.color.gold)
                        if UI.button('abandon_quest', sx + sw - 132, sy + row - 8, 118, 28, 'Abandonar', {
                            style = 'danger', font = Theme.font.xs,
                            onClick = function()
                                if Quests.abandon() then UI.toast('Missão abandonada.') end
                            end,
                        }) then end
                        row = row + 34
                    else
                        Text.draw(Theme.font.sm, 'Você não tem nenhuma missão ativa.', sx, sy, sw, 'left', Theme.color.dim)
                        row = 30
                    end
                    row = row + 8
                    section('Disponíveis', sx, sy + row, sw)
                    row = row + 26
                    local any = false
                    local ids = {}
                    for id in pairs(DB.quests) do ids[#ids + 1] = id end
                    table.sort(ids)
                    for _, id in ipairs(ids) do
                        if not Quests.isCompleted(id) then
                            any = true
                            row = row + drawQuestOffer(sx, sy + row, sw, id, false) + 8
                        end
                    end
                    if not any then
                        Text.draw(Theme.font.xs, 'Nenhuma oferta no momento.', sx, sy + row, sw, 'left', Theme.color.dim)
                        row = row + 24
                    end
                    section('Concluídas', sx, sy + row, sw)
                    row = row + 24
                    if #G_.completedQuests == 0 then
                        Text.draw(Theme.font.xs, 'Nenhuma missão concluída ainda.', sx, sy + row, sw, 'left', Theme.color.dim)
                        row = row + 24
                    else
                        for _, id in ipairs(G_.completedQuests) do
                            local q = DB.quests[id]
                            Text.draw(Theme.font.sm, '[x] ' .. (q and q.name or id), sx + 8, sy + row, sw, 'left', Theme.color.green)
                            row = row + 22
                        end
                    end
                    return row
                end)
            elseif journalTab == 'bestiary' then
                UI.scroll('journal_bestiary', x, cy, w, ch, function(sx, sy, sw)
                    local ids = {}
                    for id in pairs(DB.creatures) do ids[#ids + 1] = id end
                    table.sort(ids)
                    local row = 0
                    local shown = 0
                    for _, id in ipairs(ids) do
                        local kills = (G_.bestiary and G_.bestiary[id]) or (G_.stats.killsByType and G_.stats.killsByType[id]) or 0
                        if kills > 0 then
                            shown = shown + 1
                            local c = DB.creatures[id]
                            love.graphics.setColor(1, 1, 1, 0.04)
                            love.graphics.rectangle('fill', sx, sy + row, sw - 8, 42, 6, 6)
                            Text.draw(Theme.font.sm, c.name or id, sx + 8, sy + row + 5, sw - 260, 'left', Theme.color.text)
                            Text.draw(Theme.font.xs, string.format('Vida %d · ATQ %d · DEF %d · EXP %d', c.life or 0, c.attack or 0, c.defense or 0, c.exp or 0),
                                sx + 8, sy + row + 23, sw - 260, 'left', Theme.color.muted)
                            Text.draw(Theme.font.bold, 'Abates: ' .. kills, sx + sw - 250, sy + row + 12, 230, 'right', Theme.color.gold)
                            row = row + 46
                        end
                    end
                    if shown == 0 then
                        Text.draw(Theme.font.sm, 'Nenhuma criatura registrada. Explore e lute para preencher o bestiário.', sx, sy, sw, 'left', Theme.color.dim)
                        row = 30
                    end
                    return row
                end)
            elseif journalTab == 'achievements' then
                UI.scroll('journal_achievements', x, cy, w, ch, function(sx, sy, sw)
                    local n, total = Achievements.count()
                    Text.draw(Theme.font.sm, string.format('Desbloqueadas: %d/%d', n, total), sx, sy, sw, 'left', Theme.color.gold)
                    local row = 26
                    for _, a in ipairs(Achievements.list()) do
                        love.graphics.setColor(1, 1, 1, a.unlocked and 0.06 or 0.025)
                        love.graphics.rectangle('fill', sx, sy + row, sw - 8, 44, 6, 6)
                        Text.draw(Theme.font.sm, (a.unlocked and '[x] ' or '[ ] ') .. (a.name or a.id), sx + 8, sy + row + 5, sw - 120, 'left',
                            a.unlocked and Theme.color.gold or Theme.color.muted)
                        Text.draw(Theme.font.xs, a.desc or '', sx + 8, sy + row + 24, sw - 120, 'left', Theme.color.muted)
                        Text.draw(Theme.font.xs, a.unlocked and 'Desbloqueada' or 'Bloqueada', sx + sw - 110, sy + row + 15, 90, 'right',
                            a.unlocked and Theme.color.green or Theme.color.dim)
                        row = row + 48
                    end
                    return row
                end)
            else
                UI.scroll('journal_stats', x, cy, w, ch, function(sx, sy, sw)
                    local row = 0
                    section('Personagem', sx, sy, sw)
                    row = row + 26
                    local c = G_.character
                    local race = DB.races[c.race]
                    valueRow('Nome', c.name, sx, sy + row, sw, Theme.color.text) row = row + 22
                    valueRow('Raça', race and race.name or c.race, sx, sy + row, sw, Theme.color.text) row = row + 22
                    valueRow('Nível', c.level, sx, sy + row, sw, Theme.color.gold) row = row + 22
                    valueRow('Vida', string.format('%d/%d', c.life, c.maxLife), sx, sy + row, sw, Theme.color.hp) row = row + 22
                    valueRow('Mana', string.format('%d/%d', c.mana, c.maxMana), sx, sy + row, sw, Theme.color.mana) row = row + 22
                    valueRow('Ouro', c.gold, sx, sy + row, sw, Theme.color.gold) row = row + 30
                    section('Jornada', sx, sy + row, sw)
                    row = row + 26
                    local function stat(label, value)
                        valueRow(label, value, sx, sy + row, sw, Theme.color.text)
                        row = row + 22
                    end
                    stat('Abates', G_.stats.kills or 0)
                    stat('Missões concluídas', G_.stats.questsCompleted or 0)
                    stat('Itens criados', G_.stats.crafted or 0)
                    stat('Refeições', G_.stats.foods or 0)
                    stat('Livros lidos', G_.stats.books or 0)
                    stat('Compras', G_.stats.purchases or 0)
                    stat('Locais descobertos', (function()
                        local n = 0
                        for _ in pairs(G_.stats.locations or {}) do n = n + 1 end
                        return n
                    end)())
                    stat('NPCs conhecidos', (function()
                        local n = 0
                        for _ in pairs(G_.stats.npcs or {}) do n = n + 1 end
                        return n
                    end)())
                    stat('Tempo de jogo', string.format('%d min', math.floor((G_.playSeconds or 0) / 60)))
                    return row
                end)
            end
            return h
        end,
        buttons = {
            { text = 'Fechar', style = 'default' },
        },
    })
end

-- ───────────────────────────────────────────────────────── mina
function Modals.openMine()
    Actions.initMine()
    UI.openModal({
        kind = 'mine',
        title = 'Mina do Sul',
        icon = '⛏️',
        width = 800,
        height = 580,
        closable = false,
        body = function(x, y, w, h)
            local G_ = G()
            local mine = Actions.initMine()
            if MG.active then
                return Modals.drawMinigameBody(x, y, w, h)
            end
            Text.draw(Theme.font.sm, string.format('Profundidade: %d/3', mine.depth or 1), x, y, w, 'left', Theme.color.text)
            Text.draw(Theme.font.sm, 'Tochas / combustível', x, y + 26, 200, 'left', Theme.color.muted)
            UI.bar(x + 180, y + 28, w - 260, 12, U.clamp((mine.fuel or 0) / 300, 0, 1),
                (mine.fuel or 0) > 40 and Theme.color.orange or Theme.color.red, { label = tostring(math.floor(mine.fuel or 0)) })
            Text.draw(Theme.font.sm, string.format('Minérios extraídos: %d', mine.found or 0), x, y + 52, w, 'left', Theme.color.muted)
            local pick = Inventory.mainhandTool('pickaxe')
            Text.draw(Theme.font.xs, pick and ('Picareta: ' .. pick.name .. ' (dur. ' .. (pick.durability or 0) .. ')') or 'Nenhuma picareta equipada!',
                x, y + 74, w, 'left', pick and Theme.color.green or Theme.color.red)

            local row = 112
            local bw = (w - 16) * 0.5
            if UI.button('mine_prospect', x, y + row, bw, 46, 'Prospectar veio', {
                style = 'gold', sub = 'Minigame de picareta', enabled = pick ~= nil,
                onClick = function() Actions.mineProspect() end,
            }) then end
            if UI.button('mine_torch', x + bw + 16, y + row, bw, 46, 'Acender tocha', {
                style = 'warning', sub = 'Consome 1 tocha',
                onClick = function() Actions.mineLightTorch() end,
            }) then end
            row = row + 56
            if UI.button('mine_descend', x, y + row, bw, 44, 'Descer galeria', {
                style = 'default', enabled = (mine.depth or 1) < 3,
                onClick = function() Actions.mineDescend() end,
            }) then end
            if UI.button('mine_ascend', x + bw + 16, y + row, bw, 44, 'Subir galeria', {
                style = 'ghost', enabled = (mine.depth or 1) > 1,
                onClick = function() Actions.mineAscend() end,
            }) then end
            row = row + 56
            Text.draw(Theme.font.xs, 'Quanto mais fundo, melhores os minérios — e maiores os perigos. A escuridão machuca.',
                x, y + row, w, 'left', Theme.color.dim, 1.3)
            if UI.button('mine_leave', x, y + h - 42, w, 38, 'Sair da mina', {
                style = 'danger',
                onClick = function() UI.closeModal() end,
            }) then end
            return h
        end,
        buttons = {},
    })
end

-- corpo compartilhado do minigame (mina e coleta)
function Modals.drawMinigameBody(x, y, w, h)
    local a = MG.active
    if not a then
        return 40
    end
    Text.draw(Theme.font.boldMd, a.label or 'Coleta', x, y, w, 'left', Theme.color.gold)
    Text.draw(Theme.font.sm, 'Acerte a zona iluminada para progredir.', x, y + 26, w, 'left', Theme.color.muted)
    local barX, barY, barW, barH = x + 10, y + 70, w - 20, 34
    love.graphics.setColor(0, 0, 0, 0.45)
    love.graphics.rectangle('fill', barX, barY, barW, barH, 8, 8)
    -- zona
    local zx = barX + (a.zoneC - a.zoneW * 0.5) * barW
    love.graphics.setColor(Theme.color.green[1], Theme.color.green[2], Theme.color.green[3], 0.55)
    love.graphics.rectangle('fill', zx, barY + 2, a.zoneW * barW, barH - 4, 6, 6)
    -- marcador
    local mx = barX + a.pos * barW
    love.graphics.setColor(1, 1, 1, 0.95)
    love.graphics.rectangle('fill', mx - 2, barY - 5, 4, barH + 10, 2, 2)
    if a.flash and a.flash > 0 then
        love.graphics.setColor(1, 1, 1, a.flash * 0.6)
        love.graphics.rectangle('line', barX + 0.5, barY + 0.5, barW - 1, barH - 1, 8, 8)
    end

    local pips = {}
    for i = 1, a.needed do pips[i] = i <= a.hits end
    local px = x + w * 0.5 - (a.needed * 26) * 0.5
    for i, on in ipairs(pips) do
        love.graphics.setColor(on and Theme.color.gold[1] or 1, on and Theme.color.gold[2] or 1, on and Theme.color.gold[3] or 1, on and 1 or 0.15)
        love.graphics.circle('fill', px + i * 26 - 13, y + 130, on and 7 or 5)
    end

    if UI.button('mg_strike', x + w * 0.5 - 140, y + 158, 280, 46, a.kind == 'tree' and 'Golpear!' or 'Picar!', {
        style = 'gold', font = Theme.font.boldMd,
        onClick = function()
            MG.strike()
        end,
    }) then end
    if UI.button('mg_cancel', x + w * 0.5 - 90, y + 216, 180, 32, 'Desistir', {
        style = 'ghost', font = Theme.font.sm,
        onClick = function() MG.cancel() end,
    }) then end
    Text.draw(Theme.font.xs, string.format('Golpes certeiros: %d/%d', a.hits, a.needed), x, y + 262, w, 'center', Theme.color.muted)
    return 300
end

function Modals.openMinigame()
    UI.openModal({
        kind = 'minigame',
        title = 'Coleta',
        icon = '🪓',
        width = 640,
        height = 420,
        closable = false,
        body = function(x, y, w, h)
            return Modals.drawMinigameBody(x, y, w, h)
        end,
        buttons = {},
    })
end

-- ───────────────────────────────────────────────────────── sono
function Modals.openSleep()
    local ok, msg = Time.startSleep()
    if not ok then
        UI.toast('⚠️ ' .. tostring(msg))
        return
    end
    UI.openModal({
        kind = 'sleep',
        title = 'Dormindo',
        icon = '🌙',
        width = 560,
        height = 360,
        closable = false,
        body = function(x, y, w, h)
            local G_ = G()
            local total = Time.SLEEP_SECONDS
            local left = G_.sleepTimer or 0
            Text.draw(Theme.font.lg, 'Zzz...', x, y + 10, w, 'center', Theme.color.purple)
            Text.draw(Theme.font.sm, Time.sleepMessage(), x + 20, y + 52, w - 40, 'center', Theme.color.muted, 1.3)
            local pct = 1 - U.clamp(left / total, 0, 1)
            UI.bar(x + 40, y + 120, w - 80, 16, pct, Theme.color.purple)
            Text.draw(Theme.font.md, string.format('%d s', math.ceil(left)), x, y + 146, w, 'center', Theme.color.text)
            if UI.button('wake_up', x + w * 0.5 - 110, y + 190, 220, 40, 'Acordar agora', {
                style = 'ghost',
                onClick = function() Time.wakeUp() end,
            }) then end
            return 240
        end,
    })
end

-- ───────────────────────────────────────────────────────── livro
local bookState = { index = nil }

function Modals.openBook(index)
    local item = G().inventory[index]
    if not item then return end
    bookState.index = index
    G().stats.books = (G().stats.books or 0) + 1
    Achievements.check()
    local editable = item.id == 'book' and not item.libraryBook
    local titleId = 'book_title_' .. index
    local contentId = 'book_content_' .. index
    if editable then
        UI.input[titleId] = item.title or ''
        UI.input[contentId] = item.content or ''
    end
    UI.openModal({
        kind = 'book',
        title = item.libraryBook and 'Livro da Biblioteca' or 'Livro',
        icon = '📖',
        width = 760,
        height = 580,
        body = function(x, y, w, h)
            local it = G().inventory[bookState.index]
            if not it then
                Text.draw(Theme.font.sm, 'O livro não está mais na mochila.', x, y, w, 'left', Theme.color.dim)
                return 30
            end
            if it.libraryBook then
                Text.draw(Theme.font.boldLg, it.title or 'Sem título', x, y, w, 'left', Theme.color.gold)
                UI.divider(x, y + 30, w, 0.12)
                Text.draw(Theme.font.md, it.content or '(página em branco)', x, y + 44, w - 10, 'left', Theme.color.text, 1.5)
                Text.draw(Theme.font.xs, 'Livro emprestado da Biblioteca Real — devolva para ganhar reputação.', x, y + h - 18, w, 'left', Theme.color.dim)
                return h
            end
            if editable then
                Text.draw(Theme.font.xs, 'Título', x, y, w, 'left', Theme.color.muted)
                local title = UI.textInput(titleId, x, y + 16, w, 38, it.title or '', { placeholder = 'Título do livro...', max = 60 })
                Text.draw(Theme.font.xs, 'Conteúdo', x, y + 66, w, 'left', Theme.color.muted)
                local content = UI.textInput(contentId, x, y + 82, w, 38, it.content or '', { placeholder = 'Escreva uma linha...', max = 240 })
                if UI.button('book_save', x, y + 136, 200, 36, 'Salvar página', {
                    style = 'gold',
                    onClick = function()
                        it.title = U.trim(title)
                        it.content = U.trim(content)
                        State.addLog(string.format('📖 Você escreveu em "%s".', it.title ~= '' and it.title or 'livro sem título'))
                        UI.toast('📖 Livro salvo.')
                    end,
                }) then end
                Text.draw(Theme.font.sm, it.content or '', x, y + 190, w - 10, 'left', Theme.color.text, 1.4)
                return h
            end
            Text.draw(Theme.font.boldLg, it.name or 'Livro', x, y, w, 'left', Theme.color.gold)
            Text.draw(Theme.font.md, it.description or '', x, y + 36, w - 10, 'left', Theme.color.text, 1.4)
            return h
        end,
        buttons = {
            { text = 'Fechar', style = 'default' },
        },
    })
end

-- ───────────────────────────────────────────────────────── perfil
function Modals.openProfile()
    UI.openModal({
        kind = 'profile',
        title = 'Perfil do Aventureiro',
        icon = '🧝',
        width = 760,
        height = 560,
        body = function(x, y, w, h)
            local G_ = G()
            local c = G_.character
            local race = DB.races[c.race]
            love.graphics.setColor(Theme.color.purple[1], Theme.color.purple[2], Theme.color.purple[3], 0.28)
            love.graphics.circle('fill', x + 46, y + 46, 40)
            love.graphics.circle('line', x + 46, y + 46, 40)
            Text.draw(Theme.font.title, (c.name or '?'):sub(1, 1), x + 14, y + 18, 64, 'center', Theme.color.gold)
            Text.draw(Theme.font.boldLg, c.name, x + 98, y + 14, w - 110, 'left', Theme.color.text)
            Text.draw(Theme.font.sm, string.format('%s · %s · %d anos · Nível %d', race and race.name or c.race,
                c.gender or '', c.age or 0, c.level or 1), x + 98, y + 38, w - 110, 'left', Theme.color.muted)
            Text.draw(Theme.font.sm, c.bio or '', x + 98, y + 58, w - 120, 'left', Theme.color.text, 1.3)
            local row = 116
            valueRow('Vida', string.format('%d/%d', c.life, c.maxLife), x, y + row, w, Theme.color.hp) row = row + 24
            valueRow('Mana', string.format('%d/%d', c.mana, c.maxMana), x, y + row, w, Theme.color.mana) row = row + 24
            valueRow('Ataque', Inventory.totalAttack(), x, y + row, w, Theme.color.orange) row = row + 24
            valueRow('Defesa', Inventory.totalDefense(), x, y + row, w, Theme.color.blue) row = row + 24
            valueRow('Ouro', c.gold, x, y + row, w, Theme.color.gold) row = row + 24
            valueRow('Experiência', string.format('%d/%d', c.exp or 0, State.expNeeded()), x, y + row, w, Theme.color.green) row = row + 30
            Text.draw(Theme.font.xs, string.format('Local atual: %s', (DB.locations[G_.location] and DB.locations[G_.location].name) or G_.location),
                x, y + row, w, 'left', Theme.color.muted)
            row = row + 20
            Text.draw(Theme.font.xs, string.format('Data: %s · Clima: %s', State.shortDate(), State.weather().name or ''),
                x, y + row, w, 'left', Theme.color.muted)
            return row + 30
        end,
        buttons = {
            { text = 'Fechar', style = 'default' },
        },
    })
end

-- ───────────────────────────────────────────────────────── menu
function Modals.openMenu()
    UI.openModal({
        kind = 'menu',
        title = 'Menu',
        icon = '☰',
        width = 560,
        height = 560,
        body = function(x, y, w, h)
            if UI.button('menu_save', x, y, w, 44, 'Salvar jogo', {
                style = 'gold', sub = 'Grava o progresso localmente',
                onClick = function()
                    if State.save() then UI.toast('💾 Jogo salvo.') else UI.toast('❌ Falha ao salvar.') end
                end,
            }) then end
            if UI.button('menu_fullscreen', x, y + 54, w, 44, 'Alternar tela cheia', {
                style = 'ghost', sub = 'F11',
                onClick = function()
                    love.window.setFullscreen(not love.window.getFullscreen(), 'desktop')
                end,
            }) then end
            if UI.button('menu_title', x, y + 108, w, 44, 'Voltar ao título', {
                style = 'ghost', sub = 'O jogo é salvo antes de sair',
                onClick = function()
                    State.save(true)
                    UI.closeModal()
                    Manager.set('title')
                end,
            }) then end
            if UI.button('menu_quit', x, y + 162, w, 44, 'Sair do jogo', {
                style = 'danger', sub = 'Salva e fecha',
                onClick = function()
                    State.onQuit()
                    love.event.quit()
                end,
            }) then end

            UI.divider(x, y + 224, w, 0.1)
            Text.draw(Theme.font.bold, 'Controles', x, y + 236, w, 'left', Theme.color.gold)
            local lines = {
                'Mouse: clicar nos botões, itens e mapa',
                'Arrastar item: mover ou equipar',
                'WASD / setas: rolar a lista de ações',
                'M: mapa completo · J: diário · Esc: fechar modal',
                'F11: tela cheia',
            }
            local row = 260
            for _, line in ipairs(lines) do
                Text.draw(Theme.font.sm, '• ' .. line, x, y + row, w, 'left', Theme.color.muted, 1.25)
                row = row + 22
            end
            return row
        end,
        buttons = {
            { text = 'Fechar', style = 'default' },
        },
    })
end

-- ───────────────────────────────────────────────────────── final
function Modals.openEnding()
    UI.openModal({
        kind = 'ending',
        title = 'O Crepúsculo de Duas Coroas',
        icon = '👑',
        width = 780,
        height = 560,
        closable = false,
        body = function(x, y, w, h)
            local G_ = G()
            local text = 'O Mago Negro cai. A sombra que pairava sobre o Reino da Aurora se desfaz como névoa ao amanhecer.\n\n' ..
                'Diante de você estão duas coroas: a antiga, dourada, dos reis da aurora; e a de obsidiana, que pulsa com o crepúsculo eterno.\n\n' ..
                'O reino espera. Qual destino você escolhe?'
            Text.draw(Theme.font.md, text, x, y, w - 10, 'left', Theme.color.text, 1.45)
            local by = y + h - 150
            if UI.button('ending_aurora', x, by, (w - 16) * 0.5, 54, 'Restaurar a Aurora', {
                style = 'gold', sub = 'O reino volta a florescer sob o sol',
                onClick = function()
                    G_.flags.ending = 'aurora'
                    G_.flags.endingPending = false
                    G_.flags.endingShown = true
                    State.addLog('🌅 Você escolhe a coroa dourada. A Aurora retorna ao reino!')
                    State.addLog('🏆 FINAL: A Aurora Restaurada. Obrigado por jogar!')
                    State.save()
                    UI.closeModal()
                end,
            }) then end
            if UI.button('ending_twilight', x + (w - 16) * 0.5 + 16, by, (w - 16) * 0.5, 54, 'Assumir o Crepúsculo', {
                style = 'default', sub = 'Um novo reino sob a lua eterna',
                onClick = function()
                    G_.flags.ending = 'twilight'
                    G_.flags.endingPending = false
                    G_.flags.endingShown = true
                    State.addLog('🌑 Você escolhe a coroa de obsidiana. O Crepúsculo governa o reino!')
                    State.addLog('🏆 FINAL: O Reino do Crepúsculo. Obrigado por jogar!')
                    State.save()
                    UI.closeModal()
                end,
            }) then end
            return h
        end,
        buttons = {},
    })
end

-- ───────────────────────────────────────────────────────── morte
function Modals.openDeath()
    UI.openModal({
        kind = 'death',
        title = 'Você morreu',
        icon = '💀',
        width = 640,
        height = 440,
        closable = false,
        body = function(x, y, w, h)
            local G_ = G()
            Text.draw(Theme.font.lg, 'A jornada termina aqui...', x, y, w, 'center', Theme.color.red)
            Text.draw(Theme.font.sm, 'Seu save foi apagado. Comece uma nova história.', x, y + 36, w, 'center', Theme.color.muted)
            local row = 80
            for i = 1, math.min(5, #G_.combatLog) do
                Text.draw(Theme.font.xs, G_.combatLog[i], x, y + row, w, 'center', i == 1 and Theme.color.text or Theme.color.dim)
                row = row + 20
            end
            if UI.button('death_title', x + 40, y + h - 60, w - 80, 44, 'Voltar ao título', {
                style = 'danger',
                onClick = function()
                    UI.closeModal()
                    Manager.set('title')
                end,
            }) then end
            return h
        end,
        buttons = {},
    })
end

-- ───────────────────────────────────────────────────────── roteador
function Modals.handle(req)
    if not req then return end
    if req.type == 'npc' then
        Modals.openNpc(req.id)
    elseif req.type == 'chest' then
        Modals.openChest()
    elseif req.type == 'station' then
        Modals.openStation(req.station)
    elseif req.type == 'questboard' then
        Modals.openQuestBoard()
    elseif req.type == 'journal' then
        Modals.openJournal(req.tab)
    elseif req.type == 'mine' then
        Modals.openMine()
    elseif req.type == 'sleep' then
        Modals.openSleep()
    elseif req.type == 'book' then
        Modals.openBook(req.index)
    elseif req.type == 'ending' then
        Modals.openEnding()
    elseif req.type == 'map' then
        Map.openFull()
    elseif req.type == 'minigame' then
        Modals.openMinigame()
    end
end

return Modals
