-- Texto: limpeza de emojis, medição, quebra e desenho.
-- O jogo original usa emojis como ícones; a fonte DejaVu (empacotada) não
-- tem glifos de emoji, então eles são removidos na renderização. A pontuação
-- latina, acentos, setas e símbolos matemáticos continuam funcionando.
local U = require('src.core.util')

local Text = {}

local DROP_RANGES = {
    { 0x1F000, 0x1FAFF }, -- emoji / pictogramas
    { 0x2600, 0x27BF },   -- símbolos diversos + dingbats
    { 0x2B00, 0x2BFF },   -- setas/símbolos extras
    { 0x2300, 0x23FF },   -- relógio, etc.
    { 0xFE00, 0xFE0F },   -- variation selectors
    { 0x200D, 0x200D },   -- zero width joiner
    { 0x20E3, 0x20E3 },   -- combining keycap
    { 0xE000, 0xF8FF },   -- private use
    { 0x1F1E6, 0x1F1FF }, -- bandeiras
    { 0x3030, 0x3030 },
    { 0x303D, 0x303D },
    { 0x3297, 0x3299 },
}

local function dropped(cp)
    for _, r in ipairs(DROP_RANGES) do
        if cp >= r[1] and cp <= r[2] then return true end
    end
    return false
end

local cache = {}

function Text.clean(s)
    s = tostring(s or '')
    local hit = cache[s]
    if hit then return hit end
    local out = {}
    for _, ch in ipairs(U.utf8chars(s)) do
        local cp = U.codepoint(ch)
        if cp == 0x00A0 then
            out[#out + 1] = ' '
        elseif cp == 0x2028 or cp == 0x2029 then
            out[#out + 1] = ' '
        elseif not dropped(cp) then
            out[#out + 1] = ch
        end
    end
    local res = table.concat(out)
    res = res:gsub('[ \t]+', ' '):gsub('^%s+', ''):gsub('%s+$', '')
    res = res:gsub('%s+([,.;:!?%)])', '%1')
    cache[s] = res
    return res
end

-- Limpa mas preserva quebras de linha explícitas.
function Text.cleanLines(s)
    local parts = {}
    for line in tostring(s or ''):gmatch('[^\n]+') do
        parts[#parts + 1] = Text.clean(line)
    end
    return table.concat(parts, '\n')
end

function Text.width(font, s)
    return font:getWidth(Text.clean(s))
end

function Text.wrap(font, s, limit)
    s = Text.cleanLines(s)
    local _, lines = font:getWrap(s, limit)
    return lines
end

function Text.height(font, s, limit, lineHeight)
    local lines = Text.wrap(font, s, limit)
    return #lines * font:getHeight() * (lineHeight or 1.25)
end

function Text.draw(font, s, x, y, limit, align, color, lineHeight)
    love.graphics.setFont(font)
    if color then love.graphics.setColor(color) end
    love.graphics.printf(Text.cleanLines(s), x, y, limit, align or 'left', 0, lineHeight or 1.25)
end

function Text.drawRaw(font, s, x, y, color)
    love.graphics.setFont(font)
    if color then love.graphics.setColor(color) end
    love.graphics.print(s, x, y)
end

return Text
