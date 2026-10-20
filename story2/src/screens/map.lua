-- Mapa-múndi vetorial (nós, estradas e rótulos) desenhado com LÖVE.
local UI = require('src.core.ui')
local Theme = require('src.core.theme')
local Text = require('src.core.text')
local DB = require('src.data.init')
local State = require('src.game.state')
local Actions = require('src.game.actions')
local U = require('src.core.util')

local Map = {}

Map.panX, Map.panY, Map.zoom = 0, 0, 1
Map.dragging = false
Map.dragX, Map.dragY = 0, 0
Map.moved = false

local edges

local function G() return State.G end

local function bounds()
    local minx, miny, maxx, maxy = 1e9, 1e9, -1e9, -1e9
    for _, n in pairs(DB.mapnodes) do
        minx = math.min(minx, n.x)
        maxx = math.max(maxx, n.x)
        miny = math.min(miny, n.y)
        maxy = math.max(maxy, n.y)
    end
    minx = minx - 40
    miny = miny - 30
    maxx = maxx + 40
    maxy = maxy + 30
    return minx, miny, maxx, maxy
end

local function getEdges()
    if not edges then edges = DB.worldEdges() end
    return edges
end

local REGIONS = {
    { x = 530, y = 405, text = 'REINO DA AURORA', size = 'xl', color = { 0.55, 0.62, 0.95, 0.10 } },
    { x = 820, y = 150, text = 'FLORESTA SOMBRIA', size = 'md', color = { 0.40, 0.85, 0.50, 0.12 } },
    { x = 545, y = 735, text = 'ALDÉIAS DO SUL', size = 'md', color = { 0.95, 0.65, 0.30, 0.12 } },
    { x = 900, y = 520, text = 'TERRAS DO LESTE', size = 'md', color = { 0.85, 0.78, 0.35, 0.10 } },
    { x = 145, y = 225, text = 'CEMITÉRIO', size = 'sm', color = { 0.70, 0.72, 0.80, 0.14 } },
    { x = 155, y = 760, text = 'LAGO SAGRADO', size = 'sm', color = { 0.35, 0.80, 0.90, 0.16 } },
    { x = 930, y = 320, text = 'RIO AURORA', size = 'sm', color = { 0.35, 0.70, 0.90, 0.12 } },
}

local FOREST = { north_forest_edge = true, dark_forest = true, dragon_peak = true, north_trail_middle = true, north_trail_start = true, north_trail_end = true }
local CEMETERY = { abandoned_cemetery = true, abandoned_cemetery_gate = true, cemetery_graves = true, cemetery_mausoleum = true }
local WATER = { sacred_lake = true, sacred_lake_interior = true, river_bank = true, swim_in_river = true, west_bridge = true, across_bridge = true }
local SOUTH = { south_road = true, south_trade_route = true, south_villages = true, south_village = true,
    south_village_market = true, south_village_forge = true, south_village_orchard = true, south_village_square = true,
    south_mine = true, twilight_gate = true, twilight_citadel = true, forge_workshop = true }
local EAST = { outside = true, east_plains = true, east_wilds = true, east_ruins_path = true, east_ruins_camp = true,
    ancient_ruins = true, outside_back = true, back_forest_trail_north = true, back_forest_trail_south = true }

local function nodeColor(id, node)
    if id == 'dragon_peak' then return Theme.color.red end
    if id == 'twilight_citadel' or id == 'twilight_gate' then return { 0.65, 0.40, 0.95, 1 } end
    if FOREST[id] then return { 0.35, 0.78, 0.46, 1 } end
    if CEMETERY[id] then return { 0.68, 0.70, 0.78, 1 } end
    if WATER[id] then return { 0.30, 0.78, 0.92, 1 } end
    if SOUTH[id] then return { 0.95, 0.62, 0.28, 1 } end
    if EAST[id] then return { 0.88, 0.78, 0.35, 1 } end
    return { 0.45, 0.55, 0.95, 1 }
end

function Map.adjacent()
    local set = {}
    local G_ = G()
    if not G_ then return set end
    for _, o in ipairs(DB.walkOptions(G_.location)) do
        set[o.target] = o.fn
    end
    return set
end

