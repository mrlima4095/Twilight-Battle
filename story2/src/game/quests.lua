-- Motor de missões (port de story.html: trigger/acceptQuest/completeQuest).
local DB = require('src.data.init')
local State = require('src.game.state')
local Inventory = require('src.game.inventory')
local U = require('src.core.util')

local Q = {}

local function G() return State.G end

function Q.active()
    local G_ = G()
    if not G_ or not G_.activeQuest or not G_.activeQuest.id then return nil end
    return DB.quests[G_.activeQuest.id]
end

function Q.currentStage()
    local quest = Q.active()
    if not quest then return nil end
    local idx = (G().activeQuest.currentStage or 0) + 1
    return quest.stages[idx], idx
end

function Q.progress()
    local G_ = G()
    if not G_.activeQuest then return 0, 0 end
    local idx = G_.activeQuest.currentStage or 0
    local p = (G_.activeQuest.stageProgress and G_.activeQuest.stageProgress[idx]) or 0
    local stage = Q.currentStage()
    return p, stage and stage.required or 0
end

function Q.isCompleted(id)
    for _, qid in ipairs(G().completedQuests or {}) do
        if qid == id then return true end
    end
    return false
end

function Q.available(id)
    local quest = DB.quests[id]
    if not quest then return false, 'Missão não encontrada.' end
    if Q.isCompleted(id) and not quest.repeatable then
        return false, 'Você já completou esta missão.'
    end
    if G().activeQuest and G().activeQuest.id then
        return false, 'Você já tem uma missão ativa.'
    end
    local req = quest.requires
    if req then
        if req.level and (G().character.level or 1) < req.level then
            return false, string.format('Requer nível %d.', req.level)
        end
        if req.quests then
            for _, qid in ipairs(req.quests) do
                if not Q.isCompleted(qid) then
                    return false, 'Requer completar outra missão primeiro.'
                end
            end
        end
    end
    return true
end

function Q.accept(id)
    local quest = DB.quests[id]
    if not quest then return false end
    local ok, why = Q.available(id)
    if not ok then
        State.addLog('❌ ' .. why)
        return false
    end
    local G_ = G()
    if quest.repeatable and Q.isCompleted(id) then
        for i, qid in ipairs(G_.completedQuests) do
            if qid == id then table.remove(G_.completedQuests, i) break end
        end
    end
    G_.activeQuest = { id = id, currentStage = 0, stageProgress = { [0] = 0 }, startedAt = os.time() }
    local first = quest.stages[1]
    State.addLog(string.format('📜 MISSÃO ACEITA: %s', quest.name))
    State.addLog('📖 ' .. quest.description)
    State.addLog(string.format('📍 Estágio 1: %s', first.name))
    State.addLog('📋 ' .. first.description)
    if first.hints then State.addLog('💡 ' .. first.hints) end
    -- Missões de coleta contam o que já está na mochila.
    if first.type == 'collect_item' then
        Q.trigger('item_acquired', { itemId = first.target })
    end
    return true
end

function Q.abandon()
    local G_ = G()
    if not G_.activeQuest or not G_.activeQuest.id then return false end
    local name = DB.quests[G_.activeQuest.id] and DB.quests[G_.activeQuest.id].name or 'Missão'
    G_.activeQuest = nil
    State.addLog('⚠️ Você abandonou a missão: ' .. name)
    return true
end

function Q.complete(id)
    local quest = DB.quests[id]
    if not quest then return false end
    if Q.isCompleted(id) and not quest.repeatable then return false end
    for _, reward in ipairs(quest.rewards or {}) do
        if reward.gold then G().character.gold = G().character.gold + reward.gold end
        if reward.exp then State.addExp(reward.exp) end
        if reward.item then
            Inventory.add(reward.item, reward.itemQty or 1)
            State.addLog(string.format('🎁 Recompensa: %dx %s', reward.itemQty or 1,
                DB.items[reward.item] and DB.items[reward.item].name or reward.item))
        end
    end
    if not Q.isCompleted(id) then
        table.insert(G().completedQuests, id)
    end
    G().stats.questsCompleted = (G().stats.questsCompleted or 0) + 1
    State.addLog(string.format('✨ MISSÃO COMPLETA: %s! ✨', quest.name))
    G().activeQuest = nil
    local Achievements = require('src.game.achievements')
    Achievements.check()
    return true
