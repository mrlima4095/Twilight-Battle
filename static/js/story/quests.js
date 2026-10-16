/*
 * Twilight Battle — Modo História
 * Módulo de dados: QUESTS
 * ------------------------------------------------------------------
 * Este arquivo é carregado ANTES do script principal de story.html.
 * Ele declara a constante global `QUESTS`, consumida pelo motor de
 * missões (trigger/acceptQuest/showQuestBoard) do jogo.
 *
 * Para adicionar missões, basta incluir novas chaves neste objeto.
 * Campos suportados pelo motor:
 *   id, name, description, repeatable,
 *   requires: { level, quests: ['outra_missao'] },   // usado pelo diário (systems.js)
 *   stages: [{ name, description, type, target, itemId?, required, progress, hints,
 *              onComplete?, onProgress? }]
 *       type ∈ talk_to_npc | kill_creature | collect_item | deliver_item | visit_location
 *   rewards: [{ gold, exp, item, itemQty }]
 *   stageRewards?: [{ gold, exp, item, itemQty }]  // indexado pelo estágio
 */
const QUESTS = {
    // ────────────────────────────────────────────────────────────────
    // Cadeia introdutória (continua a existir exatamente como antes)
    // ────────────────────────────────────────────────────────────────
    royal_hunt: {
        id: 'royal_hunt',
        name: '🌲 A Caçada Real',
        description: 'O Rei pede sua ajuda para eliminar as ameaças nas florestas do reino.',
        repeatable: false,
        currentStage: 0,
        stages: [
            {
                name: 'Falar com o Capitão',
                description: 'Vá até o Salão Principal e converse com o Capitão da Guarda para obter mais informações sobre a ameaça.',
                type: 'talk_to_npc',
                target: 'captain',
                required: 1,
                progress: 0,
                hints: '🗡️ O Capitão fica no Salão Principal do castelo.',
                onComplete: () => {
                    addLog('📜 Missão atualizada: O Capitão informou que lobos gigantes estão atacando os campos!');
                }
            },
            {
                name: 'Derrotar Lobos',
                description: 'Derrote 3 Lobos na Floresta Sombria para reduzir a ameaça.',
                type: 'kill_creature',
                target: 'wolf',
                required: 3,
                progress: 0,
                hints: '🐺 Lobos podem ser encontrados na Floresta Sombria (saia pelo Portão Principal e vá para o norte).',
                onProgress: (current, required) => {
                    if (current === 1) addLog(`⚔️ Você derrotou seu primeiro lobo! Faltam ${required - current}.`);
                    else if (current === required) addLog(`✨ Todos os lobos foram derrotados! Volte ao Capitão.`);
                }
            },
            {
                name: 'Reportar ao Capitão',
                description: 'Retorne ao Capitão da Guarda para receber sua recompensa.',
                type: 'talk_to_npc',
                target: 'captain',
                required: 1,
                progress: 0,
                hints: '🏰 O Capitão está no Salão Principal aguardando seu retorno.',
                onComplete: () => {
                    addLog('👑 O Capitão ficou impressionado com sua bravura!');
                }
            }
        ],
        rewards: [
            { gold: 10, exp: 25, item: 'dagger', itemQty: 1 },
        ]
    },

    // ────────────────────────────────────────────────────────────────
    // Missões secundárias (fazem o mundo parecer vivo)
    // ────────────────────────────────────────────────────────────────
    carpenter_wood: {
        id: 'carpenter_wood',
        name: '🪵 Madeira de Primeira',
        description: 'Carlos, o marceneiro, precisa de madeira de carvalho para terminar uma encomenda.',
        repeatable: true,
        requires: { level: 1 },
        stages: [
            {
                name: 'Coletar Madeira',
                description: 'Reúna 8 Madeiras (derrote criaturas ou procure em escombros) e leve a Carlos.',
                type: 'collect_item',
                target: 'wood',
                required: 8,
                progress: 0,
                hints: '🪵 Madeira aparece ao explorar ruínas e florestas.',
                onProgress: (current, required) => { if (current === required) addLog('🪵 Madeira suficiente! Volte ao marceneiro Carlos, no Vilarejo Norte.'); }
            },
            {
                name: 'Entregar a Carlos',
                description: 'Fale com Carlos no Vilarejo Norte para entregar a madeira.',
                type: 'talk_to_npc',
                target: 'carpenter',
                required: 1,
                progress: 0,
                hints: '🔨 Carlos fica no Vilarejo Norte.',
                onComplete: () => addLog('🔨 Carlos agradece e promete um desconto nas próximas encomendas!')
            }
        ],
        rewards: [{ gold: 30, exp: 40, item: 'wooden_spoon', itemQty: 1 }]
    },

    weaver_cloth: {
        id: 'weaver_cloth',
        name: '🧵 Fios da Sorte',
        description: 'Isadora, a tecelã, quer tecidos raros para tingir com cores do lago sagrado.',
        repeatable: true,
        requires: { level: 1 },
        stages: [
            {
                name: 'Reunir Tecido',
                description: 'Consiga 5 Tecidos e entregue a Isadora no Vilarejo Sul.',
                type: 'collect_item',
                target: 'cloth',
                required: 5,
                progress: 0,
                hints: '🧵 Tecido pode ser comprado com a própria Isadora ou produzido no tear.',
                onProgress: (current, required) => { if (current === required) addLog('🧵 Tecido o bastante! Fale com Isadora no Vilarejo Sul.'); }
            },
            {
                name: 'Entregar a Isadora',
                description: 'Fale com Isadora para concluir a encomenda.',
                type: 'talk_to_npc',
                target: 'weaver',
                required: 1,
                progress: 0,
                hints: '🧵 Isadora fica no Vilarejo Sul.',
                onComplete: () => addLog('🧵 Isadora tinge os tecidos e sorri satisfeita.')
            }
        ],
        rewards: [{ gold: 45, exp: 55, item: 'coffee', itemQty: 2 }]
    },

    pedro_map: {
        id: 'pedro_map',
        name: '🗺️ Mapas do Velho Pedro',
        description: 'O cartógrafo Pedro quer confirmar três locais lendários do mundo.',
        repeatable: false,
        requires: { level: 2 },
        stages: [
            {
                name: 'Visitar o Lago Sagrado',
                description: 'Vá até a clareira do Lago Sagrado (trilha sul, pelos fundos do reino).',
                type: 'visit_location',
                target: 'sacred_lake',
                required: 1,
                progress: 0,
                hints: '💧 Atravesse a Ponte Oeste, use o Portão Secundário e siga a Trilha Sul.',
                onComplete: () => addLog('💧 Você confirma o local sagrado para os mapas de Pedro.')
            },
            {
                name: 'Visitar o Cemitério Abandonado',
                description: 'Vá até o Cemitério Abandonado (trilha norte, pelos fundos do reino).',
                type: 'visit_location',
                target: 'abandoned_cemetery',
                required: 1,
                progress: 0,
                hints: '🪦 Siga a Trilha Norte até o portão do cemitério.',
                onComplete: () => addLog('🪦 Você registra o cemitério antigo no mapa.')
            },
            {
                name: 'Visitar a Entrada da Floresta Sombria',
                description: 'Alcance a Entrada da Floresta Sombria, ao norte das ruínas.',
                type: 'visit_location',
                target: 'north_forest_edge',
                required: 1,
                progress: 0,
                hints: '🌲 Atravesse a ponte ao norte do rio e continue até a floresta.',
                onComplete: () => addLog('🌲 Local confirmado. Pedro vai adorar as anotações!')
            },
            {
                name: 'Voltar a Pedro',
                description: 'Fale com o cartógrafo Pedro no Vilarejo Sul para entregar as anotações.',
                type: 'talk_to_npc',
                target: 'cartographer',
                required: 1,
                progress: 0,
                hints: '🗺️ Pedro fica no Vilarejo Sul.',
                onComplete: () => addLog('🗺️ Pedro estuda suas anotações e sorri de orelha a orelha.')
            }
        ],
        rewards: [{ gold: 60, exp: 80, item: 'map', itemQty: 1 }]
    },

    // ────────────────────────────────────────────────────────────────
    // CAMPANHA PRINCIPAL — "A Sombra de Duas Coroas"
    // Tom híbrido: o Rei Mago brincalhão, mas a ameaça é real e sombria.
    // Baseada em docs/lore.md (Aurora × Crepúsculo, o Mago Negro).
    // ────────────────────────────────────────────────────────────────
    main_two_crowns: {
        id: 'main_two_crowns',
        name: '👑 A Sombra de Duas Coroas',
        description: 'Rumores vêm do sul: o Crepúsculo se move. O Rei Mago quer alguém de confiança — e insiste que não é por medo.',
        repeatable: false,
        requires: { level: 2 },
        stages: [
            {
                name: 'Um chamado nada cerimonial',
                description: 'Fale com o Rei Mago Luthor na Sala do Trono.',
                type: 'talk_to_npc',
                target: 'king',
                required: 1,
                progress: 0,
                hints: '👑 A Sala do Trono fica no alto do Castelo Real.',
                onComplete: () => {
                    addLog('👑 Rei Luthor: "Conversa séria agora. Sem piada." (Ele ri mesmo assim.)');
                    addLog('📜 "Vá falar com o Capitão Aldric. Ele tem os mapas do que está por vir."');
                }
            },
            {
                name: 'O briefing do Capitão',
                description: 'Fale com o Capitão da Guarda no Salão Principal.',
                type: 'talk_to_npc',
                target: 'captain',
                required: 1,
                progress: 0,
                hints: '🗡️ O Capitão fica no Salão Principal.',
                onComplete: () => {
                    addLog('🗡️ Capitão Aldric: "Goblins nas ruínas. Orcs na Floresta Sombria. E algo gigante ao norte."');
                    addLog('💡 Comece pelas ruínas antigas, além da ponte norte.');
                }
            },
            {
                name: 'Limpar as ruínas',
                description: 'Derrote 4 Goblins nos arredores das Ruínas Antigas.',
                type: 'kill_creature',
                target: 'goblin',
                required: 4,
                progress: 0,
                hints: '👺 Goblins infestam as Ruínas Antigas e o Caminho Leste. Explore para encontrá-los.',
                onProgress: (current, required) => {
                    if (current === 1) addLog('👺 Primeiro goblin abatido! Faltam ' + (required - current) + '.');
                    else if (current === required) addLog('🌟 Ruínas mais seguras. As notas do Capitão fazem sentido agora.');
                }
            },
            {
                name: 'Reconhecer a floresta',
                description: 'Chegue à Entrada da Floresta Sombria, ao norte das ruínas.',
                type: 'visit_location',
                target: 'north_forest_edge',
                required: 1,
                progress: 0,
                hints: '🌲 Ao norte das Ruínas Antigas fica a entrada da floresta.',
                onComplete: () => addLog('🌲 Uivos ao longe. Orcs acampam na escuridão — e algo maior respira mais fundo.')
            },
            {
                name: 'Quebrar o cerco orc',
                description: 'Derrote 3 Orcs na Floresta Sombria.',
                type: 'kill_creature',
                target: 'orc',
                required: 3,
                progress: 0,
                hints: '👹 Orcs aparecem ao explorar a Floresta Sombria.',
                onProgress: (current, required) => {
                    if (current === required) addLog('⚔️ O cerco orc se desfaz. Resta o que ruge nas alturas.');
                }
            },
            {
                name: 'O Pico do Dragão',
                description: 'Suba ao Pico do Dragão e derrote a fera que ameaça o reino.',
                type: 'kill_creature',
                target: 'dragon',
                required: 1,
                progress: 0,
                hints: '🐉 Da Entrada da Floresta Sombria, siga para o Pico do Dragão.',
                onProgress: (current, required) => {
                    if (current >= required) {
                        addLog('🐉 O dragão cai. O vale inteiro treme — como nas lendas de Orion.');
                        addLog('📜 Leve a prova ao Rei. Ele precisa ouvir o que vem agora.');
                    }
                }
            },
            {
                name: 'O que o Rei não disse',
                description: 'Reporte ao Rei Mago Luthor na Sala do Trono.',
                type: 'talk_to_npc',
                target: 'king',
                required: 1,
                progress: 0,
                hints: '👑 Volte à Sala do Trono.',
                onComplete: () => {
                    addLog('👑 Rei Luthor fica sério pela primeira vez: "Agora você entende."');
                    addLog('📜 "Os ataques eram isca. O Mago Negro do Crepúsculo quer a Aurora dobrada outra vez."');
                    addLog('⚠️ "Se você for ao sul... talvez não volte. Pense nisso. Eu espero — mas não muito."');
                }
            },
            {
                name: 'A Cidadela do Crepúsculo',
                description: 'Viaje ao sul e enfrente o Mago Negro na Cidadela do Crepúsculo.',
                type: 'kill_creature',
                target: 'black_mage',
                required: 1,
                progress: 0,
                hints: '🌑 Pegue a Estrada Comercial Sul → Portão do Crepúsculo → Cidadela. Prepare-se bem.',
                onProgress: (current, required) => {
                    if (current >= required) {
                        addLog('🌑 O Mago Negro se desfaz em sombra e cinza. O céu clareia.');
                        if (typeof twilightEndingChoice === 'function') setTimeout(twilightEndingChoice, 700);
                    }
                }
            }
        ],
        rewards: [
            { gold: 800, exp: 2500, item: 'twilight_crown', itemQty: 1 }
        ]
    }
};
