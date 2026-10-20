-- Despacho das ações de localização (os antigos onclick="funcao()").
-- Em vez de abrir modais diretamente, as ações registram um pedido em
-- Actions.request; a tela do jogo consome e abre o modal correspondente.
local DB = require('src.data.init')
local State = require('src.game.state')
local Inventory = require('src.game.inventory')
local Survival = require('src.game.survival')
local Time = require('src.game.time')
local Quests = require('src.game.quests')
local Combat = require('src.game.combat')
local NPC = require('src.game.npc')
local Craft = require('src.game.craft')
local MG = require('src.game.minigame')
local Achievements = require('src.game.achievements')
local U = require('src.core.util')

local Actions = {}

Actions.request = nil

local function G() return State.G end
local function rnd(n) return (love and love.math.random(n) or math.random(n)) end
local function rndf() return (love and love.math.random() or math.random()) end
local function rnd0(n) return math.floor(rndf() * n) end
local function now()
    if love and love.timer then return love.timer.getTime() end
    return os.clock()
end

local function canAct()
    local G_ = G()
    return G_ and G_.character and not G_.isDead
end

-- ───────────────────────────────────────────────────────── viagem
function Actions.travel(target, message)
    if not canAct() then return false end
    if not DB.locations[target] then
        State.addLog('⚠️ Destino desconhecido: ' .. tostring(target))
        return false
    end
    local G_ = G()
    local firstVisit = not G_.stats.locations[target]
    G_.location = target
    G_.stats.locations[target] = true
    if G_.enemy then G_.enemy = nil end
    if firstVisit then
        State.addLog(string.format('🗺️ Novo local descoberto: %s!', DB.locations[target].name))
    end
    State.addLog(message and message ~= '' and message or ('Você chega em ' .. DB.locations[target].name .. '.'))
    Survival.onTravel()
    Quests.trigger('location_change', { location = target })
    Achievements.check()
    G_.stats.travels = (G_.stats.travels or 0) + 1
    if G_.stats.travels % 5 == 0 then State.save(true) end
    return true
end

-- ───────────────────────────────────────────────────────── mapas
Actions.talkMap = {
    talkToApprenticeIvo = 'apprenticeIvo',
    talkToBakerAmelia = 'bakerAmelia',
    talkToBakerClara = 'bakerClara',
    talkToCaptain = 'captain',
    talkToCarterTomas = 'carterTomas',
    talkToElderBeatriz = 'elderBeatriz',
    talkToForemanJoaquim = 'foremanJoaquim',
    talkToGirlNina = 'girlNina',
    talkToInnkeeperHelena = 'innkeeperHelena',
    talkToKing = 'king',
    talkToLibrarian = 'librarian',
    talkToShepherdLia = 'shepherdLia',
    talkToTraderDamiao = 'traderDamiao',
    talkToVillagerBruno = 'villagerBruno',
    talkToVillagerDora = 'villagerDora',
    talkToVillagerRosa = 'villagerRosa',
    talkToWoodcutterTeo = 'woodcutterTeo',
    visitArtisan = 'artisan',
    visitCarpenter = 'carpenter',
    visitCartographer = 'cartographer',
    visitFarmerHouse1 = 'farmerMiguel',
    visitFarmerHouse2 = 'farmerAna',
    visitWeaver = 'weaver',
}

-- ───────────────────────────────────────────────────────── compras
local BUY = {
    buyApple = { id = 'apple', price = 2, kind = 'item' },
    buyBread = { id = 'bread', price = 2, kind = 'item' },
    buyMeat = { id = 'meat', price = 5, kind = 'item' },
    buyFish = { id = 'fish', price = 10, kind = 'item' },
    buyCarrot = { id = 'cenoura', price = 1, kind = 'item' },
    buyBeer = { id = 'beer', price = 5, kind = 'drink' },
    buyWine = { id = 'wine', price = 15, kind = 'drink' },
    buyCoffee = { id = 'coffee', price = 8, kind = 'drink' },
    buyWaterBottle = { id = 'water_bottle', price = 3, kind = 'drink' },
}

