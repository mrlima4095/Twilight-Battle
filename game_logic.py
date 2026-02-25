from enum import Enum
import random

class TimeOfDay(Enum):
    DAY = "day"
    NIGHT = "night"
    
    def to_string(self):
        return self.value

class Card:
    def __init__(self, card_id, name, life=0, attack=0, description="", card_type="creature"):
        self.id = card_id
        self.name = name
        self.life = life
        self.max_life = life
        self.attack = attack
        self.description = description
        self.type = card_type
        self.position = None  # 'attack', 'defense', ou None
        self.tapped = False
        self.equipment = []
        self.mounted_on = None
        
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'life': self.life,
            'max_life': self.max_life,
            'attack': self.attack,
            'description': self.description,
            'type': self.type,
            'position': self.position,
            'tapped': self.tapped
        }
    
    def take_damage(self, damage):
        self.life -= damage
        return self.life <= 0

class Player:
    def __init__(self, player_id, name):
        self.id = player_id
        self.name = name
        self.life = 5000
        self.max_life = 5000
        self.hand = []
        self.deck = []
        self.graveyard = []
        self.field = []
        self.bases = {
            'attack': 3,
            'defense': 6
        }
        self.actions_used = {
            'draw': False,
            'move': False,
            'untap': False,
            'attack': False,
            'play_card': False
        }
        self.talismans = []
        
    def draw_initial_hand(self):
        """Compra 5 cartas iniciais"""
        for _ in range(5):
            if self.deck:
                self.hand.append(self.deck.pop(0))
    
    def draw_card(self):
        """Compra uma carta do deck"""
        if self.deck and not self.actions_used['draw']:
            self.hand.append(self.deck.pop(0))
            return True
        return False
    
    def play_card(self, card_index, position):
        """Joga uma carta da mão para o campo"""
        if card_index < len(self.hand) and not self.actions_used['play_card']:
            card = self.hand.pop(card_index)
            card.position = position
            card.tapped = True  # Vira a carta ao jogar
            self.field.append(card)
            self.actions_used['play_card'] = True
            return True
        return False
    
    def take_damage(self, damage):
        """Aplica dano ao jogador, considerando cartas de defesa"""
        # Ordena cartas de defesa por vida (menor primeiro)
        defense_cards = [c for c in self.field if c.position == 'defense' and c.life > 0]
        defense_cards.sort(key=lambda x: x.life)
        
        remaining_damage = damage
        
        # Cartas de defesa absorvem dano
        for card in defense_cards:
            if remaining_damage <= 0:
                break
            
            if card.life <= remaining_damage:
                remaining_damage -= card.life
                card.life = 0
                # Carta morre, vai para o cemitério
                self.graveyard.append(card)
                self.field.remove(card)
            else:
                card.life -= remaining_damage
                remaining_damage = 0
        
        # Dano restante vai para o jogador
        if remaining_damage > 0:
            self.life -= remaining_damage
        
        return damage - remaining_damage  # Retorna dano causado
    
    def reset_actions(self):
        """Reseta as ações do jogador para o próximo turno"""
        for action in self.actions_used:
            self.actions_used[action] = False
        
        # Desvira cartas
        for card in self.field:
            card.tapped = False

