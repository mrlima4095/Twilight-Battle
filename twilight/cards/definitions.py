"""Definições de cartas, disfarces de armadilha e modificadores de sala."""

CARDS = {
    # Criaturas
    # - Tropas
    "elfo": {
        "id": "elfo",
        "name": "Elfo",
        "type": "creature",
        "life": 512, 
        "attack": 50,
        "count": 50, 
        "description": "Não ataca outros elfos. Use para realizar oraculos."
    },
    "mago": {
        "id": "mago",
        "name": "Mago",
        "type": "creature", 
        "life": 512, 
        "attack": 50, 
        "count": 50, 
        "description": "Use-o para invocar feitiços."
    },
    "orc": {
        "id": "orc",
        "name": "Orc",
        "type": "creature",
        "life": 512,
        "attack": 60,
        "count": 50,
        "description": "Brutais."
    },
    "zumbi": {
        "id": "zumbi", 
        "name": "Zumbi",
        "type": "creature",
        "life": 100, 
        "attack": 25,
        "count": 50, 
        "description": "Morre durante o dia. A menos que derrotado por outro zumbi volta para a mão do jogador.", 
        "dies_daylight": True
    },
    "centauro": {
        "id": "centauro",
        "name": "Centauro", 
        "type": "creature", 
        "life": 512, 
        "attack": 70, 
        "count": 50, 
        "description": "O jogador pode colocar personagens para montar no centauro. Realiza qualquer ataque terrestre."
    },
    "ninfa": {
        "id": "ninfa",
        "name": "Ninfa",
        "type": "creature",
        "life": 512,
        "attack": 30,
        "count": 35,
        "description": "Espiritos Magicos da Natureza"
    },
    "vampiro": {
        "id": "vampiro", 
        "name": "Vampiro", 
        "type": "creature", 
        "life": 512, 
        "attack": 75, 
        "count": 1, 
        "description": "Criatura noturna.", 
        "dies_daylight": True
    },
    
    # -- Especiais
    "vampiro_wers": {
        "id": "vampiro_wers", 
        "name": "Vampiro - Benjamim Wers", 
        "type": "creature", 
        "life": 512, 
        "attack": 250, 
        "count": 1, 
        "description": "Mata todos os centauros em campo dos oponentes e entrega a vida a jogador.", 
        "dies_daylight": True
    },
    "vampiro_tayler": {
        "id": "vampiro_tayler", 
        "name": "Vampiro - Necrothic Tayler", 
        "type": "creature", 
        "life": 512, 
        "attack": 100, 
        "count": 1, 
        "description": "Rouba a vida do oponente para recuperar a vida de seu jogador.", 
        "dies_daylight": True
    },

    "ninfa_lorem": {
        "id": "ninfa", 
        "name": "Ninfa - Belly Lorem", 
        "type": "creature", 
        "life": 512, 
        "attack": 128, 
        "count": 1, 
        "description": "Torna o jogador imune a rituais."
    },
    
    # - Mestres
    "rei_mago": {
        "id": "rei_mago", 
        "name": "Rei Mago", 
        "type": "creature", 
        "life": 1250, 
        "attack": 512, 
        "count": 1, 
        "description": "Pode impedir outros magos de realizar feitiços. Realiza feitiços sem possuir a carta."
    },
    "mago_negro": {
        "id": "mago_negro", 
        "name": "Mago Negro", 
        "type": "creature", 
        "life": 1250, 
        "attack": 510, 
        "count": 1, 
        "description": "Não se subordina ao Rei Mago. Realiza rituais sem possuir a carta."
    },
    
    "apollo": {
        "id": "apollo", 
        "name": "Apollo", 
        "type": "creature", 
        "life": 1500, 
        "attack": 600, 
        "count": 1, 
        "description": "Ataques sofridos com menos de 1k de dano recuperam a vida do jogador se colocado na defesa."
    },
    
    # - Bestas
    "dragao": {
        "id": "dragao", 
        "name": "Dragão", 
        "type": "creature", 
        "life": 1500, 
        "attack": 250, 
        "count": 12, 
        "description": "Seu ataque incendeia o inimigo, com isso ele toma 50 de danos nas próximas rodadas do fogo."
    },
    "leviatan": {
        "id": "leviatan", 
        "name": "Leviatã", 
        "type": "creature", 
        "life": 5000, 
        "attack": 1024, 
        "count": 1, 
        "description": "Só pode ser domado por deuses e magos supremos."
    },
    "apofis": {
        "id": "apofis", 
        "name": "Apofis", 
        "type": "creature", 
        "life": 5000, 
        "attack": 1250, 
        "count": 1, 
        "description": "Rei do Caos. Pode desativar armadilhas e magias de outros jogadores."
    },
    "fenix": {
        "id": "fenix", 
        "name": "Fênix", 
        "type": "creature", 
        "life": 5000, 
        "attack": 1500, 
        "count": 1, 
        "description": "Grande ave com ataque de fogo, pode mudar de dia para noite e vice-versa quando bem entender."
    },

    "medusa": {
        "id": "medusa", 
        "name": "Medusa", 
        "type": "creature", 
        "life": 1024, 
        "attack": 512, 
        "count": 1, 
        "description": "Seu ataque transforma personagens em pedra. Cartas com maior vida são imunes."
    },
    
    "profeta": {
        "id": "profeta", 
        "name": "Profeta", 
        "type": "creature", 
        "life": 256, 
        "attack": 50, 
        "count": 2, 
        "description": "Anuncia a morte de um monstro para duas rodadas a frente. A maldição pode ser retirada caso o jogador seja derrotado."
    },
    
    "super_centauro": {
        "id": "super_centauro", 
        "name": "Super Centauro", 
        "type": "creature", 
        "life": 600, 
        "attack": 256, 
        "count": 5, 
        "description": "Apenas ataques diretos. Pode encantar centauros de outros jogadores e pegar eles para a sua mão (os centauros que estão em campo)"
    },
    
    # Itens/Espadas
    "lamina_almas": {
        "id": "lamina_almas", 
        "name": "Lâmina das Almas", 
        "type": "weapon", 
        "attack": 0, 
        "count": 1, 
        "description": "Assume o dano de uma carta do cemitério. Só pode ser equipado por Elfos, magos e vampiros."
    },

    "espada_madeira": {
        "id": "espada_madeira",
        "name": "Espada de Madeira",
        "type": "weapon",
        "attack": 128,
        "count": 40,
        "description": "Espada de treino. Fraca, mas melhor que as mãos vazias."
    },
    "espada_ferro": {
        "id": "espada_ferro",
        "name": "Espada de Ferro",
        "type": "weapon",
        "attack": 256,
        "count": 35,
        "description": "Uma espada padrão para seus soldados."
    },
    "katana": {
        "id": "katana",
        "name": "Katana",
        "type": "weapon",
        "attack": 512,
        "count": 18,
        "description": "Lâmina afiada de corte limpo. Bom equilíbrio entre poder e disponibilidade."
    },

    "clava_orc": {
        "id": "clava_orc",
        "name": "Clava do Orc",
        "type": "weapon",
        "attack": 350,
        "count": 22,
        "ability": "orc_club",
        "orc_bonus": 50,
        "orc_bonus_cap": 3,
        "description": "350⚔️ base. +50⚔️ por Orc em bases de ataque (máx. 3 orcs = +150)."
    },
    "cajado_mago_negro": {
        "id": "cajado_mago_negro",
        "name": "Cajado do Mago Negro",
        "type": "weapon",
        "attack": 100,
        "count": 12,
        "ability": "dark_staff",
        "spell_power": 256,
        "equip_races": ["mago", "mago_negro", "rei_mago"],
        "description": "100⚔️. Só magos. Seus feitiços de cura/buff ganham +256 de poder."
    },
    "adaga_crepusculo": {
        "id": "adaga_crepusculo",
        "name": "Adaga do Crepúsculo",
        "type": "weapon",
        "attack": 150,
        "day_attack": 150,
        "night_attack": 600,
        "count": 14,
        "ability": "crepusculo_dagger",
        "werewolf_only": True,
        "description": "Só Lobisomem do Crepúsculo. De dia 150⚔️; de noite 600⚔️. O poder muda com o ciclo."
    },
    
    "blade_vampires": {
        "id": "blade_vampires", 
        "name": "Blade of Vampires", 
        "type": "weapon", 
        "attack": 1500, 
        "count": 1, 
        "description": "Só pode ser usada por um vampiro. Seu ataque torna o oponente noturno (morre de dia)"
    },
    "blade_dragons": {
        "id": "blade_dragons", 
        "name": "Blade of Dragons", 
        "type": "weapon", 
        "attack": 1500, 
        "count": 1, 
        "description": "Usada apenas por elfos ou vampiros. Seu ataque pode eliminar personagens permanentemente tornando impossíveis de reviver ou ser invocados de volta do cemitério."
    },
    
    # Armaduras/Equipamentos
    "capacete_trevas": {
        "id": "capacete_trevas", 
        "name": "Capacete das Trevas", 
        "type": "armor",
        "slot": "helmet",
        "protection": 300, 
        "count": 20,
        "daylight_protect": True,
        "description": "Impede o dano da luz do dia em mortos-vivos e a proteção é adicionada à carta."
    },
    "capacete_sentinela": {
        "id": "capacete_sentinela",
        "name": "Capacete da Sentinela",
        "type": "armor",
        "slot": "helmet",
        "protection": 180,
        "count": 18,
        "ability": "first_hit_reduce",
        "first_hit_reduce": 80,
        "description": "Só vale equipado. +180 proteção. Equipado no capacete do jogador: 1× por turno o primeiro dano à vida é −80. Equipado em criatura: +180 de vida nela."
    },
    "peitoral_carvalho": {
        "id": "peitoral_carvalho",
        "name": "Peitoral de Carvalho",
        "type": "armor",
        "slot": "armor",
        "protection": 350,
        "count": 16,
        "ability": "nature_ward",
        "spell_resist_races": ["elfo", "ninfa", "ninfa_lorem"],
        "description": "Só vale equipado. +350 proteção na criatura. Em Elfo ou Ninfa: a criatura ignora o próximo feitiço hostil."
    },
    "peitoral_ferro": {
        "id": "peitoral_ferro",
        "name": "Peitoral de Ferro",
        "type": "armor",
        "slot": "armor",
        "protection": 220,
        "count": 25,
        "description": "Só vale equipado. Armadura comum: +220 vida na criatura equipada."
    },
    "calcas_marcha": {
        "id": "calcas_marcha",
        "name": "Calças da Marcha",
        "type": "armor",
        "slot": "pants",
        "protection": 150,
        "count": 18,
        "ability": "damage_flat_reduce",
        "damage_flat_reduce": 40,
        "description": "Só vale equipado no slot Calças do jogador (não na mão). Todo dano à vida do jogador é reduzido em 40. Na criatura: +150 vida."
    },
    "botas_andarilho": {
        "id": "botas_andarilho",
        "name": "Botas do Andarilho",
        "type": "armor",
        "slot": "boots",
        "protection": 80,
        "count": 14,
        "ability": "free_swap",
        "description": "Só vale equipado no slot Botas do jogador (não na mão). 1 troca grátis ataque↔defesa por turno. Na criatura: +80 vida."
    },
    "botas_guerra": {
        "id": "botas_guerra",
        "name": "Botas de Guerra",
        "type": "armor",
        "slot": "boots",
        "protection": 120,
        "count": 16,
        "ability": "charge_bonus",
        "attack_bonus": 40,
        "description": "Só vale equipado na criatura em ATAQUE: +120 vida e +40 ataque. Na mão não faz nada."
    },
    "manto_eclipse": {
        "id": "manto_eclipse",
        "name": "Manto do Eclipse",
        "type": "armor",
        "slot": "armor",
        "protection": 200,
        "count": 10,
        "daylight_protect": True,
        "ability": "eclipse_cloak",
        "description": "Só vale equipado (criatura ou peitoral do jogador). +200 proteção e impede morte/dano da luz do dia em noturnos. Na mão não protege."
    },

    # Lobisomem
    "lobisomem_crepusculo": {
        "id": "lobisomem_crepusculo",
        "name": "Lobisomem do Crepúsculo",
        "type": "creature",
        "life": 700,
        "attack": 40,
        "count": 18,
        "werewolf": True,
        "day_life": 700,
        "day_attack": 40,
        "night_life": 480,
        "night_attack": 170,
        "description": "De dia: tanque (700❤️ / 40⚔️). De noite: predador (480❤️ / 170⚔️). Forma muda com o ciclo."
    },
    
    # Talismãs (não podem ser jogados, apenas segurados)
    "talisma_ordem": {
        "id": "talisma_ordem", 
        "name": "Talismã - Ordem", 
        "type": "talisman", 
        "count": 1, 
        "description": "Imunidade ao Caos."
    },
    "talisma_imortalidade": {
        "id": "talisma_imortalidade", 
        "name": "Talismã - Imortalidade", 
        "type": "talisman", 
        "count": 1, 
        "uses_left": 2,
        "description": "Se o jogador for morto com este item em mãos ele terá seus pontos de vida restaurados."
    },
    "talisma_verdade": {
        "id": "talisma_verdade", 
        "name": "Talismã - Verdade", 
        "type": "talisman", 
        "count": 1, 
        "description": "Imunidade a feitiços e oráculos."
    },
    "talisma_guerreiro": {
        "id": "talisma_guerreiro", 
        "name": "Talismã - Guerreiro", 
        "type": "talisman", 
        "count": 1, 
        "description": "Aumenta em 1024 pontos o ataque e defesa do jogador."
    },
    "talisma_sabedoria": {
        "id": "talisma_sabedoria", 
        "name": "Talismã - Sabedoria", 
        "type": "talisman", 
        "count": 1, 
        "description": "Permite jogar duas cartas por turno (em vez de uma)."
    },
    
    # Runas
    "runa": {
        "id": "runa", 
        "name": "Runa", 
        "type": "rune",
        "count": 40, 
        "description": "Colete quatro runas para realizar uma invocação de um personagem do cemitério."
    },
    
    # Feitiços
    "feitico_cortes": {
        "id": "feitico_cortes", 
        "name": "Feitiço - Cortes", 
        "type": "spell", 
        "count": 2, 
        "description": "Aumenta ataque de um monstro em 1024 pontos por duas rodadas."
    },
    "feitico_duro_matar": {
        "id": "feitico_duro_matar", 
        "name": "Feitiço - Duro de matar", 
        "type": "spell", 
        "count": 2, 
        "description": "Aumenta defesa do jogador em 1024 pontos por duas rodadas."
    },
    "feitico_troca": {
        "id": "feitico_troca", 
        "name": "Feitiço - Troca", 
        "type": "spell", 
        "count": 2, 
        "description": "Troca as cartas de outro Jogador de ataque para defesa e vice-versa."
    },
    "feitico_comunista": {
        "id": "feitico_comunista", 
        "name": "Feitiço - Comunista", 
        "type": "spell", 
        "count": 2, 
        "description": "Faz as cartas das mãos dos jogadores irem de volta para a pilha."
    },
    "feitico_silencio": {
        "id": "feitico_silencio", 
        "name": "Feitiço - Silêncio", 
        "type": "spell", 
        "count": 2, 
        "description": "Os ataques das próximas duas rodadas não ativam armadilhas."
    },
    "feitico_para_sempre": {
        "id": "feitico_para_sempre", 
        "name": "Feitiço - Para Sempre", 
        "type": "spell", 
        "count": 2, 
        "description": "Reverte o efeito da espada Blade of Vampires."
    },
    "feitico_capitalista": {
        "id": "feitico_capitalista", 
        "name": "Feitiço - Capitalista", 
        "type": "spell", 
        "count": 2, 
        "description": "Troque cartas com outros jogadores."
    },
    "feitico_cura": {
        "id": "feitico_cura", 
        "name": "Feitiço - Cura", 
        "type": "spell", 
        "count": 10, 
        "description": "Cura 1024 pontos de vida do jogador alvo. Pode ser usado em si mesmo ou em outros jogadores."
    },
    "feitico_clareira_lua": {
        "id": "feitico_clareira_lua",
        "name": "Feitiço - Clareira da Lua",
        "type": "spell",
        "count": 6,
        "description": "Força a noite imediatamente. Lobisomens e criaturas noturnas se beneficiam."
    },
    "feitico_julgamento_aurora": {
        "id": "feitico_julgamento_aurora",
        "name": "Feitiço - Julgamento da Aurora",
        "type": "spell",
        "count": 5,
        "description": "Destrói 1 criatura noturna no campo (zumbi, vampiro, lobisomem ou dies_daylight / night_creature)."
    },
    "feitico_eco_grimorio": {
        "id": "feitico_eco_grimorio",
        "name": "Feitiço - Eco do Grimório",
        "type": "spell",
        "count": 3,
        "description": "Copia o efeito do último feitiço usado nesta partida (exceto o próprio Eco)."
    },
    "feitico_selo_silencio": {
        "id": "feitico_selo_silencio",
        "name": "Feitiço - Selo de Silêncio Menor",
        "type": "spell",
        "count": 6,
        "description": "Seu próximo ataque não ativa armadilhas. Counter do Poço Sem Fundo e similares."
    },
    
    # Oraculo
    "oraculo_imortalidade": {
        "id": "oraculo_imortalidade", 
        "name": "Oráculo", 
        "type": "oracle", 
        "count": 1, 
        "description": "Se você atacar um jogador que possui o Talismã da Imortalidade, o talismã é anulado e o jogador morre como qualquer outro. O Oráculo é consumido após o uso. Requer elfo em modo de defesa."
    },
    
    # Rituais (requerem condições específicas)
    "ritual_157": {
        "id": "ritual_157", 
        "name": "Ritual 157", 
        "type": "ritual", 
        "count": 1, 
        "description": "Requer Apofis, Mago Negro, 2 zumbis e 2 elfos em modo de defesa. Todos os talismãs da mão do jogador escolhido são roubados."
    },
    "ritual_amor": {
        "id": "ritual_amor", 
        "name": "Ritual Amor", 
        "type": "ritual", 
        "count": 1, 
        "description": "Requer a Ninfa Belly Lorem e o Vampiro Necrothic Tayler. Anula a maldição do Profeta."
    },
    "ritual_chaos": {
        "id": "ritual_chaos",
        "name": "Ritual do Caos",
        "type": "ritual",
        "count": 1,
        "description": "Requer Apofis e o Mago Negro. Invoca o Caos."
    },

    # Armadilhas
    "armadilha_171": {
        "id": "armadilha_171", 
        "name": "Armadilha 171", 
        "type": "trap", 
        "count": 2, 
        "description": "Rouba a carta que te dá um golpe crítico."
    },
    "armadilha_espelho": {
        "id": "armadilha_espelho", 
        "name": "Armadilha Espelho", 
        "type": "trap", 
        "count": 2, 
        "description": "Reverte ataques e magia."
    },
    "armadilha_cheat": {
        "id": "armadilha_cheat", 
        "name": "Armadilha Cheat", 
        "type": "trap", 
        "count": 2, 
        "description": "Dobrar o ataque e passar para o próximo jogador na rodada, precisa estar de noite e um mago em campo."
    },
    "armadilha_poco": {
        "id": "armadilha_poco", 
        "name": "Armadilha - Poço Sem Fundo", 
        "type": "trap", 
        "count": 2, 
        "description": "Quando o oponente atacar, TODAS as 3 criaturas atacantes são destruídas e enviadas para o cemitério. Armadilha é desativada após o uso."
    }
}