end

local function advanceStage(quest, currentIdx)
    local G_ = G()
    local nextIdx = currentIdx + 1
    -- currentIdx é 0-based: completar a última etapa (idx #stages-1)
    -- significa concluir a missão, não avançar para uma etapa inexistente.
    if nextIdx >= #quest.stages then
        Q.complete(quest.id)
        return
    end
    G_.activeQuest.currentStage = nextIdx
    G_.activeQuest.stageProgress[nextIdx] = quest.stages[nextIdx].progress or 0
    local stage = quest.stages[nextIdx]
    State.addLog(string.format('📜 Missão atualizada: "%s"', stage.name))
    State.addLog('📖 ' .. stage.description)
    if stage.hints then State.addLog('💡 Dica: ' .. stage.hints) end
end

function Q.trigger(eventType, data)
    data = data or {}
    local G_ = G()
    if not G_ or G_.isDead or not G_.activeQuest then return false end
    local quest = DB.quests[G_.activeQuest.id]
    if not quest then return false end
    local idx = G_.activeQuest.currentStage or 0
    local stage = quest.stages[idx + 1]
    if not stage then return false end

    G_.activeQuest.stageProgress = G_.activeQuest.stageProgress or {}
    local current = tonumber(G_.activeQuest.stageProgress[idx]) or 0
    local progressed = false

    if stage.type == 'talk_to_npc' then
        if eventType == 'npc_talk' and data.npcId == stage.target and current < stage.required then
            current = stage.required
            progressed = true
            local npc = DB.npcs[stage.target]
            State.addLog(string.format('💬 Missão "%s": conversou com %s.', quest.name, npc and npc.name or stage.target))
        end
    elseif stage.type == 'kill_creature' then
        if eventType == 'kill' and data.creatureId == stage.target and current < stage.required then
            current = math.min(stage.required, current + 1)
            progressed = true
            State.addLog(string.format('⚔️ Missão "%s": %d/%d %s derrotado(s).', quest.name, current, stage.required,
                DB.creatures[stage.target] and DB.creatures[stage.target].name or stage.target))
        end
    elseif stage.type == 'collect_item' then
        if eventType == 'item_acquired' and data.itemId == stage.target then
            local qty = Inventory.count(G_.inventory, stage.target)
            local newProgress = math.min(stage.required, qty)
            if newProgress > current then
                current = newProgress
                progressed = true
                State.addLog(string.format('📦 Missão "%s": %d/%d %s.', quest.name, current, stage.required,
                    DB.items[stage.target] and DB.items[stage.target].name or stage.target))
            end
        end
    elseif stage.type == 'deliver_item' then
        if eventType == 'npc_talk' and data.npcId == stage.target then
            local itemId = data.itemId or stage.itemId
            if itemId then
                local qty = Inventory.count(G_.inventory, itemId)
                if qty >= stage.required and current < stage.required then
                    Inventory.removeById(G_.inventory, itemId, stage.required)
                    current = stage.required
                    progressed = true
                    State.addLog(string.format('📦 Missão "%s": %d %s entregue(s)!', quest.name, stage.required,
                        DB.items[itemId] and DB.items[itemId].name or itemId))
                end
            end
        end
    elseif stage.type == 'visit_location' then
        if eventType == 'location_change' and data.location == stage.target and current < stage.required then
            current = stage.required
            progressed = true
            State.addLog(string.format('📍 Missão "%s": local visitado!', quest.name))
        end
    end

    if not progressed then return false end
    G_.activeQuest.stageProgress[idx] = current
    if current >= stage.required then
        advanceStage(quest, idx)
    end
    return true
end

function Q.shortLine()
    local quest = Q.active()
    if not quest then return nil end
    local stage, idx = Q.currentStage()
    local p, req = Q.progress()
    return string.format('%s — %d/%d', stage.name, p, req), quest, stage, idx
end

return Q
