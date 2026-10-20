-- Gerenciador simples de telas.
local Manager = { current = nil, name = nil }

function Manager.set(name, ...)
    local mod = require('src.screens.' .. name)
    local UI = require('src.core.ui')
    if UI.modal then UI.closeModal() end
    Manager.current = mod
    Manager.name = name
    if mod.enter then mod.enter(...) end
end

function Manager.update(dt)
    if Manager.current and Manager.current.update then Manager.current.update(dt) end
end

function Manager.draw()
    if Manager.current and Manager.current.draw then Manager.current.draw() end
end

function Manager.keypressed(key)
    if Manager.current and Manager.current.keypressed then
        return Manager.current.keypressed(key)
    end
end

return Manager