-- Desenha o mapa dentro de (x,y,w,h). Retorna id do nó clicado (se adjacente).
function Map.draw(x, y, w, h, opts)
    opts = opts or {}
    local G_ = G()
    if not G_ then return nil end
    local zoomable = opts.zoomable == true
    local minx, miny, maxx, maxy = bounds()
    local bw, maxy2 = maxx - minx, maxy - miny
    local pad = 34
    local base = math.min((w - pad * 2) / bw, (h - pad * 2) / maxy2)
    local zoom = zoomable and Map.zoom or 1
    local panX = zoomable and Map.panX or 0
    local panY = zoomable and Map.panY or 0
    local scale = base * zoom
    local ox = x + w * 0.5 - (bw * scale) * 0.5 + panX
    local oy = y + h * 0.5 - (maxy2 * scale) * 0.5 + panY

    local function tx(wx) return ox + (wx - minx) * scale end
    local function ty(wy) return oy + (wy - miny) * scale end

    UI.clip(x, y, w, h)
    -- fundo
    UI.vgradient(x, y, w, h, { 0.055, 0.075, 0.095, 1 }, { 0.045, 0.055, 0.085, 1 }, 28)
    -- grade de pontos
    love.graphics.setColor(1, 1, 1, 0.035)
    for gx = x + 20, x + w - 10, 34 do
        for gy = y + 20, y + h - 10, 34 do
            love.graphics.circle('fill', gx, gy, 0.8)
        end
    end

    -- regiões
    for _, r in ipairs(REGIONS) do
        local font = r.size == 'xl' and Theme.font.xl or (r.size == 'md' and Theme.font.md or Theme.font.xs)
        Text.draw(font, r.text, tx(r.x) - 200, ty(r.y) - 10, 400, 'center', r.color)
    end

    -- estradas
    for _, e in ipairs(getEdges()) do
        local a, b = DB.mapnodes[e[1]], DB.mapnodes[e[2]]
        if a and b then
            love.graphics.setColor(0.75, 0.72, 0.60, 0.18)
            love.graphics.setLineWidth(1.2)
            love.graphics.line(tx(a.x), ty(a.y), tx(b.x), ty(b.y))
        end
    end

    -- nós
    local adj = Map.adjacent()
    local hovered, clicked = nil, nil
    for id, node in pairs(DB.mapnodes) do
        local nx, ny = tx(node.x), ty(node.y)
        if nx >= x - 20 and nx <= x + w + 20 and ny >= y - 20 and ny <= y + h + 20 then
            local isCurrent = id == G_.location
            local isAdj = adj[id] ~= nil
            local visited = G_.stats.locations[id] == true
            local r = (node.big and 7 or 4.6)
            local col = nodeColor(id, node)
            local hover = UI.hover(nx - 10, ny - 10, 20, 20)
            if hover then hovered = id end

            if isCurrent then
                local pulse = 0.5 + 0.5 * math.sin(UI.time * 3)
                love.graphics.setColor(Theme.color.gold[1], Theme.color.gold[2], Theme.color.gold[3], 0.18 + 0.20 * pulse)
                love.graphics.circle('fill', nx, ny, r + 7 + pulse * 3)
            end
            if isAdj and not isCurrent then
                love.graphics.setColor(col[1], col[2], col[3], 0.18)
                love.graphics.circle('fill', nx, ny, r + 5)
            end

            love.graphics.setColor(0, 0, 0, 0.55)
            love.graphics.circle('fill', nx + 1, ny + 1, r)
            if visited or isAdj or isCurrent then
                love.graphics.setColor(col[1], col[2], col[3], isCurrent and 1 or (visited and 0.95 or 0.55))
            else
                love.graphics.setColor(0.45, 0.45, 0.52, 0.55)
            end
            love.graphics.circle('fill', nx, ny, r)
            love.graphics.setColor(1, 1, 1, isCurrent and 0.9 or 0.25)
            love.graphics.setLineWidth(1)
            love.graphics.circle('line', nx, ny, r)

            if id == 'dragon_peak' or id == 'twilight_citadel' or id == 'twilight_gate' then
                love.graphics.setColor(1, 0.4, 0.4, 0.9)
                love.graphics.circle('fill', nx + r + 3, ny - r - 1, 1.8)
            end

            local showLabel = isCurrent or isAdj or hover or (node.big and scale > 0.40) or (visited and scale > 0.62)
            if showLabel then
                local label = Text.clean(node.name or id)
                local font = Theme.font.xs
                local tw = font:getWidth(label) + 8
                local ly = ny + r + 2
                love.graphics.setColor(0.05, 0.05, 0.09, 0.78)
                love.graphics.rectangle('fill', nx - tw * 0.5, ly - 1, tw, font:getHeight() + 3, 3, 3)
                Text.draw(font, label, nx - tw * 0.5, ly + 1, tw, 'center', isCurrent and Theme.color.gold or (visited and Theme.color.text or Theme.color.muted))
            end

            if hover then
                UI.tooltip(string.format('%s%s', node.name or id,
                    isCurrent and ' (você está aqui)' or (isAdj and ' — clique para viajar' or (visited and ' — sem caminho direto' or ' — inexplorado'))))
            end

            if hover and UI.pressed and UI.pressedButton == 1 then
                UI.consumeClick()
                clicked = id
            end
        end
    end
    UI.unclip()

    -- zoom/pan no mapa grande
    if zoomable then
        local hover = UI.hit(x, y, w, h)
        if hover and UI.wheel ~= 0 then
            local old = Map.zoom
            Map.zoom = U.clamp(Map.zoom + UI.wheel * 0.12, 0.7, 2.6)
            -- zoom ancorado no cursor
            local cx = (UI.mx - (x + w * 0.5)) / old
            local cy = (UI.my - (y + h * 0.5)) / old
            Map.panX = Map.panX - cx * (Map.zoom - old)
            Map.panY = Map.panY - cy * (Map.zoom - old)
            UI.wheel = 0
        end
        if hover and UI.pressed and UI.pressedButton == 1 and not clicked then
            Map.dragging = true
            Map.dragX, Map.dragY = UI.mx, UI.my
            Map.moved = false
        end
        if Map.dragging then
            if UI.down then
                local dx, dy = UI.mx - Map.dragX, UI.my - Map.dragY
                if math.abs(dx) + math.abs(dy) > 3 then Map.moved = true end
                Map.panX = Map.panX + dx
                Map.panY = Map.panY + dy
                Map.dragX, Map.dragY = UI.mx, UI.my
            else
                Map.dragging = false
            end
        end
    end

    if clicked then
        if clicked == G_.location then
            UI.toast('Você já está aqui.')
        elseif adj[clicked] then
            local fn = adj[clicked]
            Map.panX, Map.panY, Map.zoom = 0, 0, 1
            return fn
        else
            UI.toast('Não há caminho direto daqui até ' .. Text.clean(DB.mapnodes[clicked].name or clicked) .. '.')
        end
    end
    return nil
