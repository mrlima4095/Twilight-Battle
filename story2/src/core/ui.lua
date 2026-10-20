-- UI imediata (immediate mode) desenhada em coordenadas virtuais 1280x720.
-- Widgets tratam clique no próprio desenho; o estado de input é zerado no fim
-- do frame. Modais bloqueiam a UI de trás.
local Theme = require('src.core.theme')
local Text = require('src.core.text')
local Scale = require('src.core.scale')
local U = require('src.core.util')

local UI = {}

UI.mx, UI.my = 0, 0
UI.pressed = false
UI.pressedButton = nil
UI.released = false
UI.releasedButton = nil
UI.down = false
UI.wheel = 0
UI.blocked = false
UI.focus = nil
UI.input = {}
UI.inputMax = {}
UI.submitted = {}
UI.drag = nil
UI.time = 0

UI.clipStack = {}
UI.scrollOffsets = {}
UI.scrollHeights = {}

UI.modal = nil
UI.toasts = {}
UI.tooltipData = nil

UI.onModalClose = nil

-- ───────────────────────────────────────────────────────────── desenho básico
local g = love.graphics

function UI.setColor(c, a)
    g.setColor(c[1], c[2], c[3], a or c[4] or 1)
end

function UI.roundRect(mode, x, y, w, h, r)
    r = math.min(r or 8, h * 0.5, w * 0.5)
    g.rectangle(mode, x, y, w, h, r, r)
end

function UI.panel(x, y, w, h, opt)
    opt = opt or {}
    local c = opt.color or Theme.color.panel
    UI.setColor(c)
    UI.roundRect('fill', x, y, w, h, opt.radius or 10)
    if opt.highlight ~= false then
        g.setColor(1, 1, 1, 0.05)
        UI.roundRect('fill', x + 1, y + 1, w - 2, math.min(h - 2, 30), opt.radius or 10)
    end
    if opt.border ~= false then
        UI.setColor(opt.borderColor or Theme.color.borderSoft)
        g.setLineWidth(opt.borderWidth or 1)
        UI.roundRect('line', x + 0.5, y + 0.5, w - 1, h - 1, opt.radius or 10)
    end
end

function UI.shadow(x, y, w, h, r)
    g.setColor(0, 0, 0, 0.35)
    g.rectangle('fill', x + 3, y + 5, w, h, r or 10, r or 10)
end

