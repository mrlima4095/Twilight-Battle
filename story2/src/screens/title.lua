-- Tela-título.
local UI = require('src.core.ui')
local Theme = require('src.core.theme')
local Text = require('src.core.text')
local State = require('src.game.state')
local Manager = require('src.screens.manager')

local Title = {}

Title.t = 0
local stars = nil

local function initStars()
    stars = {}
    local rnd = love.math.random
    for i = 1, 140 do
        stars[i] = {
            x = rnd() * 1280,
            y = rnd() * 460,
            r = 0.6 + rnd() * 1.6,
            ph = rnd() * math.pi * 2,
            sp = 0.4 + rnd() * 1.6,
        }
    end
end

function Title.enter()
    Title.t = 0
    if not stars then initStars() end
end

function Title.update(dt)
    Title.t = Title.t + dt
end

function Title.draw()
    local g = love.graphics
    UI.vgradient(0, 0, 1280, 720, { 0.035, 0.03, 0.075, 1 }, { 0.10, 0.06, 0.16, 1 }, 60)

    -- estrelas
    for _, s in ipairs(stars) do
        local a = 0.35 + 0.45 * (0.5 + 0.5 * math.sin(Title.t * s.sp + s.ph))
        g.setColor(0.85, 0.87, 1, a)
        g.circle('fill', s.x, s.y, s.r)
    end

    -- lua
    g.setColor(0.95, 0.92, 0.78, 0.10)
    g.circle('fill', 1010, 150, 96)
    g.setColor(0.96, 0.93, 0.80, 0.95)
    g.circle('fill', 1010, 150, 74)
    g.setColor(0.10, 0.07, 0.16, 0.9)
    g.circle('fill', 1040, 132, 66)

    -- montanhas / silhueta
    g.setColor(0.055, 0.045, 0.10, 1)
    g.polygon('fill', 0, 620, 180, 430, 340, 590, 520, 390, 700, 600, 880, 440, 1080, 610, 1280, 470, 1280, 720, 0, 720)
    g.setColor(0.075, 0.06, 0.13, 1)
    g.polygon('fill', 0, 660, 220, 540, 420, 650, 640, 520, 860, 670, 1100, 560, 1280, 660, 1280, 720, 0, 720)

    -- castelo distante
    g.setColor(0.10, 0.08, 0.17, 1)
    g.rectangle('fill', 840, 500, 130, 130)
    g.rectangle('fill', 860, 460, 34, 60)
    g.rectangle('fill', 916, 470, 34, 50)
    g.polygon('fill', 855, 460, 877, 425, 899, 460)
    g.polygon('fill', 911, 470, 933, 440, 955, 470)
    g.setColor(Theme.color.gold[1], Theme.color.gold[2], Theme.color.gold[3], 0.75)
    g.rectangle('fill', 874, 520, 12, 18)
    g.rectangle('fill', 928, 530, 12, 18)

    -- título
    local glow = 0.55 + 0.2 * math.sin(Title.t * 1.3)
    g.setColor(0.4, 0.29, 0.64, 0.28 * glow)
    Text.draw(Theme.font.title, 'TWILIGHT BATTLE', 0, 100, 1280, 'center', { 0.65, 0.45, 1, 0.5 })
    g.setColor(Theme.color.shadow)
    Text.draw(Theme.font.title, 'TWILIGHT BATTLE', 3, 103, 1280, 'center', Theme.color.shadow)
    Text.draw(Theme.font.title, 'TWILIGHT BATTLE', 0, 100, 1280, 'center', Theme.color.gold)
    Text.draw(Theme.font.lg, 'Modo História', 0, 162, 1280, 'center', Theme.color.text)
    Text.draw(Theme.font.sm, 'Um reino entre a aurora e o crepúsculo — port LÖVE2D', 0, 192, 1280, 'center', Theme.color.muted)

    -- botões
    local bw, bh = 320, 52
    local bx = (1280 - bw) * 0.5
    local by = 300
    local hasSave = State.hasSave()
    if UI.button('title_continue', bx, by, bw, bh, 'Continuar jornada', {
        style = 'gold', enabled = hasSave,
        sub = hasSave and 'Retomar o save local' or 'Nenhum save encontrado',
        onClick = function()
            local ok, err = State.load()
            if ok then
                State.addLog('💾 Jornada carregada.')
                Manager.set('game')
            else
                UI.toast('❌ ' .. tostring(err))
            end
        end,
    }) then end

    if UI.button('title_new', bx, by + 64, bw, bh, 'Nova jornada', {
        style = 'default', sub = 'Criar um personagem',
        onClick = function() Manager.set('creation') end,
    }) then end

    if UI.button('title_quit', bx, by + 128, bw, 44, 'Sair', {
        style = 'ghost',
        onClick = function() love.event.quit() end,
    }) then end

    Text.draw(Theme.font.xs, 'Dica: F11 alterna tela cheia · Esc fecha modais', 0, 684, 1280, 'center', Theme.color.dim)
    Text.draw(Theme.font.xs, 'Conteúdo baseado em templates/game/story.html', 0, 700, 1280, 'center', Theme.color.dim)
end

function Title.keypressed(key)
    if key == 'return' or key == 'kpenter' then
        if State.hasSave() then
            local ok = State.load()
            if ok then
                State.addLog('💾 Jornada carregada.')
                Manager.set('game')
            end
        else
            Manager.set('creation')
        end
        return true
    end
end

return Title