end

function Map.openFull()
    local G_ = G()
    UI.openModal({
        title = 'Mapa do Mundo',
        width = 1120,
        height = 660,
        closable = true,
        body = function(x, y, w, h)
            -- botões de zoom
            if UI.button('map_zoom_in', x, y, 34, 30, '+', { style = 'ghost', font = Theme.font.lg }) then
                Map.zoom = U.clamp(Map.zoom + 0.15, 0.7, 2.6)
            end
            if UI.button('map_zoom_out', x + 40, y, 34, 30, '−', { style = 'ghost', font = Theme.font.lg }) then
                Map.zoom = U.clamp(Map.zoom - 0.15, 0.7, 2.6)
            end
            if UI.button('map_reset', x + 80, y, 84, 30, 'Centralizar', { style = 'ghost', font = Theme.font.xs }) then
                Map.panX, Map.panY, Map.zoom = 0, 0, 1
            end
            Text.draw(Theme.font.xs, 'Arraste para mover · roda do mouse para zoom · clique num local adjacente para viajar',
                x + 176, y + 9, w - 180, 'left', Theme.color.dim)

            local fn = Map.draw(x, y + 38, w, h - 38, { zoomable = true })
            if fn then
                Actions.perform(fn)
                UI.closeModal()
            end
            return h
        end,
        buttons = {
            { text = 'Fechar', style = 'ghost' },
        },
    })
end

return Map