class Game:
    def __init__(self):
        self.players = {}
        self.time_of_day = TimeOfDay.DAY
        self.time_counter = 0
        self.all_cards = self.create_all_cards()
        
    def create_all_cards(self):
        """Cria todas as cartas do jogo"""
        cards = []
        
        # Elfos (40 unidades)
        for i in range(40):
            cards.append(Card(f"elf_{i}", "Elfo", 512, 512, 
                            "Não ataca outros elfos. Use para realizar oraculos."))
        
        # Zumbis (30 unidades)
        for i in range(30):
            cards.append(Card(f"zombie_{i}", "Zumbi", 100, 100,
                            "Morre durante o dia. A menos que derrotado por outro zumbi volta para a mão do jogador."))
        
        # Medusa (1 unidade)
        cards.append(Card("medusa", "Medusa", 1024, 150,
                         "Seu ataque transforma personagens em pedra. Cartas com maior vida são imunes."))
        
        # Capacete das trevas (15 unidades)
        for i in range(15):
            cards.append(Card(f"dark_helm_{i}", "Capacete das Trevas", 0, 0,
                            "Impede o dano da luz do dia em mortos-vivos e a proteção é adicionada a carta.",
                            "equipment"))
        
        # Talismãs
        cards.append(Card("talisman_order", "Talismã - Ordem", 0, 0,
                         "Imunidade ao Caos.", "talisman"))
        cards.append(Card("talisman_immortality", "Talismã - Imortalidade", 0, 0,
                         "Se o jogador for morto com este item em mãos ele terá seus pontos de vida restaurados.", 
                         "talisman"))
        cards.append(Card("talisman_truth", "Talismã - Verdade", 0, 0,
                         "Imunidade a feitiços e oraculos.", "talisman"))
        cards.append(Card("talisman_warrior", "Talismã - Guerreiro", 0, 0,
                         "Aumenta em 1000 pontos o ataque e defesa do jogador.", "talisman"))
        
        # Vampiros
        cards.append(Card("vampire_taylor", "Vampiro - Necrothic Tayler", 512, 100,
                         "Rouba a vida do oponente para recuperar a vida de seu jogador."))
        cards.append(Card("vampire_benjamim", "Vampiro - Benjamim Wers", 512, 250,
                         "Mata todos os centauros em campo dos oponentes e entrega a vida a jogador."))
        
        # Profeta
        cards.append(Card("prophet", "Profeta", 256, 50,
                         "Anuncia a morte de um monstro para duas rodadas a frente. A maldição pode ser retirada caso o jogador seja derrotado."))
        
        # Mago Negro
        cards.append(Card("dark_mage", "Mago Negro", 2000, 1500,
                         "Não se subordina ao Rei Mago. Realiza rituais sem possuir a carta"))
        
        # Apollo
        cards.append(Card("apollo", "Apollo", 8200, 2000,
                         "Ataques sofridos com menos de 5k de dano recuperam a vida do jogador se colocado na defesa, não pode ficar na defesa por mais de 5 rodadas. Durante o dia pode revelar cartas em jogo do oponente."))
        
        # Apofis
        cards.append(Card("apophis", "Apofis", 32500, 5000,
                         "Rei do Caos. Pode desativar armadilhas e magias de outros jogadores."))
        
        # Lâmina das Almas
        cards.append(Card("soul_blade", "Lâmina das Almas", 0, 0,
                         "Assume o dano de uma carta do cemitério. Só pode ser equipado por Elfos, magos e vampiros.",
                         "equipment"))
        
        # Leviatã
        cards.append(Card("leviathan", "Leviatã", 15000, 15000,
                         "Imune a elementais de fogo. Só pode ser domado por deuses e magos supremos."))
        
        # Magos (25 unidades)
        for i in range(25):
            cards.append(Card(f"mage_{i}", "Mago", 800, 300,
                            "Use-o para invocar feitiços."))
        
        # Blades
        cards.append(Card("vampire_blade", "Blade of Vampires", 0, 5000,
                         "Só pode ser usada por um vampiro. Seu ataque torna o oponente noturno (morre de dia)",
                         "equipment"))
        cards.append(Card("dragon_blade", "Blade of Dragons", 0, 5000,
                         "Usada apenas por elfos ou vampiros. Seu ataque pode eliminar personagens permanentemente tornando impossíveis de reviver ou ser invocados de volta do cemitério.",
                         "equipment"))
        
        # Ninfa
        cards.append(Card("nymph", "Ninfa - Belly Lorem", 512, 128,
                         "Torna o jogador imune a rituais."))
        
        # Centauros (35 unidades)
        for i in range(35):
            cards.append(Card(f"centaur_{i}", "Centauro", 512, 150,
                            "O jogador pode colocar personagens para montar no centauro. Realiza qualquer ataque terrestre."))
        
        # Super Centauros (5 unidades)
        for i in range(5):
            cards.append(Card(f"super_centaur_{i}", "Super Centauro", 600, 256,
                            "Apenas ataques diretos. Pode encantar centauros de outros jogadores e pegar eles para a sua mão."))
        
        # Rei Mago
        cards.append(Card("king_mage", "Rei Mago", 2000, 1500,
                         "Pode impedir outros magos de realizar feitiços. Realiza feitiços sem possuir a carta."))
        
        # Dragões (3 unidades)
        for i in range(3):
            cards.append(Card(f"dragon_{i}", "Dragão", 5000, 1500,
                            "Seu ataque incendeia o inimigo, com isso ele toma 50 de dano nas próximas rodadas do fogo."))
        
        # Fênix
        cards.append(Card("phoenix", "Fênix", 32500, 10000,
                         "Grande ave com ataque de fogo, pode mudar de dia para noite e vice-versa quando bem entender."))
        
        # Runas (20 unidades)
        for i in range(20):
            cards.append(Card(f"rune_{i}", "Runa", 0, 0,
                            "Colete quatro runas para realizar uma invocação de um personagem do cemitério.",
                            "spell"))
        
        # Feitiços
        spells = [
            ("cortes", "Feitiço - Cortes", "Aumenta ataque de um monstro em 1024 pontos."),
            ("duro_de_matar", "Feitiço - Duro de matar", "Aumenta defesa do jogador em 1024 pontos."),
            ("troca", "Feitiço - Troca", "Troca as cartas do Jogador de defesa para ataque e vice-versa de um jogador."),
            ("comunista", "Feitiço - Comunista", "Faz as cartas das mãos dos jogadores irem de volta para a pilha."),
            ("silêncio", "Feitiço - Silêncio", "Os ataques das próximas duas rodadas não ativam armadilhas."),
            ("para_sempre", "Feitiço - Para Sempre", "Reverte o efeito da espada Blade of Vampires."),
            ("capitalista", "Feitiço - Capitalista", "Troque cartas com outros jogadores.")
        ]
        
        for spell_id, spell_name, spell_desc in spells:
            cards.append(Card(spell_id, spell_name, 0, 0, spell_desc, "spell"))
        
        # Oraculo
        cards.append(Card("oracle", "Oraculo", 0, 0,
                         "Mate o oponente com o talismã da imortalidade três vezes para que ele seja derrotado permanentemente, seja rápido antes que ele junte todos os talismãs.",
                         "spell"))
        
        # Rituais
        rituals = [
            ("ritual_157", "Ritual 157", "Requer Apofis, Mago Negro, 6 zumbis e 2 elfos em modo de defesa. Todos os talismãs da mão do jogador escolhido são roubados."),
            ("ritual_amor", "Ritual - Amor", "Requer a Ninfa Belly Lorem e o Vampiro Necrothic Tayler. Anula a maldição do Profeta.")
        ]
        
        for ritual_id, ritual_name, ritual_desc in rituals:
            cards.append(Card(ritual_id, ritual_name, 0, 0, ritual_desc, "ritual"))
        
        # Armadilhas
        traps = [
            ("trap_51", "Armadilha 51", "Faz o exército do outro jogador ficar bêbado e atacar aliados."),
            ("trap_171", "Armadilha 171", "Rouba a carta que te dá um golpe crítico."),
            ("trap_mirror", "Armadilha - Espelho", "Reverte ataques e magia."),
            ("trap_cheat", "Armadilha - Cheat", "Dobrar o ataque e passar para o próximo jogador na rodada, precisa estar de noite e um mago em campo.")
        ]
        
        for trap_id, trap_name, trap_desc in traps:
            cards.append(Card(trap_id, trap_name, 0, 0, trap_desc, "trap"))
        
        return cards
    
    def add_player(self, player):
        """Adiciona um jogador ao jogo"""
        if player.id not in self.players:
            # Cria deck para o jogador (cópias das cartas)
            player.deck = [self.copy_card(card) for card in self.all_cards]
            random.shuffle(player.deck)
            self.players[player.id] = player
    
    def copy_card(self, card):
        """Cria uma cópia de uma carta"""
        return Card(card.id, card.name, card.life, card.attack, 
                   card.description, card.type)
    
    def remove_player(self, player_id):
        """Remove um jogador do jogo"""
        if player_id in self.players:
            del self.players[player_id]
    
    def initialize_game(self):
        """Inicializa o jogo"""
        # Distribui cartas iniciais para todos os jogadores
        for player in self.players.values():
            player.draw_initial_hand()
    
    def update_time_of_day(self):
        """Atualiza o ciclo dia/noite (24 rodadas = ciclo completo)"""
        self.time_counter += 1
        if self.time_counter % 12 < 6:  # 6 rodadas de dia, 6 de noite
            self.time_of_day = TimeOfDay.DAY
        else:
            self.time_of_day = TimeOfDay.NIGHT