local STORIES = {
    { title = 'A Lenda do Herói das Montanhas', text = 'Há muito tempo, um herói chamado Aldric enfrentou o dragão das montanhas fumegantes. Com sua espada encantada, ele derrotou a besta e salvou todo o reino. Dizem que sua espada ainda está escondida em algum lugar, esperando por um novo herói digno...' },
    { title = 'Terras Além-Mar', text = 'Um mercador de barba grisalha conta sobre terras distantes: "Além do mar oriental, existe um continente onde as árvores são feitas de cristal e os rios brilham como prata líquida. Um dia, talvez, possamos navegar até lá..."' },
    { title = 'A Grande Guerra', text = 'Veteranos relembram: "Há quinhentos anos, uma guerra devastadora quase destruiu nosso reino. Foi quando o primeiro Rei da Aurora uniu todos os povos e construiu estas muralhas que nos protegem até hoje."' },
    { title = 'O Tesouro Esquecido', text = 'Um sussurro corre pela taverna: "Dizem que nas ruínas antigas, além da floresta proibida, existe um tesouro deixado pelos antigos. Mas poucos que entraram lá voltaram para contar a história..."' },
}

-- ───────────────────────────────────────────────────────── compras
local function buyItem(id, price)
    local G_ = G()
    if G_.character.gold < price then
        State.addLog('❌ Moedas insuficientes!')
        return false
    end
    G_.character.gold = G_.character.gold - price
    Inventory.add(id, 1)
    State.addLog(string.format('🛒 Você comprou %s por %d moedas.', DB.items[id] and DB.items[id].name or id, price))
    G_.stats.purchases = (G_.stats.purchases or 0) + 1
    return true
end

local function buyDrink(id, price)
    local G_ = G()
    local item = DB.items[id]
    if not item then return false end
    local finalPrice = price
    local reused
    if item.givesEmptyCup and DB.items[item.givesEmptyCup] then
        local idx = Inventory.find(G_.inventory, item.givesEmptyCup)
        if idx then
            Inventory.removeAt(G_.inventory, idx, 1)
            finalPrice = math.max(1, price - 1)
            reused = DB.items[item.givesEmptyCup]
        end
    end
    if G_.character.gold < finalPrice then
        State.addLog('❌ Moedas insuficientes!')
        return false
    end
    G_.character.gold = G_.character.gold - finalPrice
    Inventory.add(id, 1)
    if reused then
        State.addLog(string.format('♻️ Você reutilizou seu %s — desconto de 1 moeda!', reused.name))
    end
    State.addLog(string.format('🍺 Você comprou %s por %d moedas.', item.name, finalPrice))
    -- O original consome na hora (recupera vida/mana) e mantém o item no inventário.
    if item.heal and item.heal > 0 then State.heal(item.heal) end
    if item.mana and item.mana > 0 then
        G_.character.mana = math.min(G_.character.maxMana, G_.character.mana + item.mana)
    end
    G_.stats.purchases = (G_.stats.purchases or 0) + 1
    return true
end

