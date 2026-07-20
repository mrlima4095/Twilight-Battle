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
        "description": "Tropa (50⚔️ / 512❤️). Em campo: habilita Oráculo se estiver em defesa. Não ataca outros elfos."
    },
    "mago": {
        "id": "mago",
        "name": "Mago",
        "type": "creature", 
        "life": 512, 
        "attack": 50, 
        "count": 50, 
        "description": "Tropa (50⚔️ / 512❤️). Em campo (ataque ou defesa): permite lançar feitiços da mão (1 feitiço por turno)."
    },
    "orc": {
        "id": "orc",
        "name": "Orc",
        "type": "creature",
        "life": 512,
        "attack": 60,
        "count": 50,
        "description": "Tropa bruta (60⚔️ / 512❤️). Sinergia com Clava do Orc (+50⚔️ por orc em bases de ataque, máx. 3)."
    },
    "zumbi": {
        "id": "zumbi", 
        "name": "Zumbi",
        "type": "creature",
        "life": 100, 
        "attack": 25,
        "count": 50, 
        "description": "Criatura noturna fraca (25⚔️ / 100❤️). Morre ao virar o DIA se não tiver proteção solar (Capacete das Trevas / Manto do Eclipse). Se destruído por outro zumbi, pode voltar à mão.", 
        "dies_daylight": True
    },
    "centauro": {
        "id": "centauro",
        "name": "Centauro", 
        "type": "creature", 
        "life": 512, 
        "attack": 70, 
        "count": 50, 
        "description": "Tropa (70⚔️ / 512❤️). Pode ser montaria (slot mount do jogador) ou chamada em grupo (Chamar Centauros com 2+). Super Centauro pode roubar centauros em campo."
    },
    "ninfa": {
        "id": "ninfa",
        "name": "Ninfa",
        "type": "creature",
        "life": 512,
        "attack": 30,
        "count": 35,
        "description": "Espírito da natureza (30⚔️ / 512❤️). Sinergia com Peitoral de Carvalho (ward contra feitiço hostil)."
    },
    "vampiro": {
        "id": "vampiro", 
        "name": "Vampiro", 
        "type": "creature", 
        "life": 512, 
        "attack": 75, 
        "count": 1, 
        "description": "Criatura noturna rara (75⚔️ / 512❤️). Morre com a luz do dia sem proteção solar.", 
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
        "description": "Lenda (250⚔️ / 512❤️). Noturno (morre de dia sem proteção). Ao entrar em jogo: destrói centauros inimigos em campo e cura o dono com a vida deles.", 
        "dies_daylight": True
    },
    "vampiro_tayler": {
        "id": "vampiro_tayler", 
        "name": "Vampiro - Necrothic Tayler", 
        "type": "creature", 
        "life": 512, 
        "attack": 100, 
        "count": 1, 
        "description": "Lenda (100⚔️ / 512❤️). Noturno. Ao atacar: rouba vida do oponente para curar o dono. Usado no Ritual Amor com Ninfa Belly Lorem.", 
        "dies_daylight": True
    },

    "ninfa_lorem": {
        "id": "ninfa", 
        "name": "Ninfa - Belly Lorem", 
        "type": "creature", 
        "life": 512, 
        "attack": 128, 
        "count": 1, 
        "description": "Lenda (128⚔️ / 512❤️). Enquanto em campo, o dono é imune a rituais hostis. Usada no Ritual Amor com Vampiro Necrothic Tayler."
    },
    
    # - Mestres
    "rei_mago": {
        "id": "rei_mago", 
        "name": "Rei Mago", 
        "type": "creature", 
        "life": 1250, 
        "attack": 512, 
        "count": 1, 
        "description": "Mestre (512⚔️ / 1250❤️). Conta como mago para feitiços; pode bloquear magos rivais e lançar feitiços sem a carta (regras especiais de lenda)."
    },
    "mago_negro": {
        "id": "mago_negro", 
        "name": "Mago Negro", 
        "type": "creature", 
        "life": 1250, 
        "attack": 510, 
        "count": 1, 
        "description": "Mestre (510⚔️ / 1250❤️). Conta como mago. Não se subordina ao Rei Mago. Usado em rituais (Caos, 157) sem precisar da carta de ritual em alguns casos."
    },
    
    "apollo": {
        "id": "apollo", 
        "name": "Apollo", 
        "type": "creature", 
        "life": 1500, 
        "attack": 600, 
        "count": 1,
        "ability": "apollo_guard",
        "apollo_guard_threshold": 1000,
        "description": "Guardião (600⚔️ / 1500❤️). Em DEFESA: se um golpe com menos de 1000 de poder o atingir, o JOGADOR cura o valor total do golpe e Apollo sofre só metade do dano."
    },
    
    # - Bestas
    "dragao": {
        "id": "dragao", 
        "name": "Dragão", 
        "type": "creature", 
        "life": 1500, 
        "attack": 250, 
        "count": 12, 
        "description": "Besta (250⚔️ / 1500❤️). Ataque aplica queimadura: o alvo toma 50 de dano de fogo em rodadas seguintes."
    },
    "leviatan": {
        "id": "leviatan", 
        "name": "Leviatã", 
        "type": "creature", 
        "life": 5000, 
        "attack": 1024, 
        "count": 1, 
        "description": "Titã (1024⚔️ / 5000❤️). Carta única colossal — só entra no baralho se lendas estiverem ativas."
    },
    "apofis": {
        "id": "apofis", 
        "name": "Apofis", 
        "type": "creature", 
        "life": 5000, 
        "attack": 1250, 
        "count": 1, 
        "description": "Rei do Caos (1250⚔️ / 5000❤️). Pode anular armadilhas/magias rivais. Peça de Ritual 157 e Ritual do Caos."
    },
    "fenix": {
        "id": "fenix", 
        "name": "Fênix", 
        "type": "creature", 
        "life": 5000, 
        "attack": 1500, 
        "count": 1, 
        "description": "Ave lendária (1500⚔️ / 5000❤️). Ação toggle_time: alterna dia↔noite (1× por turno, se a carta permitir)."
    },

    "medusa": {
        "id": "medusa", 
        "name": "Medusa", 
        "type": "creature", 
        "life": 1024, 
        "attack": 512, 
        "count": 1, 
        "description": "Lenda (512⚔️ / 1024❤️). Ataque pode transformar criaturas em pedra; alvos com muita vida são imunes."
    },
    
    "profeta": {
        "id": "profeta", 
        "name": "Profeta", 
        "type": "creature", 
        "life": 256, 
        "attack": 50, 
        "count": 2, 
        "description": "Suporte (50⚔️ / 256❤️). Habilidade Profetizar: amaldiçoa uma criatura visível para morrer em 2 rodadas (se o dono do Profeta cair, a maldição pode cair)."
    },
    
    "super_centauro": {
        "id": "super_centauro", 
        "name": "Super Centauro", 
        "type": "creature", 
        "life": 600, 
        "attack": 256, 
        "count": 5, 
        "description": "Elite (256⚔️ / 600❤️). Ataques diretos; pode encantar e roubar centauros inimigos que estejam em campo para a sua mão."
    },
    
    # Itens/Espadas
    "lamina_almas": {
        "id": "lamina_almas", 
        "name": "Lâmina das Almas", 
        "type": "weapon", 
        "attack": 0, 
        "count": 1, 
        "description": "Arma (0⚔️ base). Só equipável em Elfo, Magos ou Vampiros (Tayler/Wers). Copia o ataque de uma carta do cemitério ao equipar/usar."
    },

    "espada_madeira": {
        "id": "espada_madeira",
        "name": "Espada de Madeira",
        "type": "weapon",
        "attack": 128,
        "count": 40,
        "description": "Arma comum (+128⚔️). Pode ir no slot Arma do JOGADOR (play) ou equipada numa criatura (equip_item, sem gastar play)."
    },
    "espada_ferro": {
        "id": "espada_ferro",
        "name": "Espada de Ferro",
        "type": "weapon",
        "attack": 256,
        "count": 35,
        "description": "Arma comum (+256⚔️). Slot do jogador ou equipada em criatura."
    },
    "katana": {
        "id": "katana",
        "name": "Katana",
        "type": "weapon",
        "attack": 512,
        "count": 18,
        "description": "Arma incomum (+512⚔️). Slot do jogador ou equipada em criatura."
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
        "description": "Arma (350⚔️ base). +50⚔️ por Orc nas bases de ATAQUE do dono (máx. 3 orcs = +150). Bônus é dinâmico."
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
        "description": "Arma (100⚔️). Só Magos (mago / mago_negro / rei_mago). Feitiços de cura/buff do dono ganham +256 de poder."
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
        "description": "Arma só para Lobisomem do Crepúsculo. De DIA: 150⚔️. De NOITE: 600⚔️. O valor muda com o ciclo automaticamente."
    },
    
    "blade_vampires": {
        "id": "blade_vampires", 
        "name": "Blade of Vampires", 
        "type": "weapon", 
        "attack": 1500, 
        "count": 1, 
        "description": "Arma lendária (+1500⚔️). Só Vampiro Tayler ou Wers. Ataques podem marcar o oponente como noturno (vulnerável ao sol)."
    },
    "blade_dragons": {
        "id": "blade_dragons", 
        "name": "Blade of Dragons", 
        "type": "weapon", 
        "attack": 1500, 
        "count": 1, 
        "description": "Arma lendária (+1500⚔️). Só Elfo ou Vampiros (Tayler/Wers). Pode banir criaturas do cemitério (sem reviver/invocar)."
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
        "description": "Armadura slot capacete (+300 proteção/vida na criatura). Protege criaturas dies_daylight da morte solar quando equipada nelas."
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
        "description": "Slot capacete. No JOGADOR: 1× por turno o 1º dano à vida do jogador é −80. Na CRIATURA: +180 vida. Na mão não faz nada."
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
        "description": "Slot peitoral. Na CRIATURA: +350 vida; em Elfo/Ninfa concede ward (ignora o próximo feitiço hostil). Prefira na criatura."
    },
    "peitoral_ferro": {
        "id": "peitoral_ferro",
        "name": "Peitoral de Ferro",
        "type": "armor",
        "slot": "armor",
        "protection": 220,
        "count": 25,
        "description": "Slot peitoral. Equipado na criatura: +220 vida. Na mão não protege."
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
        "description": "Slot calças. No JOGADOR: todo dano à vida do jogador −40. Na CRIATURA: apenas +150 vida (sem redução de dano)."
    },
    "botas_andarilho": {
        "id": "botas_andarilho",
        "name": "Botas do Andarilho",
        "type": "armor",
        "slot": "boots",
        "protection": 80,
        "count": 14,
        "ability": "free_swap",
        "description": "Slot botas. No JOGADOR: 1 troca grátis ataque↔defesa por turno. Na CRIATURA: só +80 vida (sem free swap)."
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
        "description": "Melhor na CRIATURA em ATAQUE: +120 vida e +40 ataque. Na mão ou só no jogador o bônus de carga não se aplica como na criatura em ataque."
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
        "description": "Slot peitoral. Equipado (criatura ou jogador): +200 proteção e proteção solar (noturnos não morrem/tomam sol). Na mão não protege."
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
        "description": "Muda com o ciclo. DIA: 700❤️ / 40⚔️ (tanque). NOITE: 480❤️ / 170⚔️ (predador). Usa Adaga do Crepúsculo."
    },
    
    # Talismãs (não podem ser jogados, apenas segurados)
    "talisma_ordem": {
        "id": "talisma_ordem", 
        "name": "Talismã - Ordem", 
        "type": "talisman", 
        "count": 1, 
        "description": "Talismã (fica na mão; não se joga no board). Imunidade a efeitos de Caos."
    },
    "talisma_imortalidade": {
        "id": "talisma_imortalidade", 
        "name": "Talismã - Imortalidade", 
        "type": "talisman", 
        "count": 1, 
        "uses_left": 2,
        "description": "Talismã na mão. Ao morrer (vida 0), restaura vida e consome uso (começa com 2 usos). Oráculo inimigo pode anular."
    },
    "talisma_verdade": {
        "id": "talisma_verdade", 
        "name": "Talismã - Verdade", 
        "type": "talisman", 
        "count": 1, 
        "description": "Talismã na mão. Imunidade a feitiços e oráculos hostis."
    },
    "talisma_guerreiro": {
        "id": "talisma_guerreiro", 
        "name": "Talismã - Guerreiro", 
        "type": "talisman", 
        "count": 1, 
        "description": "Talismã na mão. Enquanto na mão: +1024 no poder de ataque do jogador ao atacar."
    },
    "talisma_sabedoria": {
        "id": "talisma_sabedoria", 
        "name": "Talismã - Sabedoria", 
        "type": "talisman", 
        "count": 1, 
        "description": "Talismã na mão (ou lista de talismãs). Permite 2 ações de JOGAR CARTA por turno (play ×2)."
    },
    
    # Runas
    "runa": {
        "id": "runa", 
        "name": "Runa", 
        "type": "rune",
        "count": 40, 
        "description": "Recurso na mão. 4 runas permitem invocar/reviver uma criatura do cemitério (ação revive). Mod no_runes desliga."
    },
    
    # Feitiços
    "feitico_cortes": {
        "id": "feitico_cortes", 
        "name": "Feitiço - Cortes", 
        "type": "spell", 
        "count": 2, 
        "description": "Requer mago em campo. +1024 de ataque em UMA criatura sua por 2 rodadas."
    },
    "feitico_duro_matar": {
        "id": "feitico_duro_matar", 
        "name": "Feitiço - Duro de matar", 
        "type": "spell", 
        "count": 2, 
        "description": "Requer mago. +1024 de 'defesa' ao jogador alvo por 2 rodadas (mitiga dano)."
    },
    "feitico_troca": {
        "id": "feitico_troca", 
        "name": "Feitiço - Troca", 
        "type": "spell", 
        "count": 2, 
        "description": "Requer mago. Inverte bases de ataque↔defesa do jogador alvo."
    },
    "feitico_comunista": {
        "id": "feitico_comunista", 
        "name": "Feitiço - Comunista", 
        "type": "spell", 
        "count": 2, 
        "description": "Requer mago. Devolve as mãos dos jogadores ao baralho (redistribui pressão de mão)."
    },
    "feitico_silencio": {
        "id": "feitico_silencio", 
        "name": "Feitiço - Silêncio", 
        "type": "spell", 
        "count": 2, 
        "description": "Requer mago. Nas próximas 2 rodadas, ataques não ativam armadilhas."
    },
    "feitico_para_sempre": {
        "id": "feitico_para_sempre", 
        "name": "Feitiço - Para Sempre", 
        "type": "spell", 
        "count": 2, 
        "description": "Requer mago. Remove a maldição noturna da Blade of Vampires."
    },
    "feitico_capitalista": {
        "id": "feitico_capitalista", 
        "name": "Feitiço - Capitalista", 
        "type": "spell", 
        "count": 2, 
        "description": "Requer mago. Troca cartas da mão com outro jogador."
    },
    "feitico_cura": {
        "id": "feitico_cura", 
        "name": "Feitiço - Cura", 
        "type": "spell", 
        "count": 10, 
        "description": "Requer mago. Cura 1024 de vida no jogador alvo (você ou aliado/oponente)."
    },
    "feitico_clareira_lua": {
        "id": "feitico_clareira_lua",
        "name": "Feitiço - Clareira da Lua",
        "type": "spell",
        "count": 6,
        "description": "Requer mago. Força NOITE imediatamente (beneficia noturnos e lobisomem)."
    },
    "feitico_julgamento_aurora": {
        "id": "feitico_julgamento_aurora",
        "name": "Feitiço - Julgamento da Aurora",
        "type": "spell",
        "count": 5,
        "description": "Requer mago. Destrói 1 criatura noturna visível (zumbi/vampiro/lobisomem/dies_daylight)."
    },
    "feitico_eco_grimorio": {
        "id": "feitico_eco_grimorio",
        "name": "Feitiço - Eco do Grimório",
        "type": "spell",
        "count": 3,
        "description": "Requer mago. Copia o efeito do último feitiço da partida (não copia a si mesmo)."
    },
    "feitico_selo_silencio": {
        "id": "feitico_selo_silencio",
        "name": "Feitiço - Selo de Silêncio Menor",
        "type": "spell",
        "count": 6,
        "description": "Requer mago. Seu PRÓXIMO ataque não ativa armadilhas (counter de Poço etc.)."
    },
    
    # Oraculo
    "oraculo_imortalidade": {
        "id": "oraculo_imortalidade", 
        "name": "Oráculo", 
        "type": "oracle", 
        "count": 1, 
        "description": "Requer Elfo em DEFESA. Anula Talismã da Imortalidade do alvo no ataque mortal e é consumido."
    },
    
    # Rituais (requerem condições específicas)
    "ritual_157": {
        "id": "ritual_157", 
        "name": "Ritual 157", 
        "type": "ritual", 
        "count": 1, 
        "description": "Ritual. Requer em campo: Apofis, Mago Negro, 2 zumbis e 2 elfos em defesa. Rouba todos os talismãs da mão do alvo."
    },
    "ritual_amor": {
        "id": "ritual_amor", 
        "name": "Ritual Amor", 
        "type": "ritual", 
        "count": 1, 
        "description": "Ritual. Requer Ninfa Belly Lorem + Vampiro Necrothic Tayler. Remove maldição do Profeta."
    },
    "ritual_chaos": {
        "id": "ritual_chaos",
        "name": "Ritual do Caos",
        "type": "ritual",
        "count": 1,
        "description": "Ritual. Requer Apofis + Mago Negro. Invoca efeito de Caos (anula proteções de Ordem se aplicável)."
    },

    # Armadilhas
    "armadilha_171": {
        "id": "armadilha_171", 
        "name": "Armadilha 171", 
        "type": "trap", 
        "count": 2, 
        "description": "Armadilha em defesa (disfarçada). Ao ser ativada por ataque: rouba a criatura/carta que deu o golpe crítico."
    },
    "armadilha_espelho": {
        "id": "armadilha_espelho", 
        "name": "Armadilha Espelho", 
        "type": "trap", 
        "count": 2, 
        "description": "Armadilha em defesa. Reflete o ataque (e efeitos mágicos associados) de volta ao agressor."
    },
    "armadilha_cheat": {
        "id": "armadilha_cheat", 
        "name": "Armadilha Cheat", 
        "type": "trap", 
        "count": 2, 
        "description": "Armadilha. Só à NOITE e com mago em campo: dobra o ataque recebido e redireciona ao próximo jogador."
    },
    "armadilha_poco": {
        "id": "armadilha_poco", 
        "name": "Armadilha - Poço Sem Fundo", 
        "type": "trap", 
        "count": 2, 
        "description": "Armadilha em defesa. Ao ser atacado: destrói TODAS as criaturas nas bases de ataque do agressor e vai ao cemitério; a armadilha se desativa."
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
        "description": "Tropa (50⚔️ / 512❤️). Em campo: habilita Oráculo se estiver em defesa. Não ataca outros elfos."
    },
    {
        "id": "mago",
        "name": "Mago",
        "type": "creature", 
        "life": 512, 
        "attack": 50, 
        "count": 50, 
        "description": "Tropa (50⚔️ / 512❤️). Em campo (ataque ou defesa): permite lançar feitiços da mão (1 feitiço por turno)."
    },
    {
        "id": "orc",
        "name": "Orc",
        "type": "creature",
        "life": 512,
        "attack": 60,
        "count": 50,
        "description": "Tropa bruta (60⚔️ / 512❤️). Sinergia com Clava do Orc (+50⚔️ por orc em bases de ataque, máx. 3)."
    },
    {
        "id": "zumbi", 
        "name": "Zumbi",
        "type": "creature",
        "life": 100, 
        "attack": 25,
        "count": 50, 
        "description": "Criatura noturna fraca (25⚔️ / 100❤️). Morre ao virar o DIA se não tiver proteção solar (Capacete das Trevas / Manto do Eclipse). Se destruído por outro zumbi, pode voltar à mão.", 
        "dies_daylight": True
    },
    {
        "id": "centauro",
        "name": "Centauro", 
        "type": "creature", 
        "life": 512, 
        "attack": 70, 
        "count": 50, 
        "description": "Tropa (70⚔️ / 512❤️). Pode ser montaria (slot mount do jogador) ou chamada em grupo (Chamar Centauros com 2+). Super Centauro pode roubar centauros em campo."
    },
    {
        "id": "ninfa",
        "name": "Ninfa",
        "type": "creature",
        "life": 512,
        "attack": 30,
        "count": 35,
        "description": "Espírito da natureza (30⚔️ / 512❤️). Sinergia com Peitoral de Carvalho (ward contra feitiço hostil)."
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
        'description': 'Jogadores começam com 600 de vida (padrão é 1200)',
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
        'description': 'Criaturas inimigas viram silhueta (sem nome/stats). Logs e avisos de combate também escondem nomes, poder de ataque e vida restante do oponente.',
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

