-- Tela principal do jogo: HUD, inventário, equipamento, local, mapa,
-- combate, registro e integração com os modais.
local UI = require('src.core.ui')
local Theme = require('src.core.theme')
local Text = require('src.core.text')
local DB = require('src.data.init')
local State = require('src.game.state')
local Inventory = require('src.game.inventory')
local Survival = require('src.game.survival')
local Time = require('src.game.time')
local Craft = require('src.game.craft')
local Combat = require('src.game.combat')
local Quests = require('src.game.quests')
local Achievements = require('src.game.achievements')
local Actions = require('src.game.actions')
local MG = require('src.game.minigame')
local Modals = require('src.screens.modals')
local Map = require('src.screens.map')
local Manager = require('src.screens.manager')
local U = require('src.core.util')

local Game = {}

local drag = nil
local targets = {}
local autosave = 0
local endingOpened = false

local L = {
    top = { x = 12, y = 10, w = 1256, h = 64 },
    surv = { x = 12, y = 80, w = 1256, h = 22 },
    inv = { x = 12, y = 110, w = 330, h = 454 },
    mid = { x = 352, y = 110, w = 616, h = 454 },
    right = { x = 978, y = 110, w = 290, h = 454 },
    log = { x = 12, y = 572, w = 1256, h = 136 },
}

local EQUIP_LABELS = {
    helmet = { 'H', 'Capacete' },
    chest = { 'P', 'Peitoral' },
    pants = { 'C', 'Calças' },
    boots = { 'B', 'Botas' },
    mainhand = { 'M', 'Mão principal' },
    offhand = { 'O', 'Mão secundária' },
}
local EQUIP_ORDER = { 'helmet', 'chest', 'pants', 'boots', 'mainhand', 'offhand' }

local TYPE_COLOR = {
    weapon = Theme.color.orange,
    armor = Theme.color.blue,
    shield = Theme.color.cyan,
    tool = Theme.color.gold,
    food = Theme.color.green,
    drink = Theme.color.cyan,
    material = Theme.color.muted,
    book = Theme.color.purple,
    station = Theme.color.orange,
    container = Theme.color.gold,
    ammo = Theme.color.orange,
}

local function G() return State.G end

local function itemLabel(item)
    if not item then return '' end
    if item.type == 'book' and item.title and item.title ~= '' then return item.title end
    return item.name or item.id or '?'
end

