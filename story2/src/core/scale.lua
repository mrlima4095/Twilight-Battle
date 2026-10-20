-- Escala: resolução virtual 1280x720 com letterbox.
local Scale = {
    W = 1280,
    H = 720,
    s = 1,
    ox = 0,
    oy = 0,
}

function Scale.update()
    local w, h = love.graphics.getDimensions()
    Scale.s = math.min(w / Scale.W, h / Scale.H)
    Scale.ox = (w - Scale.W * Scale.s) * 0.5
    Scale.oy = (h - Scale.H * Scale.s) * 0.5
end

function Scale.toGame(x, y)
    return (x - Scale.ox) / Scale.s, (y - Scale.oy) / Scale.s
end

function Scale.toScreen(x, y)
    return x * Scale.s + Scale.ox, y * Scale.s + Scale.oy
end

function Scale.push()
    love.graphics.push()
    love.graphics.translate(Scale.ox, Scale.oy)
    love.graphics.scale(Scale.s, Scale.s)
end

function Scale.pop()
    love.graphics.pop()
end

return Scale
