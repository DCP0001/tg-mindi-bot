import random
from enum import Enum
from typing import List

class Suit(str, Enum):
    SPADES = "♠"
    HEARTS = "♥"
    DIAMONDS = "♦"
    CLUBS = "♣"

    @classmethod
    def from_string(cls, val: str) -> "Suit":
        for s in cls:
            if s.value == val or s.name.lower() == val.lower():
                return s
        raise ValueError(f"Invalid suit: {val}")

class Rank(str, Enum):
    TWO = "2"
    THREE = "3"
    FOUR = "4"
    FIVE = "5"
    SIX = "6"
    SEVEN = "7"
    EIGHT = "8"
    NINE = "9"
    TEN = "10"
    JACK = "J"
    QUEEN = "Q"
    KING = "K"
    ACE = "A"

RANK_ORDER = [
    Rank.TWO, Rank.THREE, Rank.FOUR, Rank.FIVE, Rank.SIX,
    Rank.SEVEN, Rank.EIGHT, Rank.NINE, Rank.TEN, Rank.JACK,
    Rank.QUEEN, Rank.KING, Rank.ACE
]

class Card:
    def __init__(self, suit: Suit, rank: Rank):
        self.suit = suit
        self.rank = rank

    @property
    def value(self) -> int:
        # 10s are Mindis (value cards)
        return 1 if self.rank == Rank.TEN else 0

    @property
    def is_mindi(self) -> bool:
        return self.rank == Rank.TEN

    def get_order_value(self) -> int:
        return RANK_ORDER.index(self.rank)

    def to_string(self) -> str:
        return f"{self.suit.value}{self.rank.value}"

    def __repr__(self) -> str:
        return self.to_string()

    def __eq__(self, other) -> bool:
        if not isinstance(other, Card):
            return False
        return self.suit == other.suit and self.rank == other.rank

    def __hash__(self) -> int:
        return hash((self.suit, self.rank))

    @classmethod
    def from_string(cls, card_str: str) -> "Card":
        if not card_str or len(card_str) < 2:
            raise ValueError(f"Invalid card string: {card_str}")
        suit_char = card_str[0]
        rank_char = card_str[1:]
        suit = Suit.from_string(suit_char)
        # Find matching rank
        for r in Rank:
            if r.value == rank_char:
                return cls(suit, r)
        raise ValueError(f"Invalid rank in card string: {card_str}")

def create_deck() -> List[Card]:
    return [Card(s, r) for s in Suit for r in Rank]

def deal_hands(deck: List[Card], player_count: int = 4) -> List[List[Card]]:
    if player_count != 4:
        raise ValueError("Mindi currently supports exactly 4 players.")
    random.shuffle(deck)
    # Deal 13 cards to each of the 4 players
    hands = [[] for _ in range(player_count)]
    for i, card in enumerate(deck):
        hands[i % player_count].append(card)
    
    # Sort hands for players (Suit order: Spades, Hearts, Diamonds, Clubs; then Rank order)
    suit_order_map = {Suit.SPADES: 0, Suit.HEARTS: 1, Suit.DIAMONDS: 2, Suit.CLUBS: 3}
    for hand in hands:
        hand.sort(key=lambda c: (suit_order_map[c.suit], c.get_order_value()))
    
    return hands
