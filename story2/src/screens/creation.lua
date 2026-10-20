-- Criação de personagem: nome, raça, gênero, idade e biografia.
local UI = require('src.core.ui')
local Theme = require('src.core.theme')
local Text = require('src.core.text')
local DB = require('src.data.init')
local State = require('src.game.state')
local Manager = require('src.screens.manager')
local U = require('src.core.util')

local Creation = {}

local C = {
    name = '',
    race = nil,
    gender = nil,
    age = 25,
    bio = '',
}

function Creation.enter()
    C.name = ''
    C.race = nil
    C.gender = nil
    C.age = 25
    C.bio = ''
    UI.input['cc_name'] = ''
    UI.input['cc_bio'] = ''
    UI.focus = nil
    C.error = nil
end

function Creation.update(dt) end

local RACE_ORDER = { 'elf', 'wizard', 'centaur', 'nymph' }

local function raceDescription(id)
    local r = DB.races[id]
    if id == 'elf' then
        return 'Ágil e perceptiva. Esquiva-se dos golpes e responde com precisão.'
    elseif id == 'wizard' then
        return 'Mestra das artes arcanas. Possui a maior reserva de mana do reino.'
    elseif id == 'centaur' then
        return 'Guerreiro das planícies. Ataque e defesa elevados, feito para a linha de frente.'
    elseif id == 'nymph' then
        return 'Filha dos bosques. A cura flui naturalmente por suas mãos.'
    end
    return ''
end

local function validate()
    if U.trim(C.name) == '' then return 'Digite um nome para seu personagem!' end
    if not C.race then return 'Selecione uma raça!' end
    if not C.gender then return 'Selecione um gênero!' end
    if not C.age or C.age < 1 or C.age > 1000 then return 'Digite uma idade válida (1–1000)!' end
    return nil
end

