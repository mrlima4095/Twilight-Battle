-- Twilight Battle — Modo História (port LÖVE2D)
-- Ponto de entrada: carrega tema, escala, tela-título e delega update/draw.
local UI = require('src.core.ui')
local Theme = require('src.core.theme')
local Scale = require('src.core.scale')
local State = require('src.game.state')
local Manager = require('src.screens.manager')

local function toggleFullscreen()
    love.window.setFullscreen(not love.window.getFullscreen(), 'desktop')
    Scale.update()
end

function love.load()
    love.graphics.setDefaultFilter('linear', 'linear')
    Theme.load()
    Scale.update()
    local seed = os.time()
    math.randomseed(seed)
    if love.math and love.math.setRandomSeed then love.math.setRandomSeed(seed) end
    UI.time = 0
    Manager.set('title')
end

function love.resize()
    Scale.update()
end

function love.update(dt)
    if dt > 0.25 then dt = 0.25 end
    Scale.update()
    UI.frame(dt)
    Manager.update(dt)
end

function love.draw()
    love.graphics.clear(Theme.color.bg[1], Theme.color.bg[2], Theme.color.bg[3], 1)
    Scale.push()
    Manager.draw()
    if UI.modal then UI.drawModal() end
    UI.drawToasts()
    UI.drawTooltip()
    Scale.pop()
    UI.endFrame()
end

function love.mousepressed(x, y, button)
    UI.mousepressed(x, y, button)
end

function love.mousereleased(x, y, button)
    UI.mousereleased(x, y, button)
end

function love.wheelmoved(dx, dy)
    UI.wheelmoved(dx, dy)
end

function love.keypressed(key)
    if key == 'f11' then
        toggleFullscreen()
        return
    end
    if UI.keypressed(key) then return end
    if Manager.keypressed and Manager.keypressed(key) then return end
end

function love.textinput(t)
    UI.textinput(t)
end

function love.focus(focused)
    if not focused and State.G and State.G.character and not State.G.isDead then
        State.save(true)
    end
end

function love.quit()
    State.onQuit()
    return false
end
