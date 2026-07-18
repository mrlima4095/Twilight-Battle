"""Construção e embaralhamento do baralho."""
import random
import uuid

from twilight.cards.definitions import CARDS, DISGUISE_OPTIONS

def get_random_disguise():
    disguise = random.choice(DISGUISE_OPTIONS)
    return {
        'id': disguise['id'],
        'name': disguise['name'],
        'type': 'creature',
        'life': disguise['life'],
        'attack': disguise['attack'],
        'description': disguise['description'],
        'dies_daylight': disguise.get('dies_daylight', False),
        'is_disguised_trap': True,  # Marcar como disfarce
        'original_trap_id': None  # Será preenchido depois
    }


def create_deck(modifiers=[]):
    deck = []
    for card_id, card_info in CARDS.items():
        for _ in range(card_info['count']):
            if 'disable_traps' in modifiers and card_info.get('type') == 'trap':
                continue
            if 'no_runes' in modifiers and card_info.get('type') == 'rune':
                continue

            new_card = card_info.copy()
            new_card['instance_id'] = str(uuid.uuid4())[:8]
            deck.append(new_card)
    random.shuffle(deck)
    return deck

