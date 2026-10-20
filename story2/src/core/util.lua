-- Utilidades puras (sem love.*), testáveis fora do LÖVE.
local U = {}

function U.clamp(v, lo, hi)
    if v < lo then return lo end
    if v > hi then return hi end
    return v
end

function U.round(v)
    return math.floor(v + 0.5)
end

function U.lerp(a, b, t)
    return a + (b - a) * t
end

function U.sign(v)
    if v < 0 then return -1 elseif v > 0 then return 1 end
    return 0
end

function U.choice(list)
    if not list or #list == 0 then return nil end
    return list[love and love.math.random(#list) or math.random(#list)]
end

function U.shuffle(list)
    local rnd = love and love.math.random or math.random
    for i = #list, 2, -1 do
        local j = rnd(i)
        list[i], list[j] = list[j], list[i]
    end
    return list
end

function U.deepcopy(v, seen)
    if type(v) ~= 'table' then return v end
    seen = seen or {}
    if seen[v] then return seen[v] end
    local out = {}
    seen[v] = out
    for k, val in pairs(v) do
        out[U.deepcopy(k, seen)] = U.deepcopy(val, seen)
    end
    return out
end

function U.merge(dst, src)
    for k, v in pairs(src) do dst[k] = v end
    return dst
end

function U.trim(s)
    return (tostring(s):gsub('^%s+', ''):gsub('%s+$', ''))
end

function U.split(s, sep)
    local out = {}
    local pattern = '([^' .. sep .. ']+)'
    for piece in tostring(s):gmatch(pattern) do out[#out + 1] = piece end
    return out
end

function U.starts(s, prefix)
    return tostring(s):sub(1, #prefix) == prefix
end

function U.fmt(n)
    n = tonumber(n) or 0
    if n >= 1000000 then return string.format('%.1fM', n / 1000000) end
    if n >= 10000 then return string.format('%.1fk', n / 1000) end
    return tostring(math.floor(n))
end

function U.timeHMS(seconds)
    seconds = math.max(0, math.floor(seconds or 0))
    local m = math.floor(seconds / 60)
    local s = seconds % 60
    return string.format('%02d:%02d', m, s)
end

-- UTF-8 (Lua 5.1 / LuaJIT não têm biblioteca utf8).
local byte, char, sub = string.byte, string.char, string.sub

function U.utf8chars(s)
    local out = {}
    s = tostring(s)
    local i, n = 1, #s
    while i <= n do
        local c = byte(s, i)
        local len = 1
        if c >= 0xF0 then len = 4
        elseif c >= 0xE0 then len = 3
        elseif c >= 0xC0 then len = 2 end
        out[#out + 1] = sub(s, i, i + len - 1)
        i = i + len
    end
    return out
end

function U.codepoint(ch)
    local c = byte(ch, 1) or 0
    if c < 0x80 then return c end
    if c < 0xE0 then
        local c2 = byte(ch, 2) or 0
        return (c - 0xC0) * 0x40 + (c2 - 0x80)
    end
    if c < 0xF0 then
        local c2 = byte(ch, 2) or 0
        local c3 = byte(ch, 3) or 0
        return (c - 0xE0) * 0x1000 + (c2 - 0x80) * 0x40 + (c3 - 0x80)
    end
    local c2 = byte(ch, 2) or 0
    local c3 = byte(ch, 3) or 0
    local c4 = byte(ch, 4) or 0
    return (c - 0xF0) * 0x40000 + (c2 - 0x80) * 0x1000 + (c3 - 0x80) * 0x40 + (c4 - 0x80)
end

function U.utf8encode(cp)
    if cp < 0x80 then return char(cp) end
    if cp < 0x800 then
        return char(0xC0 + math.floor(cp / 0x40), 0x80 + cp % 0x40)
    end
    if cp < 0x10000 then
        return char(0xE0 + math.floor(cp / 0x1000),
            0x80 + math.floor(cp / 0x40) % 0x40,
            0x80 + cp % 0x40)
    end
    return char(0xF0 + math.floor(cp / 0x40000),
        0x80 + math.floor(cp / 0x1000) % 0x40,
        0x80 + math.floor(cp / 0x40) % 0x40,
        0x80 + cp % 0x40)
end

return U
