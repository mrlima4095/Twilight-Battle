-- Tema visual: paleta do site original + fontes empacotadas.
local Theme = {}

Theme.color = {
    bg          = { 0.055, 0.047, 0.098, 1 },   -- #0e0c19
    bg2         = { 0.086, 0.078, 0.137, 1 },   -- #161423
    panel       = { 0.102, 0.102, 0.180, 0.97 },-- #1a1a2e
    panelAlt    = { 0.139, 0.119, 0.216, 1 },   -- #231e37
    panelHi     = { 0.190, 0.153, 0.302, 1 },
    border      = { 0.400, 0.494, 0.918, 0.35 },-- #667eea
    borderSoft  = { 1, 1, 1, 0.08 },
    text        = { 0.925, 0.918, 0.961, 1 },
    muted       = { 0.639, 0.608, 0.722, 1 },   -- #a39bb8
    dim         = { 0.443, 0.412, 0.537, 1 },
    gold        = { 1, 0.843, 0, 1 },           -- #ffd700
    goldDark    = { 0.647, 0.533, 0, 1 },
    purple      = { 0.400, 0.494, 0.918, 1 },   -- #667eea
    purple2     = { 0.463, 0.290, 0.635, 1 },   -- #764ba2
    green       = { 0.298, 0.686, 0.314, 1 },   -- #4CAF50
    greenDark   = { 0.243, 0.549, 0.251, 1 },
    red         = { 1, 0.267, 0.267, 1 },       -- #ff4444
    redDark     = { 0.690, 0.149, 0.149, 1 },
    orange      = { 1, 0.647, 0.239, 1 },       -- #ffa53d
    orangeDark  = { 0.756, 0.451, 0.086, 1 },
    blue        = { 0.290, 0.565, 0.886, 1 },   -- #4a90e2
    cyan        = { 0.290, 0.851, 0.851, 1 },
    pink        = { 0.925, 0.478, 0.690, 1 },
    black       = { 0, 0, 0, 1 },
    white       = { 1, 1, 1, 1 },
    shadow      = { 0, 0, 0, 0.45 },
    hp          = { 0.851, 0.263, 0.263, 1 },
    mana        = { 0.290, 0.565, 0.886, 1 },
    hunger      = { 1, 0.647, 0.239, 1 },
    thirst      = { 0.290, 0.788, 0.918, 1 },
    sanity      = { 0.725, 0.478, 0.925, 1 },
}

Theme.font = {}

function Theme.load()
    local dir = 'assets/fonts/'
    local function f(name, size)
        local ok, font = pcall(love.graphics.newFont, dir .. name, size)
        if ok then return font end
        return love.graphics.newFont(size)
    end
    Theme.font.xs    = f('DejaVuSans.ttf', 11)
    Theme.font.sm    = f('DejaVuSans.ttf', 12)
    Theme.font.base  = f('DejaVuSans.ttf', 14)
    Theme.font.md    = f('DejaVuSans.ttf', 16)
    Theme.font.lg    = f('DejaVuSans.ttf', 19)
    Theme.font.xl    = f('DejaVuSans.ttf', 24)
    Theme.font.title = f('DejaVuSans-Bold.ttf', 46)
    Theme.font.bold  = f('DejaVuSans-Bold.ttf', 14)
    Theme.font.boldMd = f('DejaVuSans-Bold.ttf', 16)
    Theme.font.boldLg = f('DejaVuSans-Bold.ttf', 20)
    Theme.font.mono  = f('DejaVuSansMono.ttf', 13)
    Theme.font.monoSm = f('DejaVuSansMono.ttf', 11)

    -- Alturas de linha padronizadas por tamanho.
    Theme.line = {
        xs = Theme.font.xs:getHeight() * 1.25,
        sm = Theme.font.sm:getHeight() * 1.25,
        base = Theme.font.base:getHeight() * 1.25,
        md = Theme.font.md:getHeight() * 1.3,
        lg = Theme.font.lg:getHeight() * 1.3,
        xl = Theme.font.xl:getHeight() * 1.25,
    }
end

function Theme.set(color, alpha)
    love.graphics.setColor(color[1], color[2], color[3], alpha or color[4] or 1)
end

function Theme.fade(color, a)
    return { color[1], color[2], color[3], (color[4] or 1) * a }
end

function Theme.mix(a, b, t)
    return {
        a[1] + (b[1] - a[1]) * t,
        a[2] + (b[2] - a[2]) * t,
        a[3] + (b[3] - a[3]) * t,
        (a[4] or 1) + ((b[4] or 1) - (a[4] or 1)) * t,
    }
end

return Theme