function Creation.draw()
    local g = love.graphics
    UI.vgradient(0, 0, 1280, 720, { 0.04, 0.03, 0.08, 1 }, { 0.09, 0.06, 0.14, 1 }, 50)

    local px, py, pw, ph = 80, 42, 1120, 636
    UI.shadow(px, py, pw, ph, 16)
    UI.panel(px, py, pw, ph, { color = Theme.color.panel, radius = 16, borderColor = Theme.color.border })
    g.setColor(Theme.color.purple[1], Theme.color.purple[2], Theme.color.purple[3], 0.16)
    g.rectangle('fill', px, py, pw, 58, 16, 16)
    g.rectangle('fill', px, py + 34, pw, 24)
    Text.draw(Theme.font.boldLg, 'Forje seu destino', px + 26, py + 16, pw - 52, 'left', Theme.color.gold)
    Text.draw(Theme.font.sm, 'Escolha quem você será no Reino da Aurora.', px + 26, py + 42, pw - 52, 'left', Theme.color.muted)

    -- ───────────────────────────── raças (esquerda)
    local lx, ly, lw = px + 24, py + 82, 640
    Text.draw(Theme.font.boldMd, 'Raça', lx, ly, lw, 'left', Theme.color.text)
    local cardW, cardH = 306, 166
    for i, id in ipairs(RACE_ORDER) do
        local race = DB.races[id]
        local col = (i - 1) % 2
        local row = math.floor((i - 1) / 2)
        local x = lx + col * (cardW + 16)
        local y = ly + 28 + row * (cardH + 14)
        local selected = C.race == id
        local hover = UI.hover(x, y, cardW, cardH)
        g.setColor(0, 0, 0, 0.30)
        g.rectangle('fill', x + 2, y + 3, cardW, cardH, 12, 12)
        local bg = selected and { 0.20, 0.16, 0.33, 1 } or (hover and { 0.16, 0.14, 0.25, 1 } or { 0.12, 0.11, 0.20, 1 })
        g.setColor(bg)
        g.rectangle('fill', x, y, cardW, cardH, 12, 12)
        g.setColor(selected and Theme.color.gold[1] or 1, selected and Theme.color.gold[2] or 1, selected and Theme.color.gold[3] or 1, selected and 0.95 or 0.10)
        g.setLineWidth(selected and 2 or 1)
        g.rectangle('line', x + 0.5, y + 0.5, cardW - 1, cardH - 1, 12, 12)

        g.setColor(Theme.color.purple[1], Theme.color.purple[2], Theme.color.purple[3], selected and 0.28 or 0.14)
        g.circle('fill', x + 42, y + 42, 24)
        Text.draw(Theme.font.lg, (race.name or ''):sub(1, 1), x + 22, y + 29, 40, 'center', Theme.color.gold)

        Text.draw(Theme.font.boldMd, race.name, x + 76, y + 22, cardW - 90, 'left', Theme.color.text)
        Text.draw(Theme.font.xs, string.format('Vida %d · Mana %d', race.baseLife, race.mana), x + 76, y + 46, cardW - 90, 'left', Theme.color.muted)
        Text.draw(Theme.font.xs, string.format('Ataque %d · Defesa %d', race.baseAttack, race.baseDefense), x + 76, y + 63, cardW - 90, 'left', Theme.color.muted)
        Text.draw(Theme.font.xs, 'Habilidade: ' .. (race.skill or ''), x + 76, y + 80, cardW - 90, 'left', Theme.color.gold)
        Text.draw(Theme.font.xs, raceDescription(id), x + 16, y + 105, cardW - 32, 'left', Theme.color.muted, 1.25)

        if hover and UI.pressed and UI.pressedButton == 1 then
            C.race = id
            UI.consumeClick()
        end
    end

    -- ───────────────────────────── formulário (direita)
    local rx = px + 700
    local rw = 396
    local ry = py + 82
    Text.draw(Theme.font.boldMd, 'Identidade', rx, ry, rw, 'left', Theme.color.text)

    Text.draw(Theme.font.xs, 'Nome', rx, ry + 28, rw, 'left', Theme.color.muted)
    local name = UI.textInput('cc_name', rx, ry + 44, rw, 42, C.name, { placeholder = 'Como o mundo te chamará...' })
    C.name = name

    Text.draw(Theme.font.xs, 'Idade', rx, ry + 100, rw, 'left', Theme.color.muted)
    if UI.button('cc_age_minus', rx, ry + 116, 44, 40, '−', { style = 'ghost', font = Theme.font.lg }) then
        C.age = math.max(1, C.age - 1)
    end
    g.setColor(0, 0, 0, 0.35)
    g.rectangle('fill', rx + 52, ry + 116, rw - 104, 40, 8, 8)
    Text.draw(Theme.font.md, tostring(C.age), rx + 52, ry + 124, rw - 104, 'center', Theme.color.text)
    if UI.button('cc_age_plus', rx + rw - 44, ry + 116, 44, 40, '+', { style = 'ghost', font = Theme.font.lg }) then
        C.age = math.min(1000, C.age + 1)
    end

    Text.draw(Theme.font.xs, 'Gênero', rx, ry + 172, rw, 'left', Theme.color.muted)
    local gw = (rw - 12) * 0.5
    if UI.button('cc_male', rx, ry + 188, gw, 40, 'Masculino', {
        style = C.gender == 'masculino' and 'default' or 'ghost',
        onClick = function() C.gender = 'masculino' end,
    }) then end
    if UI.button('cc_female', rx + gw + 12, ry + 188, gw, 40, 'Feminino', {
        style = C.gender == 'feminino' and 'default' or 'ghost',
        onClick = function() C.gender = 'feminino' end,
    }) then end

    Text.draw(Theme.font.xs, 'História (opcional)', rx, ry + 244, rw, 'left', Theme.color.muted)
    local bio = UI.textInput('cc_bio', rx, ry + 260, rw, 42, C.bio, { placeholder = 'De onde vem? O que busca no crepúsculo?' })
    C.bio = bio

    -- resumo / erro
    if C.race then
        local race = DB.races[C.race]
        local summary = string.format('%s · %s · %d anos\nVida %d · Mana %d · Ataque %d · Defesa %d',
            U.trim(C.name) ~= '' and U.trim(C.name) or 'Sem nome', race.name, C.age,
            race.baseLife, race.mana, race.baseAttack, race.baseDefense)
        Text.draw(Theme.font.xs, summary, rx, ry + 318, rw, 'left', Theme.color.muted, 1.4)
    end
    if C.error then
        Text.draw(Theme.font.xs, C.error, rx, ry + 360, rw, 'left', Theme.color.red)
    end

    -- botões
    local btnY = py + ph - 62
    if UI.button('cc_back', px + 24, btnY, 170, 42, 'Voltar', {
        style = 'ghost', onClick = function() Manager.set('title') end,
    }) then end
    if UI.button('cc_start', px + pw - 300, btnY, 276, 42, 'Iniciar jornada', {
        style = 'gold',
        onClick = function()
            local err = validate()
            if err then
                C.error = err
                UI.toast('❌ ' .. err, 3)
                return
            end
            C.error = nil
            local G = State.startNew(C.name, C.race, C.gender, C.age, C.bio)
            State.addLog(string.format('🌅 %s, %s, inicia sua jornada no Reino da Aurora.', G.character.name, DB.races[C.race].name))
            State.addLog('🏠 Você acorda em sua casa. Há uma mochila com maçãs e pão sobre a mesa.')
            State.addLog('🗺️ Abra o mapa (botão Mapa) para viajar. À noite, cuidado com as estradas.')
            State.addLog('💡 Dica: clique nos itens para usar/equipar; arraste para reorganizar.')
            Manager.set('game')
        end,
    }) then end
end

function Creation.keypressed(key)
    if key == 'escape' then
        Manager.set('title')
        return true
    end
end

return Creation