DISGUISE_OPTIONS = [
    {
        "id": "elfo",
        "name": "Elfo",
        "type": "creature",
        "life": 512, 
        "attack": 50,
        "count": 50, 
        "description": "Não ataca outros elfos. Use para realizar oraculos."
    },
    {
        "id": "mago",
        "name": "Mago",
        "type": "creature", 
        "life": 512, 
        "attack": 50, 
        "count": 50, 
        "description": "Use-o para invocar feitiços."
    },
    {
        "id": "orc",
        "name": "Orc",
        "type": "creature",
        "life": 512,
        "attack": 60,
        "count": 50,
        "description": "Brutais."
    },
    {
        "id": "zumbi", 
        "name": "Zumbi",
        "type": "creature",
        "life": 100, 
        "attack": 25,
        "count": 50, 
        "description": "Morre durante o dia. A menos que derrotado por outro zumbi volta para a mão do jogador.", 
        "dies_daylight": True
    },
    {
        "id": "centauro",
        "name": "Centauro", 
        "type": "creature", 
        "life": 512, 
        "attack": 70, 
        "count": 50, 
        "description": "O jogador pode colocar personagens para montar no centauro. Realiza qualquer ataque terrestre."
    },
    {
        "id": "ninfa",
        "name": "Ninfa",
        "type": "creature",
        "life": 512,
        "attack": 30,
        "count": 35,
        "description": "Espiritos Magicos da Natureza"
    }
]

