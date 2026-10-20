-- JSON mínimo (encode/decode) para saves em love.filesystem.
-- Sem dependências externas; funciona em Lua 5.1 / LuaJIT.
local JSON = {}

local function isArray(t)
    local n = 0
    for k in pairs(t) do
        if type(k) ~= 'number' or k < 1 or k ~= math.floor(k) then return false end
        if k > n then n = k end
    end
    for i = 1, n do
        if t[i] == nil then return false end
    end
    return true, n
end

local esc = {
    ['"'] = '\\"', ['\\'] = '\\\\', ['\b'] = '\\b', ['\f'] = '\\f',
    ['\n'] = '\\n', ['\r'] = '\\r', ['\t'] = '\\t',
}

local function encodeString(s)
    s = tostring(s)
    s = s:gsub('[%z\1-\31\\"]', function(c)
        return esc[c] or string.format('\\u%04x', c:byte())
    end)
    return '"' .. s .. '"'
end

local function encodeValue(v, out)
    local t = type(v)
    if v == nil then
        out[#out + 1] = 'null'
    elseif t == 'boolean' then
        out[#out + 1] = v and 'true' or 'false'
    elseif t == 'number' then
        if v ~= v or v == math.huge or v == -math.huge then
            out[#out + 1] = '0'
        elseif v == math.floor(v) and math.abs(v) < 1e15 then
            out[#out + 1] = string.format('%d', v)
        else
            out[#out + 1] = string.format('%.6f', v):gsub('0+$', ''):gsub('%.$', '')
        end
    elseif t == 'string' then
        out[#out + 1] = encodeString(v)
    elseif t == 'table' then
        local arr, n = isArray(v)
        if arr then
            out[#out + 1] = '['
            for i = 1, n do
                if i > 1 then out[#out + 1] = ',' end
                encodeValue(v[i], out)
            end
            out[#out + 1] = ']'
        else
            local keys = {}
            for k in pairs(v) do keys[#keys + 1] = tostring(k) end
            table.sort(keys)
            out[#out + 1] = '{'
            local first = true
            for _, k in ipairs(keys) do
                local val = v[k]
                if val == nil then val = v[tonumber(k)] end
                if val ~= nil then
                    if not first then out[#out + 1] = ',' end
                    first = false
                    out[#out + 1] = encodeString(k)
                    out[#out + 1] = ':'
                    encodeValue(val, out)
                end
            end
            out[#out + 1] = '}'
        end
    else
        out[#out + 1] = 'null'
    end
end

function JSON.encode(value, pretty)
    if not pretty then
        local out = {}
        encodeValue(value, out)
        return table.concat(out)
    end
    -- pretty: indentação simples via pós-processamento do texto compacto.
    local out = {}
    encodeValue(value, out)
    local s = table.concat(out)
    local result, depth, inString, escNext = {}, 0, false, false
    for i = 1, #s do
        local c = s:sub(i, i)
        if inString then
            result[#result + 1] = c
            if escNext then escNext = false
            elseif c == '\\' then escNext = true
            elseif c == '"' then inString = false end
        else
            if c == '"' then
                inString = true
                result[#result + 1] = c
            elseif c == '{' or c == '[' then
                depth = depth + 1
                result[#result + 1] = c .. '\n' .. string.rep('  ', depth)
            elseif c == '}' or c == ']' then
                depth = depth - 1
                result[#result + 1] = '\n' .. string.rep('  ', depth) .. c
            elseif c == ',' then
                result[#result + 1] = ',\n' .. string.rep('  ', depth)
            elseif c == ':' then
                result[#result + 1] = ': '
            else
                result[#result + 1] = c
            end
        end
    end
    return table.concat(result)
end

function JSON.decode(str)
    local pos = 1
    local s = tostring(str):gsub('^%s+', '')
    local function errorAt(msg)
        error(string.format('JSON: %s na posição %d', msg, pos))
    end
    local function skip()
        while true do
            local c = s:sub(pos, pos)
            if c == ' ' or c == '\n' or c == '\r' or c == '\t' then pos = pos + 1 else break end
        end
    end
    local parseValue

    local function parseString()
        pos = pos + 1 -- aspas
        local buf = {}
        while true do
            local c = s:sub(pos, pos)
            if c == '' then errorAt('string sem fim') end
            if c == '"' then pos = pos + 1 break end
            if c == '\\' then
                local e = s:sub(pos + 1, pos + 1)
                local map = { ['"'] = '"', ['\\'] = '\\', ['/'] = '/', b = '\b', f = '\f', n = '\n', r = '\r', t = '\t' }
                if e == 'u' then
                    local hex = s:sub(pos + 2, pos + 5)
                    local cp = tonumber(hex, 16) or 0
                    -- surrogate pair
                    if cp >= 0xD800 and cp <= 0xDBFF then
                        local hex2 = s:sub(pos + 8, pos + 11)
                        local cp2 = tonumber(hex2, 16) or 0
                        cp = 0x10000 + (cp - 0xD800) * 0x400 + (cp2 - 0xDC00)
                        pos = pos + 6
                    end
                    buf[#buf + 1] = require('src.core.util').utf8encode(cp)
                    pos = pos + 6
                else
                    buf[#buf + 1] = map[e] or e
                    pos = pos + 2
                end
            else
                buf[#buf + 1] = c
                pos = pos + 1
            end
        end
        return table.concat(buf)
    end

    local function parseNumber()
        local start = pos
        if s:sub(pos, pos) == '-' then pos = pos + 1 end
        while s:sub(pos, pos):match('%d') do pos = pos + 1 end
        if s:sub(pos, pos) == '.' then
            pos = pos + 1
            while s:sub(pos, pos):match('%d') do pos = pos + 1 end
        end
        local e = s:sub(pos, pos)
        if e == 'e' or e == 'E' then
            pos = pos + 1
            local sign = s:sub(pos, pos)
            if sign == '+' or sign == '-' then pos = pos + 1 end
            while s:sub(pos, pos):match('%d') do pos = pos + 1 end
        end
        return tonumber(s:sub(start, pos - 1))
    end

    function parseValue()
        skip()
        local c = s:sub(pos, pos)
        if c == '{' then
            pos = pos + 1
            local obj = {}
            skip()
            if s:sub(pos, pos) == '}' then pos = pos + 1 return obj end
            while true do
                skip()
                if s:sub(pos, pos) ~= '"' then errorAt('chave esperada') end
                local k = parseString()
                skip()
                if s:sub(pos, pos) ~= ':' then errorAt('":" esperado') end
                pos = pos + 1
                obj[k] = parseValue()
                skip()
                local c2 = s:sub(pos, pos)
                if c2 == ',' then pos = pos + 1
                elseif c2 == '}' then pos = pos + 1 break
                else errorAt('"," ou "}" esperado') end
            end
            return obj
        elseif c == '[' then
            pos = pos + 1
            local arr = {}
            skip()
            if s:sub(pos, pos) == ']' then pos = pos + 1 return arr end
            while true do
                arr[#arr + 1] = parseValue()
                skip()
                local c2 = s:sub(pos, pos)
                if c2 == ',' then pos = pos + 1
                elseif c2 == ']' then pos = pos + 1 break
                else errorAt('"," ou "]" esperado') end
            end
            return arr
        elseif c == '"' then
            return parseString()
        elseif c == 't' and s:sub(pos, pos + 3) == 'true' then
            pos = pos + 4 return true
        elseif c == 'f' and s:sub(pos, pos + 4) == 'false' then
            pos = pos + 5 return false
        elseif c == 'n' and s:sub(pos, pos + 3) == 'null' then
            pos = pos + 4 return nil
        else
            return parseNumber()
        end
    end

    local ok, result = pcall(parseValue)
    if not ok then return nil, result end
    return result
end

return JSON
