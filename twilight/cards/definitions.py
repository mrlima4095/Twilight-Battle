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

    "espada_ferro": {
        "id": "espada_ferro",
        "name": "Espada de Ferro",
        "type": "weapon",
        "attack": 256,
        "count": 40,
        "description": "Uma espada para seus soldados."
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
        "protection": 300, 
        "count": 20, 
        "description": "Impede o dano da luz do dia em mortos-vivos e a proteção é adicionada a carta."
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
        'id': 'no_runes',
        'name': 'Sem Runas',
        'description': 'As cartas de Runa não podem reviver do cemiterio',
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
        'id': 'disable_traps',
        'name': 'Desativar Armadilhas',
        'description': 'Não haverá cartas de armadilha no jogo',
        'icon': '🕳️',
        'enabled': True
    },
    # Futuros modificadores podem ser adicionados aqui:
    # {
    #     'id': 'double_damage',
    #     'name': 'Dano Dobrado',
    #     'description': 'Todo dano causado é dobrado',
    #     'icon': '💥',
    #     'enabled': True
    # },
]