MODIFIERS = [
    {
        'id': 'empty_hand',
        'name': 'Mão Vazia',
        'description': 'Jogadores começam a partida sem nenhuma carta na mão',
        'icon': '🃏',
        'enabled': True
    },
    {
        'id': 'big_hand',
        'name': 'Mão Cheia',
        'description': 'Jogadores começam com 8 cartas na mão (em vez de 5)',
        'icon': '🎴',
        'enabled': True
    },
    {
        'id': 'no_runes',
        'name': 'Sem Runas',
        'description': 'As cartas de Runa não podem reviver do cemitério',
        'icon': '🔷',
        'enabled': True
    },
    {
        'id': 'disable_daycicle',
        'name': 'Desativar Ciclo de Dia/Noite',
        'description': 'Sempre dia ou noite até um jogador alterar',
        'icon': '☀️',
        'enabled': True
    },
    {
        'id': 'fast_cycle',
        'name': 'Crepúsculo Acelerado',
        'description': 'O ciclo dia/noite muda a cada 6 turnos (em vez de 24)',
        'icon': '⏱️',
        'enabled': True
    },
    {
        'id': 'disable_traps',
        'name': 'Desativar Armadilhas',
        'description': 'Não haverá cartas de armadilha no jogo',
        'icon': '🕳️',
        'enabled': True
    },
    {
        'id': 'no_first_round',
        'name': 'Sem Preparação',
        'description': 'Ataques liberados desde o primeiro turno (sem rodada de preparação)',
        'icon': '⚔️',
        'enabled': True
    },
    {
        'id': 'hardcore',
        'name': 'Hardcore',
        'description': 'Jogadores começam com apenas 600 de vida',
        'icon': '💀',
        'enabled': True
    },
    {
        'id': 'bleed_out',
        'name': 'Sangria',
        'description': 'No fim do seu turno, se você não atacou, perde 20 de vida',
        'icon': '🩸',
        'enabled': True
    },
    {
        'id': 'no_legendaries',
        'name': 'Sem Lendas',
        'description': 'Cartas únicas (count 1) não entram no baralho — sem Rei Mago, dragões, etc.',
        'icon': '📜',
        'enabled': True
    },
    {
        'id': 'no_equipment',
        'name': 'Desarmados',
        'description': 'Armas e armaduras não entram no baralho',
        'icon': '🚫',
        'enabled': True
    },
    {
        'id': 'no_spells',
        'name': 'Mordaça',
        'description': 'Feitiços não entram no baralho',
        'icon': '🤐',
        'enabled': True
    },
    {
        'id': 'no_prophet',
        'name': 'Sem Profecia',
        'description': 'A habilidade Profetizar está desativada',
        'icon': '🔮',
        'enabled': True
    },
    {
        'id': 'open_field',
        'name': 'Campo Aberto',
        'description': 'Apenas 1 base de defesa (em vez de 6)',
        'icon': '🏞️',
        'enabled': True
    },
    {
        'id': 'war_front',
        'name': 'Frente de Guerra',
        'description': '5 bases de ataque (em vez de 3)',
        'icon': '🏰',
        'enabled': True
    },
    {
        'id': 'fog_of_war',
        'name': 'Névoa de Guerra',
        'description': 'Você não vê nome, vida nem ataque das criaturas inimigas — só silhueta',
        'icon': '🌫️',
        'enabled': True
    },
    {
        'id': 'king_hunt',
        'name': 'Caça ao Rei',
        'description': 'Quem eliminar o criador da sala ganha +300 de vida',
        'icon': '👑',
        'enabled': True
    },
]

