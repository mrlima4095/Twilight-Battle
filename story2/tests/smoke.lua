-- Testes de lógica + smoke test de desenho com um mock mínimo de LÖVE.
package.path = './?.lua;' .. package.path

local files = {}
local function fontObj(size)
    return {
        getWidth = function(_, s) return (#tostring(s or '')) * (size or 10) * 0.55 end,
        getHeight = function() return size or 12 end,
        getWrap = function(_, str, limit)
            str = tostring(str or '')
            return limit or 1000, { str }
        end,
    }
end

love = {
    math = {
        random = function(a, b)
            if a == nil then return 0.5 end
            if b == nil then return 1 end
            return math.random(a, b)
        end,
        setRandomSeed = function() end,
    },
    timer = { getTime = function() return os.clock() end },
    graphics = {
        newFont = function(a, b)
            if type(a) == 'number' then return fontObj(a) end
            return fontObj(b or 12)
        end,
        setDefaultFilter = function() end,
        setBackgroundColor = function() end,
        setColor = function() end,
        setFont = function() end,
        setLineWidth = function() end,
        rectangle = function() end,
        circle = function() end,
        line = function() end,
        polygon = function() end,
        print = function() end,
        printf = function() end,
        push = function() end,
        pop = function() end,
        translate = function() end,
        scale = function() end,
        setScissor = function() end,
        clear = function() end,
        getDimensions = function() return 1280, 720 end,
    },
    filesystem = {
        read = function(name) return files[name] end,
        write = function(name, data) files[name] = data return true end,
        getInfo = function(name) if files[name] then return { type = 'file' } end return nil end,
        remove = function(name) files[name] = nil return true end,
    },
    window = {
        getFullscreen = function() return false end,
        setFullscreen = function() end,
        setTitle = function() end,
    },
    mouse = {
        getPosition = function() return _G.__mouseX or 0, _G.__mouseY or 0 end,
        isDown = function() return false end,
    },
    event = { quit = function() end },
    keyboard = { isDown = function() return false end },
}

local ok, err = pcall(function()
    local State = require('src.game.state')
    local Inventory = require('src.game.inventory')
    local Survival = require('src.game.survival')
    local Time = require('src.game.time')
    local Quests = require('src.game.quests')
    local Combat = require('src.game.combat')
    local Craft = require('src.game.craft')
    local NPC = require('src.game.npc')
    local Actions = require('src.game.actions')
    local Achievements = require('src.game.achievements')
    local MG = require('src.game.minigame')
    local DB = require('src.data.init')
    local Theme = require('src.core.theme')

    Theme.load()

    local function check(cond, msg)
        if not cond then error('FALHOU: ' .. msg, 2) end
        print('ok  ' .. msg)
    end

    -- criação
    local G = State.startNew('Teste', 'elf', 'feminino', 42, 'bio')
    check(G.character.name == 'Teste', 'criação define nome')
    check(G.character.life == DB.races.elf.baseLife, 'vida inicial da raça')
    check(Inventory.count(G.inventory, 'apple') == 3, 'maçãs iniciais')
    check(Inventory.count(G.chest, 'clock') == 1, 'relógio no baú')

    -- inventário / stack / equipamento
    Inventory.add('wood', 70)
    check(Inventory.count(G.inventory, 'wood') == 70, 'stack de madeira em 64+6')
    Inventory.organize(G.inventory)
    check(Inventory.count(G.inventory, 'wood') == 70, 'organizar mantém quantidade')
    local axe = Inventory.add('machado_pedra', 1)
    local idx = Inventory.find(G.inventory, 'machado_pedra')
    check(idx ~= nil, 'machado no inventário')
    local okEq = Inventory.equip(idx)
    check(okEq and G.equipment.mainhand and G.equipment.mainhand.id == 'machado_pedra', 'equipar machado')
    check(Inventory.totalAttack() == DB.races.elf.baseAttack + (G.equipment.mainhand.attack or 0), 'ataque total com arma')

    -- dano em armadura
    Inventory.add('peitoral_couro', 1)
    local ai = Inventory.find(G.inventory, 'peitoral_couro')
    Inventory.equip(ai)
    local lifeBefore = G.character.life
    Inventory.applyDamage(5)
    check(G.character.life >= lifeBefore - 5, 'armadura absorve dano')
    Inventory.unequip('chest')

    -- sobrevivência
    G.survival.hunger = 50
    Inventory.add('bread', 1)
    local bi = Inventory.find(G.inventory, 'bread')
    Inventory.use(bi)
    check(G.survival.hunger > 50, 'pão recupera fome')

    -- missões: coleta conta itens já na mochila
    G.inventory = State.emptySlots(18)
    Inventory.add('wood', 8)
    check(Quests.accept('carpenter_wood'), 'aceitar missão do marceneiro')
    check(G.activeQuest.currentStage == 1, 'estágio de coleta conta 8 madeiras já na mochila')
    local stage = Quests.currentStage()
    check(stage and stage.type == 'talk_to_npc', 'avança para falar com o carpinteiro')
    NPC.talk('carpenter')
    check(Quests.isCompleted('carpenter_wood'), 'missão concluída ao falar')

    -- combate
    G.character.life = G.character.maxLife
    check(Combat.start('wolf'), 'inicia combate com lobo')
    local guard = 0
    while G.enemy and guard < 100 do
        Combat.attack()
        guard = guard + 1
    end
    check(not G.enemy, 'lobo derrotado em ' .. guard .. ' turnos')
    check((G.stats.killsByType.wolf or 0) == 1, 'abate registrado')
    check(G.bestiary.wolf == 1, 'bestiário registrado')

    -- craft
    G.inventory = State.emptySlots(18)
    Inventory.add('paper', 3)
    Inventory.add('leather', 2)
    check(Craft.craft('book'), 'cria livro na bancada')
    check(Inventory.find(G.inventory, 'book') ~= nil, 'livro no inventário')

    -- fornalha
    G.inventory = State.emptySlots(18)
    Inventory.add('iron_ore', 1)
    Inventory.add('wood', 2)
    local smeltOk = Craft.startSmelt('iron_ore')
    check(smeltOk == true, 'inicia fundição de ferro')
    Craft.update(10)
    local collected = Craft.collectSmelt(1)
    check(collected == true and Inventory.find(G.inventory, 'iron_ingot') ~= nil, 'coleta lingote')

    -- NPC compra/venda
    G.character.gold = 100
    G.inventory = State.emptySlots(18)
    check(NPC.buy('villagerDora', 'apple'), 'compra maçã da Dora')
    local wi = Inventory.find(G.inventory, 'apple')
    local goldBefore = G.character.gold
    check(NPC.sell('villagerDora', wi), 'vende maçã para a Dora')
    check(G.character.gold > goldBefore, 'venda dá ouro')

    -- viagem e ações
    G.location = 'home'
    Actions.perform('goNorthVillage')
    check(G.location == 'north_village', 'viagem para vilarejo norte')
    check(G.stats.locations.north_village, 'local visitado registrado')
    Actions.perform('toggleChest')
    local req = Actions.pendingRequest()
    check(req and req.type == 'chest', 'pedido de baú emitido')

    -- conquistas
    Achievements.check()
    check(type(G.achievements) == 'table', 'conquistas verificadas')

    -- save/load
    check(State.save(), 'salva o jogo')
    local oldName = G.character.name
    G.character.name = 'Alterado'
    check(State.load(), 'carrega o jogo')
    check(State.G.character.name == oldName, 'save/load preserva nome')
    G = State.G

    -- save/load com missão ativa (chaves numéricas no JSON)
    G.activeQuest = { id = 'royal_hunt', currentStage = 0, stageProgress = { [0] = 2 } }
    check(State.save(), 'salva com missão ativa')
    check(State.load(), 'carrega com missão ativa')
    check(State.G.activeQuest and State.G.activeQuest.stageProgress[0] == 2, 'progresso numérico da missão sobrevive ao JSON')
    G = State.G

    -- minigame
    MG.start({ kind = 'tree', needed = 3, onSuccess = function() G.flags.treeDone = true end })
    local hits = 0
    local guard2 = 0
    while MG.active and guard2 < 500 do
        MG.update(0.02)
        if MG.inZone() then MG.strike() end
        guard2 = guard2 + 1
    end
    check(MG.active == nil and G.flags.treeDone == true, 'minigame conclui e chama recompensa')

    -- smoke test de telas/modais
    local UI = require('src.core.ui')
    local Manager = require('src.screens.manager')
    local Modals = require('src.screens.modals')
    local Map = require('src.screens.map')
    local function frame()
        UI.frame(0.016)
        Manager.draw()
        if UI.modal then UI.drawModal() end
        UI.drawToasts()
        UI.drawTooltip()
        UI.endFrame()
    end
    Manager.set('title') frame() frame()
    Manager.set('creation') frame() frame()
    Manager.set('game') frame() frame()

    Modals.openChest() frame() UI.closeModal()
    Modals.openNpc('carpenter')
    frame()
    Modals.openJournal('quests') frame() UI.closeModal()
    Modals.openJournal('bestiary') frame() UI.closeModal()
    Modals.openJournal('achievements') frame() UI.closeModal()
    Modals.openJournal('stats') frame() UI.closeModal()
    Modals.openQuestBoard() frame() UI.closeModal()
    Modals.openStation('crafting_table') frame() UI.closeModal()
    Modals.openStation('loom') frame() UI.closeModal()
    Modals.openStation('furnace') frame() UI.closeModal()
    Modals.openStation('mill') frame() UI.closeModal()
    Modals.openStation('anvil') frame() UI.closeModal()
    Modals.openStation('alchemy') frame() UI.closeModal()
    Modals.openProfile() frame() UI.closeModal()
    Modals.openMenu() frame() UI.closeModal()
    Map.openFull() frame() UI.closeModal()

    G.location = 'south_mine'
    Inventory.add('picareta_pedra', 1)
    local pi = Inventory.find(G.inventory, 'picareta_pedra')
    Inventory.equip(pi)
    Modals.openMine() frame()
    Actions.mineProspect()
    frame() frame()
    MG.cancel()
    frame() UI.closeModal()

    Modals.openEnding() frame() UI.closeModal()

    -- combate + modais abertos (o update deve fechar)
    Combat.start('goblin')
    frame()
    Modals.openChest()
    UI.modal = nil
    Combat.flee()

    -- ───────────────────────── cliques reais (press + release)
    local function paint()
        Manager.draw()
        if UI.modal then UI.drawModal() end
        UI.drawToasts()
        UI.drawTooltip()
        UI.endFrame()
    end
    local function click(gx, gy, button)
        _G.__mouseX, _G.__mouseY = gx, gy
        UI.frame(0.016)
        UI.mousepressed(gx, gy, button or 1)
        paint()
        _G.__mouseX, _G.__mouseY = gx, gy
        UI.frame(0.016)
        UI.mousereleased(gx, gy, button or 1)
        paint()
    end

    Manager.set('title')
    click(640, 364)
    check(Manager.name == 'creation', 'clique em Nova jornada abre a criação')

    -- seleciona raça, digita nome, escolhe gênero e inicia
    click(180, 190)
    click(900, 188)          -- campo nome
    UI.textinput('A') UI.textinput('n')
    click(820, 332)          -- gênero masculino
    click(1030, 630)         -- iniciar
    check(Manager.name == 'game', 'clique em Iniciar jornada abre o jogo')
    check(State.G.character.name == 'An', 'nome digitado foi aplicado')

    -- usa a primeira maçã da mochila com clique (sem arrastar)
    local appleBefore = Inventory.count(State.G.inventory, 'apple')
    click(70, 182)
    check(Inventory.count(State.G.inventory, 'apple') == appleBefore - 1, 'clique usa item da mochila')

    -- abre o baú, move o relógio e fecha pelo botão do modal
    State.G.chest = State.emptySlots(18)
    Inventory.addToChest('clock', 1)
    Modals.openChest()
    paint()
    click(262, 166)
    check(Inventory.find(State.G.inventory, 'clock') ~= nil, 'clique no baú move item para a mochila')
    click(900, 635)
    check(UI.modal == nil, 'botão Fechar do modal funciona')

    -- NPC: aba Comprar e botão Comprar
    Modals.openNpc('villagerDora')
    paint()
    local gold0 = State.G.character.gold
    click(430, 230)
    paint()
    click(950, 300)
    check(State.G.character.gold < gold0, 'compra na loja do NPC pelo botão')
    UI.closeModal()

    -- combate: botão Atacar
    State.G.character.life = State.G.character.maxLife
    Combat.start('wolf')
    paint()
    local hp0 = State.G.enemy and State.G.enemy.life or 0
    click(430, 528)
    check(State.G.enemy == nil or State.G.enemy.life < hp0, 'botão Atacar causa dano')
    State.G.enemy = nil

    -- botão do menu superior
    click(1230, 42)
    check(UI.modal and UI.modal.kind == 'menu', 'botão Menu abre o modal')
    UI.closeModal()

    -- main.lua completo (load/update/draw) com o mock
    dofile('main.lua')
    love.load()
    love.update(0.016)
    love.draw()
    love.update(0.016)
    love.draw()
    check(true, 'main.lua carrega, atualiza e desenha')

    print('TODOS OS TESTES PASSARAM')
end)
if not ok then
    io.stderr:write(tostring(err) .. '\n')
    os.exit(1)
end
