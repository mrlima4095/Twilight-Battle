-- Twilight Battle — Modo História (port LÖVE2D)
-- Configuração da janela. Resolução virtual: 1280x720 (escala automática).
function love.conf(t)
    t.identity = 'twilight-story2'
    t.version = '11.4'
    t.console = false

    t.window.title = 'Twilight Battle — Modo História'
    t.window.width = 1280
    t.window.height = 720
    t.window.minwidth = 900
    t.window.minheight = 560
    t.window.resizable = true
    t.window.vsync = 1
    t.window.msaa = 2
    t.window.highdpi = true

    t.modules.joystick = false
    t.modules.physics = false
    t.modules.video = false
end