local function itemTooltip(item)
    if not item then return end
    local lines = { itemLabel(item) }
    local bits = {}
    if (item.attack or 0) > 0 then bits[#bits + 1] = 'ATQ +' .. item.attack end
    if (item.defense or 0) > 0 then bits[#bits + 1] = 'DEF +' .. item.defense end
    if item.heal and item.heal > 0 then bits[#bits + 1] = 'Vida +' .. item.heal end
    if item.mana and item.mana > 0 then bits[#bits + 1] = 'Mana +' .. item.mana end
    if item.maxDurability then bits[#bits + 1] = string.format('Dur %d/%d', item.durability or 0, item.maxDurability) end
    if (item.quantity or 1) > 1 then bits[#bits + 1] = 'x' .. item.quantity end
    if #bits > 0 then lines[#lines + 1] = table.concat(bits, ' · ') end
    if item.description and item.description ~= '' then lines[#lines + 1] = item.description end
    UI.tooltip(table.concat(lines, '\n'))
end

local function shortText(text, n)
    text = tostring(text or '')
    if #text <= n then return text end
    return text:sub(1, n - 1) .. '…'
end

function Game.enter()
    drag = nil
    targets = {}
    autosave = 0
    endingOpened = false
    if not G() or not G().character then
        Manager.set('title')
    end
end

-- ───────────────────────────────────────────────────────── uso de item
local function placeStation(item, index)
    local G_ = G()
    local loc = DB.locations[G_.location]
    if not loc or not loc.allowsStations then
        State.addLog('❌ Você não pode montar esta estação aqui.')
        UI.toast('❌ Local inadequado para montar a estação.')
        return
    end
    local stype = item.stationType or 'crafting_table'
    G_.placedStations[G_.location] = G_.placedStations[G_.location] or {}
    G_.placedStations[G_.location][stype] = true
    Inventory.removeAt(G_.inventory, index, 1)
    G_.stats.stations = (G_.stats.stations or 0) + 1
    State.addLog(string.format('🔨 Você montou %s em %s.', item.name, loc.name))
    Achievements.check()
end

local function useItem(index)
    local item = G().inventory[index]
    if not item then return end
    local action, data = Inventory.use(index)
    if action == 'book' then
        if item.libraryBook then
            Modals.openBook(index)
        else
            Modals.openBook(index)
        end
    elseif action == 'map' then
        Map.openFull()
    elseif action == 'clock' then
        local left = math.max(0, math.floor(G().cycleRemaining or 0))
        State.addLog(string.format('🕰️ Faltam %d min para a próxima virada de dia/noite.', math.floor(left / 60)))
    elseif action == 'station' then
        placeStation(data, index)
    elseif action == 'container' then
        State.addLog(string.format('📦 %s: %s', data.name or 'Recipiente', data.description or 'Sem nada dentro.'))
        UI.toast('📦 ' .. shortText(data.description or 'Recipiente vazio.', 60))
    elseif action == 'equipped' then
        State.addLog(string.format('⚔️ Você equipou %s.', item.name))
    elseif action == 'error' then
        UI.toast('❌ ' .. tostring(data))
    elseif action == 'nothing' then
        UI.toast(string.format('ℹ️ %s', data.description or 'Você examina o item.'))
    end
    Achievements.check()
end

-- ───────────────────────────────────────────────────────── pedidos de UI
function Game.update(dt)
    local G_ = G()
    if not G_ or not G_.character then return end
    Time.update(dt)
    Survival.update(dt)
    Craft.update(dt)
    MG.update(dt)

    local req = Actions.pendingRequest()
    if req then
        Modals.handle(req)
    end

    -- minigame iniciado por uma ação (machado) precisa de modal
    if MG.active and not UI.modal then
        Modals.openMinigame()
    end
    if UI.modal and UI.modal.kind == 'minigame' and not MG.active then
        UI.closeModal()
    end
    if UI.modal and UI.modal.kind == 'sleep' and not G_.isSleeping then
        UI.closeModal()
    end

    -- combate tem prioridade sobre modais comuns
    if G_.enemy and UI.modal then
        local kind = UI.modal.kind
        if kind ~= 'death' and kind ~= 'ending' then
            UI.closeModal()
        end
    end

    if G_.isDead and not UI.modal then
        Modals.openDeath()
    end

    if G_.flags.endingPending and not G_.flags.endingShown and not UI.modal then
        Modals.openEnding()
        endingOpened = true
    end

    -- autosave periódico
    autosave = autosave + dt
    if autosave >= 45 then
        autosave = 0
        if not G_.enemy and not G_.isSleeping and not G_.isDead and not UI.modal then
            State.save(true)
        end
    end
end

-- ───────────────────────────────────────────────────────── topo
local function drawTopBar()
    local G_ = G()
    local c = G_.character
    local race = DB.races[c.race]
    local x, y, w, h = L.top.x, L.top.y, L.top.w, L.top.h
    UI.panel(x, y, w, h, { color = Theme.color.panel, radius = 10 })
    love.graphics.setColor(Theme.color.purple[1], Theme.color.purple[2], Theme.color.purple[3], 0.14)
    love.graphics.rectangle('fill', x, y, w, h, 10, 10)

    -- avatar
    love.graphics.setColor(Theme.color.purple[1], Theme.color.purple[2], Theme.color.purple[3], 0.30)
    love.graphics.circle('fill', x + 38, y + 32, 24)
    UI.circleLine(x + 38, y + 32, 24, Theme.color.gold, 1.5)
    Text.draw(Theme.font.lg, (c.name or '?'):sub(1, 1), x + 18, y + 18, 40, 'center', Theme.color.gold)

    Text.draw(Theme.font.boldMd, c.name, x + 72, y + 10, 220, 'left', Theme.color.text)
    Text.draw(Theme.font.xs, string.format('%s · Nível %d', race and race.name or c.race, c.level or 1),
        x + 72, y + 32, 220, 'left', Theme.color.muted)
    Text.draw(Theme.font.xs, string.format('%s · %s', c.gender or '', (c.age or 0) .. ' anos'),
        x + 72, y + 47, 220, 'left', Theme.color.dim)

    -- barras de vida/mana
    UI.bar(x + 292, y + 12, 200, 14, (c.life or 0) / math.max(1, c.maxLife),
        Theme.color.hp, { label = string.format('Vida %d/%d', c.life or 0, c.maxLife or 0) })
    UI.bar(x + 292, y + 34, 180, 12, (c.mana or 0) / math.max(1, c.maxMana),
        Theme.color.mana, { label = string.format('Mana %d/%d', c.mana or 0, c.maxMana or 0) })
    Text.draw(Theme.font.xs, string.format('EXP %d/%d', c.exp or 0, State.expNeeded()), x + 292, y + 50, 200, 'left', Theme.color.dim)
    UI.bar(x + 380, y + 51, 112, 5, (c.exp or 0) / math.max(1, State.expNeeded()), Theme.color.green)

    -- atributos
    Text.draw(Theme.font.xs, string.format('ATQ %d', Inventory.totalAttack()), x + 510, y + 14, 80, 'left', Theme.color.orange)
    Text.draw(Theme.font.xs, string.format('DEF %d', Inventory.totalDefense()), x + 510, y + 32, 80, 'left', Theme.color.blue)
    Text.draw(Theme.font.sm, string.format('💰 %d', c.gold or 0), x + 510, y + 49, 100, 'left', Theme.color.gold)

    -- data/clima
    local w_ = State.weather()
    Text.draw(Theme.font.sm, string.format('%s · %s', Time.phaseText(), Time.clockText()), x + 620, y + 12, 180, 'left', Theme.color.text)
    Text.draw(Theme.font.xs, string.format('%s · %s', State.shortDate(), w_.name or ''), x + 620, y + 33, 230, 'left', Theme.color.muted)
    Text.draw(Theme.font.xs, string.format('Ciclo: %s', G_.timeOfDay == 'day' and 'sol' or 'lua'), x + 620, y + 49, 200, 'left', Theme.color.dim)

    -- botões
    local bx = x + w - 292
    local bw, bh = 52, 34
    local by = y + 15
    local defs = {
        { id = 'hud_journal', label = 'Diário', fn = function() Modals.openJournal('quests') end },
        { id = 'hud_map', label = 'Mapa', fn = function() Map.openFull() end },
        { id = 'hud_profile', label = 'Perfil', fn = function() Modals.openProfile() end },
        { id = 'hud_save', label = 'Salvar', fn = function()
            if State.save() then UI.toast('💾 Jogo salvo.') else UI.toast('❌ Falha ao salvar.') end
        end },
        { id = 'hud_menu', label = 'Menu', fn = function() Modals.openMenu() end },
    }
    for i, b in ipairs(defs) do
        if UI.button(b.id, bx + (i - 1) * (bw + 5), by, bw, bh, b.label, {
            style = 'ghost', font = Theme.font.xs, onClick = b.fn,
        }) then end
    end
end

-- ───────────────────────────────────────────────────────── sobrevivência
local function drawSurvival()
    local x, y, w, h = L.surv.x, L.surv.y, L.surv.w, L.surv.h
    UI.panel(x, y, w, h, { color = Theme.color.panelAlt, radius = 8, highlight = false })
    local s = Survival.ensure() or { hunger = 0, thirst = 0, sanity = 0 }
    local bw = 208
    local by = y + 5
    UI.bar(x + 16, by, bw, 12, s.hunger / 100, Theme.color.hunger, { label = string.format('Fome %d', math.floor(s.hunger)) })
    UI.bar(x + 272, by, bw, 12, s.thirst / 100, Theme.color.thirst, { label = string.format('Sede %d', math.floor(s.thirst)) })
    UI.bar(x + 528, by, bw, 12, s.sanity / 100, Theme.color.sanity, { label = string.format('Sanidade %d', math.floor(s.sanity)) })

    local left = (s.hunger < 30 and 'Com fome! ' or '') .. (s.thirst < 30 and 'Com sede! ' or '') ..
        (s.sanity < 30 and 'Mente turva!' or '')
    Text.draw(Theme.font.xs, left, x + 756, y + 4, 290, 'left', Theme.color.orange)

    if Survival.hasWaterSource() then
        if UI.button('drink_water', x + w - 152, y + 2, 138, 18, 'Beber água', {
            style = 'blue', font = Theme.font.xs,
            onClick = function() Survival.drinkWater() end,
        }) then end
    else
        Text.draw(Theme.font.xs, 'Sem água por perto', x + w - 152, y + 4, 138, 'right', Theme.color.dim)
    end
end

-- ───────────────────────────────────────────────────────── inventário
local function drawSlot(x, y, w, h, item, index)
    local hover = UI.hover(x, y, w, h)
    love.graphics.setColor(0, 0, 0, 0.28)
    love.graphics.rectangle('fill', x, y, w, h, 7, 7)
    if item then
        local col = TYPE_COLOR[item.type] or Theme.color.muted
        love.graphics.setColor(1, 1, 1, hover and 0.10 or 0.055)
        love.graphics.rectangle('fill', x, y, w, h, 7, 7)
        love.graphics.setColor(col[1], col[2], col[3], 0.85)
        love.graphics.rectangle('fill', x, y + 5, 3, h - 10, 2, 2)

        local label = itemLabel(item)
        local lines = Text.wrap(Theme.font.xs, label, w - 16)
        local shown = 0
        for i = 1, math.min(2, #lines) do
            Text.draw(Theme.font.xs, lines[i], x + 8, y + 5 + (i - 1) * 13, w - 16, 'left', Theme.color.text)
            shown = shown + 1
        end
        if (item.quantity or 1) > 1 then
            Text.draw(Theme.font.xs, 'x' .. item.quantity, x + w - 30, y + h - 16, 24, 'right', Theme.color.gold)
        end
        if item.maxDurability then
            local pct = (item.durability or 0) / math.max(1, item.maxDurability)
            UI.bar(x + 7, y + h - 7, w - 14, 3, pct, pct > 0.35 and Theme.color.green or Theme.color.red)
        end
        if hover then itemTooltip(item) end
        if hover and UI.pressed and UI.pressedButton == 1 and not UI.blocked then
            UI.consumeClick()
            drag = { index = index, item = item, sx = UI.mx, sy = UI.my }
        end
    else
        love.graphics.setColor(1, 1, 1, 0.045)
        love.graphics.rectangle('line', x + 0.5, y + 0.5, w - 1, h - 1, 7, 7)
    end
end

local function drawInventory()
    local G_ = G()
    local x, y, w, h = L.inv.x, L.inv.y, L.inv.w, L.inv.h
    UI.panel(x, y, w, h, { color = Theme.color.panel, radius = 10 })
    Text.draw(Theme.font.boldMd, 'Mochila', x + 14, y + 10, 140, 'left', Theme.color.gold)
    local used = 0
    for i = 1, Inventory.SLOTS do if G_.inventory[i] then used = used + 1 end end
    Text.draw(Theme.font.xs, string.format('%d/%d', used, Inventory.SLOTS), x + 96, y + 15, 50, 'left', Theme.color.muted)
    if UI.button('organize_inv', x + w - 96, y + 8, 84, 26, 'Organizar', {
        style = 'ghost', font = Theme.font.xs,
        onClick = function()
            Inventory.organize(G_.inventory)
            UI.toast('🎒 Mochila organizada.')
        end,
    }) then end
    UI.divider(x + 12, y + 38, w - 24, 0.07)

    local cols, gap = 3, 6
    local gx = x + 12
    local gy = y + 46
    local sw = (w - 24 - gap * (cols - 1)) / cols
    local sh = 56
    for i = 1, Inventory.SLOTS do
        local col = (i - 1) % cols
        local row = math.floor((i - 1) / cols)
        local sx = gx + col * (sw + gap)
        local sy = gy + row * (sh + gap)
        drawSlot(sx, sy, sw, sh, G_.inventory[i], i)
        targets[#targets + 1] = { kind = 'inv', index = i, x = sx, y = sy, w = sw, h = sh }
    end
    Text.draw(Theme.font.xs, 'Clique para usar/equipar · arraste para mover', x + 12, y + h - 20, w - 24, 'center', Theme.color.dim)
end

-- ───────────────────────────────────────────────────────── equipamento / lado direito
local function drawRight()
    local G_ = G()
    local x, y, w, h = L.right.x, L.right.y, L.right.w, L.right.h
    UI.panel(x, y, w, h, { color = Theme.color.panel, radius = 10 })
    Text.draw(Theme.font.boldMd, 'Equipamento', x + 14, y + 10, 180, 'left', Theme.color.gold)
    UI.divider(x + 12, y + 34, w - 24, 0.07)

    local rowY = y + 42
    local rowH = 34
    for i, slot in ipairs(EQUIP_ORDER) do
        local label = EQUIP_LABELS[slot]
        local item = G_.equipment[slot]
        local ry = rowY + (i - 1) * (rowH + 3)
        local hover = UI.hover(x + 12, ry, w - 24, rowH)
        love.graphics.setColor(1, 1, 1, hover and 0.09 or 0.04)
        love.graphics.rectangle('fill', x + 12, ry, w - 24, rowH, 6, 6)
        love.graphics.setColor(Theme.color.purple[1], Theme.color.purple[2], Theme.color.purple[3], 0.25)
        love.graphics.rectangle('fill', x + 17, ry + 5, 24, rowH - 10, 4, 4)
        Text.draw(Theme.font.bold, label[1], x + 17, ry + 8, 24, 'center', Theme.color.text)
        if item then
            Text.draw(Theme.font.xs, shortText(itemLabel(item), 22), x + 48, ry + 5, w - 62, 'left', Theme.color.text)
            local sub = {}
            if (item.attack or 0) > 0 then sub[#sub + 1] = 'ATQ+' .. item.attack end
            if (item.defense or 0) > 0 then sub[#sub + 1] = 'DEF+' .. item.defense end
            if item.maxDurability then sub[#sub + 1] = string.format('%d/%d', item.durability or 0, item.maxDurability) end
            Text.draw(Theme.font.xs, table.concat(sub, ' '), x + 48, ry + 19, w - 62, 'left', Theme.color.muted)
            if hover then itemTooltip(item) end
            if hover and UI.pressed and UI.pressedButton == 1 and not UI.blocked then
                UI.consumeClick()
                local ok, err = Inventory.unequip(slot)
                if not ok then UI.toast('❌ ' .. tostring(err)) end
            end
        else
            Text.draw(Theme.font.xs, '— ' .. label[2], x + 48, ry + 9, w - 62, 'left', Theme.color.dim)
        end
        targets[#targets + 1] = { kind = 'equip', slot = slot, x = x + 12, y = ry, w = w - 24, h = rowH }
    end

    -- atributos
    local sy = rowY + 6 * (rowH + 3) + 6
    UI.divider(x + 12, sy, w - 24, 0.08)
    Text.draw(Theme.font.bold, 'Atributos', x + 14, sy + 8, w - 28, 'left', Theme.color.gold)
    local c = G_.character
    Text.draw(Theme.font.xs, string.format('Ataque %d    Defesa %d', Inventory.totalAttack(), Inventory.totalDefense()),
        x + 14, sy + 28, w - 28, 'left', Theme.color.text)
    Text.draw(Theme.font.xs, string.format('Nível %d · EXP %d/%d', c.level or 1, c.exp or 0, State.expNeeded()),
        x + 14, sy + 46, w - 28, 'left', Theme.color.muted)
    Text.draw(Theme.font.sm, string.format('💰 %d moedas', c.gold or 0), x + 14, sy + 64, w - 28, 'left', Theme.color.gold)

    -- missão ativa
    local qy = sy + 88
    UI.divider(x + 12, qy, w - 24, 0.08)
    Text.draw(Theme.font.bold, 'Missão', x + 14, qy + 8, 100, 'left', Theme.color.gold)
    local active = Quests.active()
    if active then
        Text.draw(Theme.font.xs, shortText(active.name, 30), x + 14, qy + 28, w - 28, 'left', Theme.color.text)
        local stage, idx = Quests.currentStage()
        local p, need = Quests.progress()
        Text.draw(Theme.font.xs, string.format('%d/%d · %s', idx or 0, #active.stages, stage and (stage.name or '') or ''),
            x + 14, qy + 44, w - 28, 'left', Theme.color.muted)
        UI.bar(x + 14, qy + 62, w - 28, 6, p / math.max(1, need), Theme.color.gold)
        if UI.button('tracker_journal', x + 14, qy + 74, w - 28, 24, 'Abrir diário', {
            style = 'ghost', font = Theme.font.xs,
            onClick = function() Modals.openJournal('quests') end,
        }) then end
    else
        Text.draw(Theme.font.xs, 'Nenhuma missão ativa.', x + 14, qy + 28, w - 28, 'left', Theme.color.dim)
        if UI.button('tracker_board', x + 14, qy + 48, w - 28, 24, 'Ver quadro de missões', {
            style = 'ghost', font = Theme.font.xs,
            onClick = function() Modals.openQuestBoard() end,
        }) then end
    end
end

-- ───────────────────────────────────────────────────────── combate
local function strikeLabel(strike)
    local dmg
    if strike.type == 'heal' then
        dmg = 'cura'
    elseif strike.ranged then
        dmg = 'à distância'
    else
        local mn, mx = Combat.strikeRange(strike)
        dmg = string.format('%d–%d', mn, mx)
    end
    local cost = (strike.mana or 0) > 0 and string.format(' · %d mana', strike.mana) or ''
    return strike.name, dmg .. cost
end

local function drawCombat(x, y, w, h)
    local G_ = G()
    local enemy = G_.enemy
    if not enemy then return end
    UI.panel(x, y, w, h, { color = Theme.color.panel, radius = 10 })
    love.graphics.setColor(Theme.color.red[1], Theme.color.red[2], Theme.color.red[3], 0.08)
    love.graphics.rectangle('fill', x, y, w, 96, 10, 10)
    love.graphics.rectangle('fill', x, y + 70, w, 26)

    Text.draw(Theme.font.boldLg, enemy.name or 'Inimigo', x + 16, y + 12, w - 190, 'left', Theme.color.red)
    Text.draw(Theme.font.xs, string.format('ATQ %d · DEF %d · EXP %d · Ouro %d', enemy.attack or 0, enemy.defense or 0,
        enemy.exp or 0, enemy.gold or 0), x + 16, y + 38, w - 190, 'left', Theme.color.muted)
    UI.bar(x + 16, y + 60, w - 190, 18, (enemy.life or 0) / math.max(1, enemy.maxLife or enemy.life or 1), Theme.color.red,
        { label = string.format('Vida %d/%d', math.max(0, math.floor(enemy.life or 0)), math.floor(enemy.maxLife or enemy.life or 0)) })

    -- status do jogador
    local c = G_.character
    local px = x + w - 160
    UI.bar(px, y + 16, 144, 12, (c.life or 0) / math.max(1, c.maxLife), Theme.color.hp)
    UI.bar(px, y + 32, 144, 10, (c.mana or 0) / math.max(1, c.maxMana), Theme.color.mana)
    Text.draw(Theme.font.xs, string.format('Você: %d/%d', c.life or 0, c.maxLife or 0), px, y + 46, 144, 'left', Theme.color.text)
    if G_.flags.evasionActive then
        Text.draw(Theme.font.xs, 'Preparado para esquivar', px, y + 60, 144, 'left', Theme.color.cyan)
    end

    -- registro curto
    local ly = y + 106
    local lh = 122
    love.graphics.setColor(0, 0, 0, 0.25)
    love.graphics.rectangle('fill', x + 12, ly, w - 24, lh, 7, 7)
    local row = ly + 8
    for i = 1, math.min(5, #G_.combatLog) do
        local line = Text.wrap(Theme.font.xs, G_.combatLog[i], w - 44)
        for j = 1, math.min(2, #line) do
            if row + 14 > ly + lh then break end
            Text.draw(Theme.font.xs, line[j], x + 20, row, w - 40, 'left',
                i == 1 and Theme.color.text or Theme.color.muted)
            row = row + 13
        end
    end
    -- painel de golpes/habilidades
    local panelY = ly + lh + 8
    local panelH = 112
    if G_.combatPanel == 'strikes' then
        local strikes = Combat.availableStrikes()
        local cols = 2
        local bw = (w - 24 - 8) / cols
        for i, s in ipairs(strikes) do
            local col = (i - 1) % cols
            local rowI = math.floor((i - 1) / cols)
            if rowI >= 3 then break end
            local name, sub = strikeLabel(s)
            if UI.button('strike_' .. tostring(s.id) .. tostring(i), x + 12 + col * (bw + 8), panelY + rowI * 36, bw, 32, name, {
                style = 'default', font = Theme.font.xs, sub = sub,
                onClick = function() Combat.useStrike(s.id) end,
            }) then end
        end
    elseif G_.combatPanel == 'abilities' then
        local abilities = Combat.availableAbilities()
        local cols = 2
        local bw = (w - 24 - 8) / cols
        local all = {}
        for _, a in ipairs(abilities) do all[#all + 1] = { kind = 'ability', def = a } end
        local skill = Combat.racialSkill()
        if skill then all[#all + 1] = { kind = 'skill', def = skill } end
        if #all == 0 then
            Text.draw(Theme.font.xs, 'Nenhuma habilidade aprendida ainda. Suba de nível!', x + 16, panelY + 8, w - 32, 'left', Theme.color.dim)
        end
        for i, entry in ipairs(all) do
            if i > 6 then break end
            local col = (i - 1) % cols
            local rowI = math.floor((i - 1) / cols)
            local d = entry.def
            if UI.button('ability_' .. i, x + 12 + col * (bw + 8), panelY + rowI * 36, bw, 32, d.name, {
                style = entry.kind == 'skill' and 'gold' or 'default', font = Theme.font.xs,
                sub = (d.desc or '') .. ((d.cost or d.mana) and (' · ' .. (d.cost or d.mana) .. ' mana') or ''),
                onClick = function()
                    if entry.kind == 'skill' then Combat.useRacialSkill() else Combat.useStrike(d.id) end
                end,
            }) then end
        end
    else
        Text.draw(Theme.font.xs, 'Escolha um golpe ou habilidade. A sanidade baixa pode fazer magias falharem.',
            x + 16, panelY + 10, w - 32, 'left', Theme.color.dim)
    end

    -- botões principais
    local by = y + h - 56
    local gap = 8
    local bw = (w - 24 - gap * 3) / 4
    if UI.button('combat_attack', x + 12, by, bw, 42, 'Atacar', {
        style = 'danger', icon = '⚔️',
        onClick = function() Combat.attack() end,
    }) then end
    if UI.button('combat_strikes', x + 12 + (bw + gap), by, bw, 42, 'Golpes', {
        style = G_.combatPanel == 'strikes' and 'gold' or 'default',
        onClick = function() G_.combatPanel = G_.combatPanel == 'strikes' and nil or 'strikes' end,
    }) then end
    if UI.button('combat_abilities', x + 12 + (bw + gap) * 2, by, bw, 42, 'Habilidades', {
        style = G_.combatPanel == 'abilities' and 'gold' or 'default',
        onClick = function() G_.combatPanel = G_.combatPanel == 'abilities' and nil or 'abilities' end,
    }) then end
    if UI.button('combat_flee', x + 12 + (bw + gap) * 3, by, bw, 42, 'Fugir', {
        style = 'ghost',
        onClick = function() Combat.flee() end,
    }) then end
end

-- ───────────────────────────────────────────────────────── local
local function drawLocation(x, y, w, h)
    local G_ = G()
    local loc = DB.locations[G_.location] or { name = G_.location, description = '', actions = {} }
    UI.panel(x, y, w, h, { color = Theme.color.panel, radius = 10 })
    Text.draw(Theme.font.boldLg, loc.name or G_.location, x + 16, y + 10, w - 220, 'left', Theme.color.gold)
    local outdoor = DB.isOutdoor(G_.location)
    Text.draw(Theme.font.xs, outdoor and 'Exterior' or 'Interior', x + w - 190, y + 16, 60, 'right', Theme.color.muted)
    if UI.button('loc_map', x + w - 124, y + 9, 108, 26, 'Mapa completo', {
        style = 'ghost', font = Theme.font.xs,
        onClick = function() Map.openFull() end,
    }) then end
    Text.draw(Theme.font.xs, shortText(loc.description or '', 150), x + 16, y + 36, w - 32, 'left', Theme.color.muted, 1.2)
    UI.divider(x + 14, y + 56, w - 28, 0.07)

    local actionsY
    if outdoor then
        local mapH = 190
        local fn = Map.draw(x + 14, y + 62, w - 28, mapH, { zoomable = false })
        if fn then Actions.perform(fn) end
        actionsY = y + 62 + mapH + 8
    else
        actionsY = y + 64
    end

    -- lista de ações
    local entries = {}
    for _, o in ipairs(DB.walkOptions(G_.location)) do
        entries[#entries + 1] = { label = o.label, fn = o.fn, style = 'ghost' }
    end
    for _, a in ipairs(DB.localInteractions(G_.location)) do
        entries[#entries + 1] = { label = a.name, fn = a.action, style = 'default' }
    end
    -- estações montadas / fixas
    local placed = G_.placedStations[G_.location] or {}
    for stype in pairs(placed) do
        local info = Craft.stationInfo(stype)
        entries[#entries + 1] = {
            label = info.icon .. ' ' .. info.name,
            onClick = function() Modals.openStation(stype) end,
            style = 'warning',
        }
    end
    if G_.location == 'mill' then
        entries[#entries + 1] = { label = '🌾 Moinho', onClick = function() Modals.openStation('mill') end, style = 'warning' }
        entries[#entries + 1] = { label = '🔥 Fornalha', onClick = function() Modals.openStation('furnace') end, style = 'warning' }
    elseif G_.location == 'forge_workshop' then
        entries[#entries + 1] = { label = '⚒️ Bigorna', onClick = function() Modals.openStation('anvil') end, style = 'warning' }
        entries[#entries + 1] = { label = '🔥 Fornalha', onClick = function() Modals.openStation('furnace') end, style = 'warning' }
    end
    if Survival.hasWaterSource() then
        entries[#entries + 1] = { label = '💧 Beber água', onClick = function() Survival.drinkWater() end, style = 'blue' }
    end

    local listH = y + h - actionsY - 8
    UI.scroll('loc_actions', x + 12, actionsY, w - 24, listH, function(sx, sy, sw)
        if #entries == 0 then
            Text.draw(Theme.font.sm, 'Não há nada para fazer aqui agora.', sx, sy, sw, 'left', Theme.color.dim)
            return 24
        end
        local cols = 2
        local gap = 6
        local bw = (sw - gap) / cols
        local bh = 30
        local row = 0
        local col = 0
        for _, e in ipairs(entries) do
            if UI.button('act_' .. col .. '_' .. row, sx + col * (bw + gap), sy + row * (bh + gap), bw, bh, e.label, {
                style = e.style or 'default', font = Theme.font.xs,
                onClick = function()
                    if e.onClick then e.onClick() else Actions.perform(e.fn) end
                end,
            }) then break end
            col = col + 1
            if col >= cols then col = 0 row = row + 1 end
        end
        return (row + 1) * (bh + gap)
    end)
end

-- ───────────────────────────────────────────────────────── registro
local function logColor(line)
    if line:find('❌') or line:find('💀') or line:find('⚠️') then return Theme.color.red end
    if line:find('✨') or line:find('🏆') or line:find('🌟') then return Theme.color.gold end
    if line:find('✅') or line:find('❤️') or line:find('💚') then return Theme.color.green end
    if line:find('💬') then return Theme.color.cyan end
    if line:find('🎁') or line:find('💰') then return Theme.color.gold end
    return Theme.color.text
end

local function drawLogPanel()
    local G_ = G()
    local x, y, w, h = L.log.x, L.log.y, L.log.w, L.log.h
    UI.panel(x, y, w, h, { color = Theme.color.panel, radius = 10 })
    Text.draw(Theme.font.bold, 'Registro', x + 14, y + 8, 100, 'left', Theme.color.gold)
    Text.draw(Theme.font.xs, string.format('%d entradas', #G_.combatLog), x + 80, y + 11, 120, 'left', Theme.color.dim)
    Text.draw(Theme.font.xs, 'Role com a roda do mouse', x + w - 200, y + 11, 186, 'right', Theme.color.dim)
    UI.scroll('game_log', x + 12, y + 30, w - 24, h - 38, function(sx, sy, sw)
        local row = 0
        local font = Theme.font.sm
        for i = 1, math.min(200, #G_.combatLog) do
            local line = G_.combatLog[i]
            local lines = Text.wrap(font, line, sw - 18)
            local col = logColor(line)
            for _, l in ipairs(lines) do
                Text.draw(font, l, sx + 4, sy + row, sw - 18, 'left', col, 1.2)
                row = row + font:getHeight() * 1.22
            end
            row = row + 1
        end
        return row
    end)
end

-- ───────────────────────────────────────────────────────── drag & drop
local function resolveDrag()
    if not drag then return end
    if not UI.released then return end
    local moved = math.abs(UI.mx - drag.sx) + math.abs(UI.my - drag.sy) > 7
    local target
    for _, t in ipairs(targets) do
        if UI.mx >= t.x and UI.mx <= t.x + t.w and UI.my >= t.y and UI.my <= t.y + t.h then
            target = t
            break
        end
    end
    if not moved then
        useItem(drag.index)
    elseif target then
        if target.kind == 'inv' then
            Inventory.move(G().inventory, drag.index, G().inventory, target.index)
        elseif target.kind == 'equip' then
            local item = G().inventory[drag.index]
            if item and item.slot == target.slot then
                Inventory.equip(drag.index)
            else
                UI.toast('❌ Este item não vai nesse slot.')
            end
        end
    end
    drag = nil
end

local function drawDragGhost()
    if not drag or not drag.item then return end
    local item = G().inventory[drag.index]
    if not item then return end
    local label = itemLabel(item)
    local w = math.min(220, Theme.font.sm:getWidth(label) + 26)
    local x = UI.mx + 14
    local y = UI.my + 12
    love.graphics.setColor(0, 0, 0, 0.85)
    love.graphics.rectangle('fill', x, y, w, 30, 6, 6)
    love.graphics.setColor(Theme.color.gold[1], Theme.color.gold[2], Theme.color.gold[3], 0.6)
    love.graphics.rectangle('line', x + 0.5, y + 0.5, w - 1, 29, 6, 6)
    Text.draw(Theme.font.sm, shortText(label, 26), x + 10, y + 7, w - 20, 'left', Theme.color.text)
end

-- ───────────────────────────────────────────────────────── desenho
function Game.draw()
    local G_ = G()
    if not G_ or not G_.character then return end
    targets = {}

    UI.vgradient(0, 0, 1280, 720, { 0.035, 0.03, 0.065, 1 }, { 0.065, 0.05, 0.10, 1 }, 40)
    -- vinheta
    love.graphics.setColor(0, 0, 0, 0.25)
    love.graphics.rectangle('fill', 0, 0, 1280, 8)
    love.graphics.rectangle('fill', 0, 712, 1280, 8)

    drawTopBar()
    drawSurvival()
    drawInventory()
    if G_.enemy then
        drawCombat(L.mid.x, L.mid.y, L.mid.w, L.mid.h)
    else
        drawLocation(L.mid.x, L.mid.y, L.mid.w, L.mid.h)
    end
    drawRight()
    drawLogPanel()
    drawDragGhost()
    resolveDrag()

    if drag then
        Text.draw(Theme.font.xs, 'Solte sobre um slot para mover, ou sobre o equipamento para equipar.', 0, 552, 1280, 'center', Theme.color.dim)
    end
end

function Game.keypressed(key)
    if UI.modal then return false end
    if key == 'm' then
        Map.openFull()
        return true
    elseif key == 'j' then
        Modals.openJournal('quests')
        return true
    elseif key == 'p' then
        Modals.openProfile()
        return true
    elseif key == 'escape' then
        Modals.openMenu()
        return true
    end
end

return Game