-- ───────────────────────────────────────────────────────── ações
function Actions.perform(fnName)
    local G_ = G()
    if not G_ or not G_.character or G_.isDead then return false end
    if G_.enemy then return false end
    fnName = tostring(fnName or '')

    -- Biblioteca só abre de dia.
    if fnName == 'goLibrary' then
        if G_.timeOfDay ~= 'day' then
            State.addLog('🌙 A Biblioteca Real está fechada. Volte durante o dia!')
            return true
        end
    end

    -- Conversar / visitar NPCs
    local npcId = Actions.talkMap[fnName]
    if npcId then
        Actions.request = { type = 'npc', id = npcId }
        return true
    end

    -- Compras rápidas de barraca
    local b = BUY[fnName]
    if b then
        if b.kind == 'drink' then buyDrink(b.id, b.price) else buyItem(b.id, b.price) end
        return true
    end

    -- Viagens (funções go)
    local mv = DB.moves[fnName]
    if mv then
        return Actions.travel(mv.target, mv.msg)
    end

    -- Ações especiais
    if fnName == 'rest' then
        if G_.location ~= 'home' then
            State.addLog('😴 Você só pode dormir em casa (ou alugando um quarto na estalagem).')
            return true
        end
        local ok, msg = Time.canSleep()
        if not ok then
            State.addLog('⚠️ ' .. msg)
            return true
        end
        Actions.request = { type = 'sleep' }
        return true
    elseif fnName == 'toggleChest' then
        Actions.request = { type = 'chest' }
        return true
    elseif fnName == 'fillBottle' then
        local idx = Inventory.find(G_.inventory, 'bottle')
        if not idx then
            State.addLog('❌ Você não tem uma garrafa vazia para encher!')
            return true
        end
        if not DB.WATER_LOCATIONS[G_.location] then
            State.addLog('💧 Não há fonte de água potável aqui.')
            return true
        end
        Inventory.removeAt(G_.inventory, idx, 1)
        Inventory.add('water_bottle', 1)
        State.addLog('💧 Você enche a garrafa com água fresca.')
        return true
    elseif fnName == 'drinkWater' then
        Survival.drinkWater()
        return true
    elseif fnName == 'eatApplePie' then
        local healed = State.heal(45)
        Survival.apply(30, 5)
        State.addLog(string.format('🥧 Você come uma fatia generosa de torta de maçã. Vida +%d', healed))
        return true
    elseif fnName == 'warmByForge' then
        Survival.addSanity(4)
        State.addLog('🔥 Você se aquece junto à fornalha. A mente clareia um pouco. (+4 sanidade)')
        return true
    elseif fnName == 'pickFruit' then
        local last = G_.flags._lastPick or 0
        if now() - last < 1.5 then return true end
        G_.flags._lastPick = now()
        local fruits = { 'apple', 'apple', 'apple', 'lemon' }
        local id = fruits[rnd(#fruits)]
        Survival.spend(1, 1)
        Inventory.add(id, 1)
        State.addLog(string.format('🍎 Você colhe %s nos pomares.', (DB.items[id] and DB.items[id].name or 'fruta'):lower()))
        return true
    elseif fnName == 'chopWoodEastPlains' or fnName == 'chopWood' then
        local last = G_.flags._lastChop or 0
        if now() - last < 1.5 then return true end
        G_.flags._lastChop = now()
        local axe = Inventory.mainhandTool('axe')
        local difficulty = axe and (axe.chopPower or 1) == 2 and 0.85 or 1.05
        MG.start({
            kind = 'tree',
            label = 'Derrubar a árvore',
            difficulty = difficulty,
            needed = 3,
            onSuccess = function()
                local amount = rndf() < 0.35 and 2 or 1
                if axe then
                    amount = amount + 1
                    Inventory.damageTool(axe, 1)
                end
                Inventory.add('wood', amount)
                State.addLog(string.format('🪓 Você corta uma árvore e junta %d de Madeira.', amount))
            end,
        })
        return true
    elseif fnName == 'listenStories' then
        local story = STORIES[rnd(#STORIES)]
        State.addLog('📖 ' .. story.title .. ': ' .. story.text)
        if rndf() < 0.2 then
            G_.character.mana = math.min(G_.character.maxMana, G_.character.mana + 10)
            State.addLog('🎵 As histórias inspiradoras recuperam 10 de mana!')
        end
        return true
    elseif fnName == 'rentInnRoom' then
        local ok, msg = Time.canSleep()
        if not ok then
            State.addLog('⚠️ ' .. msg)
            return true
        end
        if G_.character.gold < 5 then
            State.addLog('🛏️ Você precisa de 5 moedas para alugar um quarto na estalagem.')
            return true
        end
        G_.character.gold = G_.character.gold - 5
        State.addLog('🛏️ Você paga 5 moedas e aluga um quarto na Estalagem do Sul.')
        Actions.request = { type = 'sleep' }
        return true
    elseif fnName == 'searchRuins' then
        local r = rndf()
        if r < 0.3 then
            local finds = { 'bone', 'paper', 'bottle' }
            local id = finds[rnd(#finds)]
            Inventory.add(id, 1)
            State.addLog(string.format('🔍 Entre os escombros, você encontra %s!', DB.items[id].name))
        elseif r < 0.5 then
            local gold = 5 + rnd0(20)
            G_.character.gold = G_.character.gold + gold
            State.addLog(string.format('💰 Você encontra %d moedas de ouro entre as pedras!', gold))
        else
            State.addLog('🔍 Você revira os escombros, mas não encontra nada de valor.')
        end
        return true
    elseif fnName == 'exploreDarkForest' then
        if rndf() < 0.6 then
            Combat.start('wolf')
        else
            State.addLog('🌲 A floresta está silenciosa... por enquanto. Você encontra alguns cogumelos pelo caminho.')
            if rndf() < 0.3 then
                local finds = { 'apple', 'bread' }
                local id = finds[rnd(#finds)]
                Inventory.add(id, 1)
                State.addLog(string.format('🍄 Você encontrou %s abandonado perto de uma árvore caída!', DB.items[id].name))
            end
        end
        return true
    elseif fnName == 'openMillInterface' then
        Actions.request = { type = 'station', station = 'mill' }
        return true
    elseif fnName == 'showQuestBoard' then
        Actions.request = { type = 'questboard' }
        return true
    elseif fnName == 'searchLibraryBooks' then
        return Actions.searchLibraryBooks()
    elseif fnName == 'returnLibraryBooks' then
        return Actions.returnLibraryBooks()
    elseif fnName == 'enterMine' then
        return Actions.enterMine()
    elseif fnName == 'mineProspect' then
        return Actions.mineProspect()
    elseif fnName == 'mineDescend' then
        return Actions.mineDescend()
    elseif fnName == 'mineAscend' then
        return Actions.mineAscend()
    elseif fnName == 'mineLightTorch' then
        return Actions.mineLightTorch()
    elseif fnName == 'mineLeave' then
        Actions.request = nil
        State.addLog('🪜 Você sobe de volta para a entrada da mina.')
        return true
    elseif fnName == 'searchMausoleum' then
        if (G_.stats.killsByType.cemetery_lord or 0) > 0 and rndf() < 0.5 then
            State.addLog('🪦 O sarcófago está vazio. Restam só ossos e poeira.')
            if rndf() < 0.4 then
                G_.character.gold = G_.character.gold + 40
                State.addLog('💰 Você encontra 40 moedas escondidas nas frestas!')
            end
        else
            State.addLog('☠️ O sarcófago se abre com um estalo. Algo antigo se ergue!')
            Combat.start('cemetery_lord')
        end
        return true
    elseif fnName == 'searchGraves' then
        if Combat.spawnFor('cemetery_graves') then return true end
        local r = rndf()
        if r < 0.35 then
            Inventory.add('bone', 1)
            State.addLog('🦴 Você encontra um osso antigo entre as covas.')
        elseif r < 0.55 then
            local g = 5 + rnd0(25)
            G_.character.gold = G_.character.gold + g
            State.addLog(string.format('💰 %d moedas perdidas entre as lápides!', g))
        else
            State.addLog('🪦 Nada além de névoa e silêncio... por enquanto.')
        end
        return true
    elseif fnName == 'exploreDragonPeak' then
        if G_.enemy then return true end
        State.addLog('🐉 O chão treme. Asas enormes rasgam as nuvens — o dragão desce!')
        Combat.start('dragon')
        return true
    elseif fnName == 'exploreEastWilds' then
        if Combat.spawnFor('east_wilds') then return true end
        if rndf() < 0.4 then
            Inventory.add('wood', 1)
            State.addLog('🪵 Você encontra madeira entre os destroços de uma carroça.')
        else
            State.addLog('🌾 O descampado está silencioso. Só o vento passa.')
        end
        return true
    elseif fnName == 'searchEastCamp' then
        if rndf() < 0.5 then
            local g = 10 + rnd0(40)
            G_.character.gold = G_.character.gold + g
            State.addLog(string.format('💰 Você saqueia %d moedas do acampamento abandonado!', g))
        elseif rndf() < 0.6 then
            local finds = { 'paper', 'bone', 'cloth' }
            local id = finds[rnd(#finds)]
            Inventory.add(id, 1)
            State.addLog(string.format('📦 Você encontra %s numa caixa largada.', DB.items[id].name))
        else
            State.addLog('🔍 O acampamento foi saqueado antes de você chegar.')
        end
        return true
    elseif fnName == 'challengeBlackMage' then
        if (G_.stats.killsByType.black_mage or 0) > 0 then
            State.addLog('🧙 As sombras se aquietaram. O Mago Negro não volta tão cedo.')
            return true
        end
        State.addLog('🌑 O Mago Negro ergue a mão e a luz do mundo parece hesitar.')
        Combat.start('black_mage')
        return true
    end

    State.addLog('⚠️ Ação ainda não portada: ' .. fnName)
    return false
end

-- ───────────────────────────────────────────────────────── mina
function Actions.initMine()
    local G_ = G()
    G_.mine = G_.mine or { depth = 1, fuel = 120, found = 0 }
    return G_.mine
end

function Actions.enterMine()
    local G_ = G()
    local pick = Inventory.mainhandTool('pickaxe')
    if not pick then
        State.addLog('⛏️ Você precisa de uma picareta equipada na mão principal para minerar.')
        return true
    end
    Actions.initMine()
    State.addLog(string.format('🕳️ Você desce à galeria da mina (profundidade %d).', G_.mine.depth))
    Actions.request = { type = 'mine' }
    return true
end

local function mineVein(depth)
    local r = rndf()
    if depth <= 1 then
        if r < 0.55 then return 'stone' elseif r < 0.85 then return 'coal' else return 'iron_ore' end
    elseif depth == 2 then
        if r < 0.25 then return 'stone' elseif r < 0.6 then return 'coal' elseif r < 0.92 then return 'iron_ore' else return 'amethyst' end
    else
        if r < 0.2 then return 'coal' elseif r < 0.72 then return 'iron_ore' else return 'amethyst' end
    end
end

local function mineFuelCheck()
    local G_ = G()
    local mine = Actions.initMine()
    if mine.fuel <= 0 then
        State.addLog('🌑 Está escuro demais! Você se machuca tateando na rocha. (Vida −5)')
        Inventory.applyDamage(5)
        return false
    end
    return true
end

function Actions.mineProspect()
    local G_ = G()
    local pick = Inventory.mainhandTool('pickaxe')
    if not pick then
        State.addLog('⛏️ Equipe uma picareta para minerar.')
        return true
    end
    local mine = Actions.initMine()
    if mine.fuel <= 0 then mineFuelCheck() return true end
    local oreId = mineVein(mine.depth)
    local hardness = ({ stone = 0.9, coal = 1.0, iron_ore = 1.15, amethyst = 1.35 })[oreId] or 1
    local power = pick.minePower or 1
    MG.start({
        kind = 'mine',
        label = 'Minerar ' .. (DB.items[oreId] and DB.items[oreId].name or oreId),
        difficulty = math.max(0.65, hardness - (power - 1) * 0.2),
        needed = 3,
        onSuccess = function()
            local qty = 1
            if power >= 2 and rndf() < 0.35 then qty = 2 end
            if rndf() < 0.1 then qty = qty + 1 end
            Inventory.add(oreId, qty)
            Inventory.damageTool(pick, 1)
            mine.fuel = math.max(0, mine.fuel - 8)
            mine.found = (mine.found or 0) + qty
            State.addLog(string.format('⛏️ Você extrai %dx %s!', qty, DB.items[oreId] and DB.items[oreId].name or oreId))
        end,
    })
    return true
end

function Actions.mineDescend()
    local mine = Actions.initMine()
    if mine.depth >= 3 then
        State.addLog('🕳️ A galeria termina aqui: rocha maciça bloqueia o caminho.')
        return true
    end
    mine.depth = mine.depth + 1
    mine.fuel = math.max(0, mine.fuel - 15)
    State.addLog(string.format('🪜 Você desce para a profundidade %d. O ar fica mais pesado.', mine.depth))
    if rndf() < 0.25 then
        local ids = { 'bat', 'skeleton', 'goblin' }
        local id = ids[rnd(#ids)]
        if DB.creatures[id] then
            State.addLog('❗ Algo se move nas sombras...')
            Combat.start(id)
        end
    end
    return true
end

function Actions.mineAscend()
    local mine = Actions.initMine()
    if mine.depth <= 1 then
        State.addLog('🪜 Você já está na entrada da mina.')
        return true
    end
    mine.depth = mine.depth - 1
    State.addLog(string.format('🪜 Você sobe para a profundidade %d.', mine.depth))
    return true
end

function Actions.mineLightTorch()
    local G_ = G()
    local mine = Actions.initMine()
    local idx = Inventory.find(G_.inventory, 'tocha')
    if not idx then
        State.addLog('🔥 Você não tem tochas no inventário.')
        return true
    end
    Inventory.removeAt(G_.inventory, idx, 1)
    mine.fuel = math.min(300, (mine.fuel or 0) + 120)
    State.addLog('🔥 Você acende uma tocha. A galeria volta a ser visível.')
    return true
end

-- ───────────────────────────────────────────────────────── biblioteca
function Actions.searchLibraryBooks()
    local G_ = G()
    local hasCard = Inventory.find(G_.inventory, 'library_card') ~= nil
    if not hasCard and not G_.library.hasMembership then
        State.addLog('🎫 Você precisa do cartão de membro para pegar livros emprestados. Fale com a bibliotecária.')
        return true
    end
    if G_.flags._lastLibrarySearch == G_.dayCount then
        State.addLog('📚 Você já pegou um livro hoje. Volte amanhã.')
        return true
    end
    G_.flags._lastLibrarySearch = G_.dayCount
    local titles = {
        { title = 'Crônicas da Aurora', content = 'A história do Reino da Aurora começa com a união dos povos sob a primeira coroa. As muralhas foram erguidas no ano 12 da Era do Crepúsculo.' },
        { title = 'Herbário do Norte', content = 'Ervas de folha prateada crescem perto de rios. Evite as de caule negro: seu pó causa sonhos febris.' },
        { title = 'Sobre Dragões', content = 'Dragões acumulam calor e memória. Dizem que o dragão do Pico guarda a última escama de seu antepassado.' },
        { title = 'Mapas do Velho Pedro', content = 'Anotações sobre trilhas esquecidas: o caminho leste das ruínas leva a um acampamento abandonado.' },
    }
    local book = titles[rnd(#titles)]
    Inventory.add('book', 1)
    local idx = Inventory.find(G_.inventory, 'book')
    if idx then
        local item = G_.inventory[idx]
        item.title = book.title
        item.content = book.content
        item.libraryBook = true
        item.bookId = 'lib_' .. G_.dayCount .. '_' .. rnd(999)
    end
    G_.library.reputation = math.min(100, (G_.library.reputation or 50) + 2)
    State.addLog(string.format('📚 Você pega emprestado "%s". (Reputação +2)', book.title))
    Achievements.check()
    return true
end

function Actions.returnLibraryBooks()
    local G_ = G()
    local count = 0
    for i = Inventory.SLOTS, 1, -1 do
        local it = G_.inventory[i]
        if it and it.libraryBook then
            count = count + 1
            G_.inventory[i] = nil
        end
    end
    if count == 0 then
        State.addLog('📚 Você não tem nenhum livro da biblioteca para devolver.')
        return true
    end
    G_.library.reputation = math.min(100, (G_.library.reputation or 50) + 3 * count)
    State.addLog(string.format('📚 Você devolve %d livro(s). (Reputação +%d)', count, 3 * count))
    Achievements.check()
    return true
end

-- ───────────────────────────────────────────────────────── estações
function Actions.openStation(stationType)
    Actions.request = { type = 'station', station = stationType }
end

function Actions.pendingRequest()
    local r = Actions.request
    Actions.request = nil
    return r
end

return Actions