function UI.clip(x, y, w, h)
    local sx, sy = Scale.toScreen(x, y)
    local sw, sh = w * Scale.s, h * Scale.s
    local gx, gy, gw, gh = x, y, w, h
    local prev = UI.clipStack[#UI.clipStack]
    if prev then
        -- interseção com o clip anterior
        local x1 = math.max(prev.sx, sx)
        local y1 = math.max(prev.sy, sy)
        local x2 = math.min(prev.sx + prev.sw, sx + sw)
        local y2 = math.min(prev.sy + prev.sh, sy + sh)
        sx, sy = x1, y1
        sw, sh = math.max(0, x2 - x1), math.max(0, y2 - y1)
        local gx1 = math.max(prev.gx, x)
        local gy1 = math.max(prev.gy, y)
        local gx2 = math.min(prev.gx + prev.gw, x + w)
        local gy2 = math.min(prev.gy + prev.gh, y + h)
        gx, gy, gw, gh = gx1, gy1, math.max(0, gx2 - gx1), math.max(0, gy2 - gy1)
    end
    UI.clipStack[#UI.clipStack + 1] = { sx = sx, sy = sy, sw = sw, sh = sh, gx = gx, gy = gy, gw = gw, gh = gh }
    g.setScissor(sx, sy, sw, sh)
end

function UI.unclip()
    UI.clipStack[#UI.clipStack] = nil
    local prev = UI.clipStack[#UI.clipStack]
    if prev then
        g.setScissor(prev.sx, prev.sy, prev.sw, prev.sh)
    else
        g.setScissor()
    end
end

-- ───────────────────────────────────────────────────────────────── input
function UI.frame(dt)
    UI.time = UI.time + dt
    local mx, my = love.mouse.getPosition()
    UI.mx, UI.my = Scale.toGame(mx, my)
    UI.down = love.mouse.isDown(1)
    UI.blocked = UI.modal ~= nil
    for i = #UI.toasts, 1, -1 do
        UI.toasts[i].t = UI.toasts[i].t - dt
        if UI.toasts[i].t <= 0 then table.remove(UI.toasts, i) end
    end
    UI.tooltipData = nil
end

function UI.endFrame()
    UI.pressed = false
    UI.pressedButton = nil
    UI.released = false
    UI.releasedButton = nil
    UI.wheel = 0
end

function UI.hit(x, y, w, h)
    local inside = UI.mx >= x and UI.mx <= x + w and UI.my >= y and UI.my <= y + h
    if not inside then return false end
    local c = UI.clipStack[#UI.clipStack]
    if c and c.gw > 0 and c.gh > 0 then
        return UI.mx >= c.gx and UI.mx <= c.gx + c.gw and UI.my >= c.gy and UI.my <= c.gy + c.gh
    end
    return true
end

function UI.hover(x, y, w, h)
    return not UI.blocked and UI.hit(x, y, w, h)
end

function UI.clicked(x, y, w, h)
    return UI.hover(x, y, w, h) and UI.pressed and UI.pressedButton == 1
end

function UI.consumeClick()
    UI.pressed = false
    UI.pressedButton = nil
end

function UI.mousepressed(x, y, button)
    local gx, gy = Scale.toGame(x, y)
    UI.mx, UI.my = gx, gy
    UI.pressed = true
    UI.pressedButton = button
    UI.down = true
end

function UI.mousereleased(x, y, button)
    local gx, gy = Scale.toGame(x, y)
    UI.mx, UI.my = gx, gy
    UI.released = true
    UI.releasedButton = button
    UI.down = false
end

function UI.wheelmoved(dx, dy)
    UI.wheel = UI.wheel + dy
end

function UI.keypressed(key)
    if key == 'escape' then
        if UI.focus then
            UI.focus = nil
            return true
        end
        if UI.modal and UI.modal.closable ~= false then
            UI.closeModal()
            return true
        end
    end
    if UI.focus then
        local buf = UI.input[UI.focus]
        if buf then
            if key == 'backspace' then
                local chars = U.utf8chars(buf)
                table.remove(chars)
                UI.input[UI.focus] = table.concat(chars)
                return true
            elseif key == 'return' or key == 'kpenter' then
                UI.submitted[UI.focus] = true
                UI.focus = nil
                return true
            end
        end
    end
    return false
end

function UI.textinput(t)
    if UI.focus and UI.input[UI.focus] then
        local max = UI.inputMax[UI.focus] or 40
        if #U.utf8chars(UI.input[UI.focus]) < max then
            UI.input[UI.focus] = UI.input[UI.focus] .. t
        end
    end
end

-- ───────────────────────────────────────────────────────────────── widgets
local STYLE = {
    default = { Theme.color.purple, Theme.color.purple2 },
    success = { Theme.color.green, Theme.color.greenDark },
    danger  = { Theme.color.red, Theme.color.redDark },
    warning = { Theme.color.orange, Theme.color.orangeDark },
    gold    = { Theme.color.gold, Theme.color.goldDark },
    blue    = { Theme.color.blue, { 0.18, 0.36, 0.62, 1 } },
    ghost   = { { 0.20, 0.18, 0.30, 1 }, { 0.14, 0.12, 0.22, 1 } },
}

function UI.button(id, x, y, w, h, label, opt)
    opt = opt or {}
    local enabled = opt.enabled ~= false
    local hover = enabled and UI.hover(x, y, w, h)
    local col = STYLE[opt.style or 'default'] or STYLE.default
    local c1, c2 = col[1], col[2]
    if hover then
        c1 = Theme.mix(c1, { 1, 1, 1, 1 }, 0.12)
        c2 = Theme.mix(c2, { 1, 1, 1, 1 }, 0.10)
    end
    if not enabled then
        c1 = { 0.20, 0.19, 0.26, 1 }
        c2 = { 0.15, 0.14, 0.20, 1 }
    end
    local radius = opt.radius or math.min(9, h * 0.35)

    -- sombra + corpo
    g.setColor(0, 0, 0, enabled and 0.28 or 0.12)
    g.rectangle('fill', x + 1, y + 2, w, h, radius, radius)
    UI.setColor(c2)
    g.rectangle('fill', x, y, w, h, radius, radius)
    UI.setColor(c1)
    g.rectangle('fill', x, y, w, h - 2, radius, radius)
    -- brilho superior
    g.setColor(1, 1, 1, enabled and 0.10 or 0.03)
    g.rectangle('fill', x + 2, y + 1, w - 4, math.min(h * 0.4, 12), radius, radius)
    if opt.border ~= false then
        g.setColor(1, 1, 1, enabled and 0.14 or 0.05)
        g.setLineWidth(1)
        g.rectangle('line', x + 0.5, y + 0.5, w - 1, h - 1, radius, radius)
    end

    local font = opt.font or Theme.font.base
    local labelClean = Text.clean(label)
    local textColor = opt.color or (enabled and Theme.color.white or Theme.color.dim)
    local sub = opt.sub
    if sub then
        Text.draw(font, labelClean, x + 6, y + h * 0.5 - font:getHeight() * 0.95, w - 12, 'center', textColor, 1.1)
        Text.draw(Theme.font.xs, sub, x + 6, y + h * 0.5 + 2, w - 12, 'center', Theme.color.muted, 1.1)
    else
        Text.draw(font, labelClean, x + 6, y + (h - font:getHeight()) * 0.5 - 1, w - 12, 'center', textColor, 1.0)
    end

    local clicked = hover and UI.pressed and UI.pressedButton == 1
    if clicked then
        UI.consumeClick()
        if opt.onClick then opt.onClick() end
    end
    return clicked
end

function UI.label(text, x, y, opt)
    opt = opt or {}
    local font = opt.font or Theme.font.base
    Text.draw(font, text, x, y, opt.w or 1000, opt.align or 'left', opt.color or Theme.color.text, opt.lineHeight)
    return font:getHeight()
end

function UI.paragraph(text, x, y, w, opt)
    opt = opt or {}
    local font = opt.font or Theme.font.base
    local lh = opt.lineHeight or 1.35
    local h = Text.height(font, text, w, lh)
    Text.draw(font, text, x, y, w, opt.align or 'left', opt.color or Theme.color.text, lh)
    return h
end

function UI.bar(x, y, w, h, pct, color, opt)
    opt = opt or {}
    pct = U.clamp(pct or 0, 0, 1)
    g.setColor(0, 0, 0, 0.45)
    g.rectangle('fill', x, y, w, h, h * 0.5, h * 0.5)
    if pct > 0 then
        UI.setColor(color or Theme.color.green)
        g.rectangle('fill', x + 1, y + 1, math.max(2, (w - 2) * pct), h - 2, (h - 2) * 0.5, (h - 2) * 0.5)
        g.setColor(1, 1, 1, 0.18)
        g.rectangle('fill', x + 2, y + 1, math.max(1, (w - 4) * pct), math.max(1, (h - 2) * 0.4), 3, 3)
    end
    g.setColor(1, 1, 1, 0.10)
    g.setLineWidth(1)
    g.rectangle('line', x + 0.5, y + 0.5, w - 1, h - 1, h * 0.5, h * 0.5)
    if opt.label then
        local font = opt.font or Theme.font.xs
        Text.draw(font, opt.label, x, y + (h - font:getHeight()) * 0.5 - 1, w, 'center', opt.labelColor or Theme.color.white)
    end
end

function UI.divider(x, y, w, alpha)
    g.setColor(1, 1, 1, alpha or 0.07)
    g.setLineWidth(1)
    g.line(x, y + 0.5, x + w, y + 0.5)
end

-- Gradiente vertical simples (bandas), usado nos fundos das telas.
function UI.vgradient(x, y, w, h, c1, c2, steps)
    steps = steps or 48
    for i = 0, steps - 1 do
        local t = i / (steps - 1)
        local c = Theme.mix(c1, c2, t)
        g.setColor(c[1], c[2], c[3], (c[4] or 1))
        local bandY = y + (h / steps) * i
        g.rectangle('fill', x, bandY, w, (h / steps) + 1)
    end
end

function UI.circleFill(x, y, r, color)
    UI.setColor(color)
    g.circle('fill', x, y, r)
end

function UI.circleLine(x, y, r, color, width)
    UI.setColor(color)
    g.setLineWidth(width or 1)
    g.circle('line', x, y, r)
end


function UI.tooltip(text)
    if text and text ~= '' then
        UI.tooltipData = { text = text }
    end
end

function UI.textInput(id, x, y, w, h, value, opt)
    opt = opt or {}
    UI.inputMax[id] = opt.max or 40
    if UI.input[id] == nil then UI.input[id] = value or '' end
    local buf = UI.input[id]
    local hover = UI.hover(x, y, w, h)
    if hover and UI.pressed and UI.pressedButton == 1 then
        UI.consumeClick()
        UI.focus = id
        UI.input[id] = buf
    end
    local focused = UI.focus == id

    g.setColor(0, 0, 0, focused and 0.55 or 0.35)
    g.rectangle('fill', x, y, w, h, 8, 8)
    g.setColor(focused and Theme.color.purple[1] or 1, focused and Theme.color.purple[2] or 1, focused and Theme.color.purple[3] or 1, focused and 0.9 or 0.20)
    g.setLineWidth(focused and 1.5 or 1)
    g.rectangle('line', x + 0.5, y + 0.5, w - 1, h - 1, 8, 8)

    local font = opt.font or Theme.font.md
    local shown = Text.clean(buf)
    if shown == '' and not focused and opt.placeholder then
        shown = opt.placeholder
        Text.draw(font, shown, x + 12, y + (h - font:getHeight()) * 0.5, w - 24, 'left', Theme.color.dim)
    else
        Text.draw(font, shown, x + 12, y + (h - font:getHeight()) * 0.5, w - 24, 'left', Theme.color.text)
    end
    if focused and math.floor(UI.time * 2) % 2 == 0 then
        local tw = math.min(font:getWidth(shown), w - 24)
        g.setColor(Theme.color.gold)
        g.rectangle('fill', x + 12 + tw + 1, y + 8, 1.5, h - 16)
    end
    return buf, UI.submitted[id]
end

function UI.clearSubmitted(id)
    UI.submitted[id] = nil
end

-- Área com scroll: drawFn(x, y, w) desenha e retorna a altura do conteúdo.
function UI.scroll(id, x, y, w, h, drawFn, opt)
    opt = opt or {}
    local hover = UI.hover(x, y, w, h)
    local off = UI.scrollOffsets[id] or 0
    local contentH = UI.scrollHeights[id] or h

    if hover and UI.wheel ~= 0 then
        off = off - UI.wheel * (opt.speed or 48)
        UI.wheel = 0
    end
    local maxOff = math.max(0, contentH - h)
    off = U.clamp(off, 0, maxOff)

    UI.clip(x, y, w, h)
    local measured = drawFn(x, y - off, w)
    UI.unclip()
    UI.scrollHeights[id] = measured or contentH
    contentH = UI.scrollHeights[id]
    maxOff = math.max(0, contentH - h)
    off = U.clamp(off, 0, maxOff)
    UI.scrollOffsets[id] = off

    if contentH > h + 1 then
        local trackX = x + w - 6
        local trackY = y + 4
        local trackH = h - 8
        g.setColor(1, 1, 1, 0.05)
        g.rectangle('fill', trackX, trackY, 4, trackH, 2, 2)
        local ratio = h / contentH
        local thumbH = math.max(24, trackH * ratio)
        local thumbY = trackY + (trackH - thumbH) * (off / maxOff)
        g.setColor(Theme.color.purple[1], Theme.color.purple[2], Theme.color.purple[3], 0.75)
        g.rectangle('fill', trackX, thumbY, 4, thumbH, 2, 2)
        -- arrastar a barra
        if hover and UI.pressed and UI.mx >= trackX - 4 and UI.mx <= trackX + 8 then
            local rel = U.clamp((UI.my - trackY - thumbH * 0.5) / (trackH - thumbH), 0, 1)
            UI.scrollOffsets[id] = rel * maxOff
            UI.consumeClick()
        end
    end
    return off
end

function UI.scrollTo(id, v)
    UI.scrollOffsets[id] = v
end

-- ───────────────────────────────────────────────────────────────── modais
function UI.openModal(spec)
    spec = spec or {}
    UI.modal = {
        title = spec.title or '',
        icon = spec.icon,
        kind = spec.kind,
        data = spec.data,
        body = spec.body,
        buttons = spec.buttons or {},
        closable = spec.closable ~= false,
        width = spec.width or 760,
        height = spec.height or 520,
        onClose = spec.onClose,
        scrollId = spec.scrollId or ('modal_' .. tostring(spec.title)),
        padding = spec.padding or 22,
    }
    UI.blocked = true
end

function UI.closeModal()
    if not UI.modal then return end
    local m = UI.modal
    UI.modal = nil
    UI.blocked = false
    UI.focus = nil
    if m.onClose then m.onClose() end
    if UI.onModalClose then UI.onModalClose() end
end

function UI.modalOpen()
    return UI.modal ~= nil
end

function UI.drawModal()
    local m = UI.modal
    if not m then return end
    -- A tela de trás já foi desenhada neste frame com UI.blocked = true.
    -- Liberamos os widgets daqui para baixo para o próprio modal responder.
    UI.blocked = false
    g.setColor(0, 0, 0, 0.72)
    g.rectangle('fill', 0, 0, 1280, 720)

    local w = math.min(m.width, 1180)
    local h = math.min(m.height, 660)
    local x = (1280 - w) * 0.5
    local y = (720 - h) * 0.5

    UI.shadow(x, y, w, h, 14)
    UI.panel(x, y, w, h, { color = Theme.color.panel, radius = 14, borderColor = Theme.color.border })
    -- faixa superior
    g.setColor(Theme.color.purple[1], Theme.color.purple[2], Theme.color.purple[3], 0.18)
    g.rectangle('fill', x, y, w, 52, 14, 14)
    g.rectangle('fill', x, y + 30, w, 22)

    local titleX = x + 22
    if m.icon then
        Text.draw(Theme.font.lg, m.icon, x + 20, y + 13, 40, 'left', Theme.color.gold)
        titleX = x + 46
    end
    Text.draw(Theme.font.boldMd, m.title, titleX, y + 16, w - 90, 'left', Theme.color.gold)

    -- botão fechar
    local closeX = x + w - 44
    if m.closable then
        if UI.button('modal_close', closeX, y + 12, 30, 28, 'X', { style = 'ghost', font = Theme.font.bold }) then
            UI.closeModal()
            return
        end
    end

    local bodyY = y + 64
    local bodyH = h - 64 - (m.buttons and #m.buttons > 0 and 62 or 14)
    local bodyX = x + m.padding
    local bodyW = w - m.padding * 2

    if m.body then
        UI.clip(bodyX, bodyY, bodyW, bodyH)
        local contentH = m.body(bodyX, bodyY, bodyW, bodyH)
        UI.unclip()
        m._contentH = contentH or bodyH
    end

    if m.buttons and #m.buttons > 0 then
        local bx = x + m.padding
        local by = y + h - 52
        local bw = (bodyW - (#m.buttons - 1) * 10) / #m.buttons
        for i, b in ipairs(m.buttons) do
            local style = b.style or (i == #m.buttons and 'success' or 'ghost')
            if UI.button('modal_btn_' .. i, bx + (i - 1) * (bw + 10), by, bw, 38, b.text, {
                style = style, enabled = b.enabled ~= false,
                onClick = function()
                    if b.close ~= false then UI.closeModal() end
                    if b.onClick then b.onClick() end
                end
            }) and b.keepOpen then
                -- mantém aberto (o onClick já tratou)
            end
        end
    end
end

function UI.toast(text, duration)
    if not text or text == '' then return end
    UI.toasts[#UI.toasts + 1] = { text = text, t = duration or 3.2, max = duration or 3.2 }
    if #UI.toasts > 6 then table.remove(UI.toasts, 1) end
end

function UI.drawToasts()
    local x = 1280 - 344
    local y = 14
    for i = #UI.toasts, 1, -1 do
        local to = UI.toasts[i]
        local alpha = U.clamp(to.t / math.min(0.4, to.max), 0, 1)
        local lines = Text.wrap(Theme.font.sm, to.text, 300)
        local h = math.max(40, #lines * Theme.font.sm:getHeight() * 1.25 + 18)
        g.setColor(0, 0, 0, 0.45 * alpha)
        g.rectangle('fill', x + 2, y + 2, 330, h, 8, 8)
        g.setColor(0.10, 0.09, 0.17, 0.97 * alpha)
        g.rectangle('fill', x, y, 330, h, 8, 8)
        g.setColor(Theme.color.purple[1], Theme.color.purple[2], Theme.color.purple[3], 0.65 * alpha)
        g.setLineWidth(1)
        g.rectangle('line', x + 0.5, y + 0.5, 329, h - 1, 8, 8)
        g.setColor(Theme.color.gold[1], Theme.color.gold[2], Theme.color.gold[3], alpha)
        g.rectangle('fill', x, y + 6, 3, h - 12, 2, 2)
        Text.draw(Theme.font.sm, to.text, x + 14, y + 9, 300, 'left',
            { Theme.color.text[1], Theme.color.text[2], Theme.color.text[3], alpha }, 1.25)
        y = y + h + 8
    end
end

function UI.drawTooltip()
    if not UI.tooltipData or UI.blocked and not UI.modal then return end
    local text = UI.tooltipData.text
    local font = Theme.font.sm
    local maxW = 300
    local lines = Text.wrap(font, text, maxW - 20)
    local w = 0
    for _, l in ipairs(lines) do w = math.max(w, font:getWidth(l)) end
    w = math.min(maxW, w + 20)
    local h = #lines * font:getHeight() * 1.3 + 14
    local x = UI.mx + 16
    local y = UI.my + 18
    if x + w > 1276 then x = UI.mx - w - 10 end
    if y + h > 716 then y = 716 - h end
    g.setColor(0, 0, 0, 0.9)
    g.rectangle('fill', x, y, w, h, 7, 7)
    g.setColor(Theme.color.gold[1], Theme.color.gold[2], Theme.color.gold[3], 0.5)
    g.setLineWidth(1)
    g.rectangle('line', x + 0.5, y + 0.5, w - 1, h - 1, 7, 7)
    Text.draw(font, text, x + 10, y + 7, w - 20, 'left', Theme.color.text, 1.3)
end

function UI.title(text, x, y, w, color)
    Text.draw(Theme.font.boldLg, text, x, y, w, 'left', color or Theme.color.gold)
end

function UI.iconButton(id, x, y, size, label, opt)
    return UI.button(id, x, y, size, size, label, opt)
end

return UI
