import json
import random
from typing import List, Dict, Optional, Tuple, Any
from mindi.game.card import Card, Suit, Rank, create_deck, deal_hands
from mindi.game.rules import validate_move, determine_trick_winner, calculate_game_result

class GameState:
    LOBBY = "LOBBY"
    SELECTING_TRUMP = "SELECTING_TRUMP"
    PLAYING = "PLAYING"
    COMPLETED = "COMPLETED"

class MindiGame:
    def __init__(
        self,
        match_id: str,
        player_ids: List[int],  # List of 4 Telegram IDs
        player_names: List[str],  # Display names
        trump_mode: str = "open",  # "open" or "hidden"
        dealer_idx: int = 0,
        group_chat_id: Optional[int] = None,
        group_msg_id: Optional[int] = None
    ):
        self.match_id = match_id
        self.player_ids = player_ids
        self.player_names = player_names
        self.trump_mode = trump_mode.lower()
        self.dealer_idx = dealer_idx
        self.group_chat_id = group_chat_id
        self.group_msg_id = group_msg_id
        
        self.state = GameState.LOBBY
        self.hands: List[List[Card]] = [[] for _ in range(4)]
        self.current_turn = 0
        self.starter_idx = 0
        
        self.trump_suit: Optional[Suit] = None
        self.is_trump_revealed = False
        self.hidden_hukum_card: Optional[str] = None  # The card string set as the hidden Hukam
        self.hidden_trump_selector_idx: Optional[int] = None
        self.trump_revealer_idx: Optional[int] = None
        
        self.current_trick: List[Dict[str, Any]] = []  # List of {"seat_index": int, "card": Card}
        self.tricks_history: List[Dict[str, Any]] = []
        self.center_pile: List[Card] = []
        
        self.team1_mindis = 0
        self.team2_mindis = 0
        self.team1_tricks = 0
        self.team2_tricks = 0
        self.last_trick_winner: Optional[int] = None

    def start_game(self):
        """Initializes the deck, deals cards, and advances the game state."""
        deck = create_deck()
        self.hands = deal_hands(deck)
        
        # In Mindi, the player to the left of the dealer starts
        self.starter_idx = (self.dealer_idx + 1) % 4
        self.current_turn = self.starter_idx
        
        if self.trump_mode == "hidden":
            self.state = GameState.SELECTING_TRUMP
            # The dealer's partner selects the trump suit
            self.hidden_trump_selector_idx = (self.dealer_idx + 2) % 4
        else:
            self.state = GameState.PLAYING
            self.trump_suit = None
            self.is_trump_revealed = False

    def select_hidden_trump(self, player_idx: int, card: Card) -> Tuple[bool, str]:
        """Sets the hidden trump suit by picking a card from the partner's hand."""
        if self.state != GameState.SELECTING_TRUMP:
            return False, "Not in trump selection state."
        if player_idx != self.hidden_trump_selector_idx:
            return False, "You are not designated to choose the trump."
        if card not in self.hands[player_idx]:
            return False, "Card is not in your hand."
            
        self.trump_suit = card.suit
        self.hidden_hukum_card = card.to_string()
        self.is_trump_revealed = False
        self.hands[player_idx].remove(card)
        self.state = GameState.PLAYING
        return True, ""

    def reveal_hidden_hukum(self, revealer_idx: int) -> Tuple[bool, str, Optional[str]]:
        """Reveals the hidden hukum card, returns it to the dealer's partner's hand, and activates trump suit."""
        if self.trump_mode != "hidden":
            return False, "Hukum mode is not hidden.", None
        if self.is_trump_revealed:
            return False, "Trump is already revealed.", None
        if not self.hidden_hukum_card:
            return False, "No hidden trump card is set.", None
            
        self.is_trump_revealed = True
        self.trump_revealer_idx = revealer_idx
        partner_idx = (self.dealer_idx + 2) % 4
        card = Card.from_string(self.hidden_hukum_card)
        
        # Return card to partner's hand and sort it
        self.hands[partner_idx].append(card)
        suit_order_map = {Suit.SPADES: 0, Suit.HEARTS: 1, Suit.DIAMONDS: 2, Suit.CLUBS: 3}
        self.hands[partner_idx].sort(key=lambda c: (suit_order_map[c.suit], c.get_order_value()))
        
        return True, "", self.hidden_hukum_card

    def get_led_suit(self) -> Optional[Suit]:
        """Returns the suit of the first card led in the current trick."""
        if not self.current_trick:
            return None
        return self.current_trick[0]["card"].suit

    def get_player_seat(self, player_id: int) -> int:
        """Returns the seat index of a player ID."""
        return self.player_ids.index(player_id)

    def get_legal_moves(self, seat_idx: int) -> List[Card]:
        """Returns a list of legal cards a player can play."""
        hand = self.hands[seat_idx]
        led_suit = self.get_led_suit()
        if led_suit is None:
            # First player can lead any card
            return hand
        
        # Follow suit if possible
        follow_suit_cards = [c for c in hand if c.suit == led_suit]
        if follow_suit_cards:
            return follow_suit_cards
        
        # If no card of the led suit, can play any card
        return hand

    def play_card(self, player_id: int, card: Card) -> Dict[str, Any]:
        """
        Executes a play. Validates the turn, card ownership, and rules.
        Handles trump revealing and trick resolution.
        """
        try:
            seat_idx = self.get_player_seat(player_id)
        except ValueError:
            return {"success": False, "error": "Player not in this game."}

        if self.state != GameState.PLAYING:
            return {"success": False, "error": "Game is not in playing state."}

        if seat_idx != self.current_turn:
            return {"success": False, "error": "It is not your turn."}

        hand = self.hands[seat_idx]
        led_suit = self.get_led_suit()
        
        if card not in hand:
            return {"success": False, "error": "Card is not in your hand."}
            
        # Validate move legality
        is_valid, err_msg = validate_move(hand, card, led_suit)
        if not is_valid:
            return {"success": False, "error": err_msg}

        # Check if player is cut (cannot follow suit)
        revealed_this_turn = False
        just_declared_suit = None
        
        if led_suit is not None and card.suit != led_suit:
            # Player is not following suit!
            if self.trump_mode == "open" and self.trump_suit is None:
                # The suit of this card played becomes the trump suit!
                self.trump_suit = card.suit
                self.is_trump_revealed = True
                self.trump_revealer_idx = seat_idx
                revealed_this_turn = True
                just_declared_suit = self.trump_suit

        # Remove card from hand
        hand.remove(card)
        self.current_trick.append({"seat_index": seat_idx, "card": card})
        
        event_info = {
            "success": True,
            "player_id": player_id,
            "seat_index": seat_idx,
            "card": card.to_string(),
            "revealed_trump": revealed_this_turn,
            "trump_suit": just_declared_suit.value if just_declared_suit else (self.trump_suit.value if self.trump_suit else None),
            "action": "play_card"
        }

        # If trick is not complete, move to next player
        if len(self.current_trick) < 4:
            self.current_turn = (self.current_turn + 1) % 4
            event_info["next_state"] = "next_turn"
            event_info["next_turn"] = self.current_turn
            return event_info

        # Trick is complete! Resolve it.
        trick_winner_seat = determine_trick_winner(
            self.current_trick,
            led_suit=self.current_trick[0]["card"].suit,
            trump_suit=self.trump_suit,
            is_trump_revealed=self.is_trump_revealed
        )
        
        # Register trick win
        winner_team = 1 if trick_winner_seat in [0, 2] else 2
        if winner_team == 1:
            self.team1_tricks += 1
        else:
            self.team2_tricks += 1

        # Add this trick's cards to the center pile
        trick_cards = [play["card"] for play in self.current_trick]
        self.center_pile.extend(trick_cards)

        collected = False
        collected_cards = []

        is_last_trick = (len(self.tricks_history) == 12)  # Since tricks_history is appended below, 12 means this is the 13th trick

        if is_last_trick:
            # Winner of the final trick collects all remaining cards in the center pile
            collected = True
            collected_cards = [c.to_string() for c in self.center_pile]
            mindis_collected = sum(c.value for c in self.center_pile)
            if winner_team == 1:
                self.team1_mindis += mindis_collected
            else:
                self.team2_mindis += mindis_collected
            self.center_pile = []
            self.last_trick_winner = None
        else:
            if self.last_trick_winner is not None:
                last_winner_team = 1 if self.last_trick_winner in [0, 2] else 2
                if winner_team == last_winner_team:
                    # Consecutive win! Winner collects the accumulated center pile
                    collected = True
                    collected_cards = [c.to_string() for c in self.center_pile]
                    mindis_collected = sum(c.value for c in self.center_pile)
                    if winner_team == 1:
                        self.team1_mindis += mindis_collected
                    else:
                        self.team2_mindis += mindis_collected
                    self.center_pile = []
                    self.last_trick_winner = trick_winner_seat
                else:
                    # Alternating win. Pile accumulates, update last winner.
                    self.last_trick_winner = trick_winner_seat
            else:
                # First trick of the game. Pile accumulates, update last winner.
                self.last_trick_winner = trick_winner_seat

        # Save trick to history
        self.tricks_history.append({
            "plays": [{"seat_index": p["seat_index"], "card": p["card"].to_string()} for p in self.current_trick],
            "winner_seat": trick_winner_seat,
            "collected": collected,
            "collected_cards": collected_cards
        })
        
        event_info["next_state"] = "trick_complete"
        event_info["trick_winner"] = trick_winner_seat
        event_info["trick_winner_name"] = self.player_names[trick_winner_seat]
        event_info["collected"] = collected
        event_info["collected_cards"] = collected_cards
        event_info["center_pile_size"] = len(self.center_pile)
        
        # Clear current trick
        self.current_trick = []

        # Check if game is over (13 tricks completed)
        if len(self.tricks_history) == 13:
            self.state = GameState.COMPLETED
            res = calculate_game_result(
                self.team1_mindis,
                self.team2_mindis,
                self.team1_tricks,
                self.team2_tricks
            )
            event_info["next_state"] = "game_completed"
            event_info["result"] = res
        else:
            # Winner leads the next trick
            self.current_turn = trick_winner_seat
            self.starter_idx = trick_winner_seat
            event_info["next_turn"] = self.current_turn

        return event_info

    def to_dict(self) -> Dict[str, Any]:
        """Serializes game state to a dictionary."""
        return {
            "match_id": self.match_id,
            "player_ids": self.player_ids,
            "player_names": self.player_names,
            "trump_mode": self.trump_mode,
            "dealer_idx": self.dealer_idx,
            "group_chat_id": self.group_chat_id,
            "group_msg_id": self.group_msg_id,
            "state": self.state,
            "hands": [[c.to_string() for c in hand] for hand in self.hands],
            "current_turn": self.current_turn,
            "starter_idx": self.starter_idx,
            "trump_suit": self.trump_suit.value if self.trump_suit else None,
            "is_trump_revealed": self.is_trump_revealed,
            "hidden_trump_selector_idx": self.hidden_trump_selector_idx,
            "trump_revealer_idx": self.trump_revealer_idx,
            "current_trick": [{"seat_index": p["seat_index"], "card": p["card"].to_string()} for p in self.current_trick],
            "tricks_history": self.tricks_history,
            "center_pile": [c.to_string() for c in self.center_pile],
            "team1_mindis": self.team1_mindis,
            "team2_mindis": self.team2_mindis,
            "team1_tricks": self.team1_tricks,
            "team2_tricks": self.team2_tricks,
            "last_trick_winner": self.last_trick_winner,
            "hidden_hukum_card": self.hidden_hukum_card
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MindiGame":
        """Deserializes game state from a dictionary."""
        game = cls(
            match_id=data["match_id"],
            player_ids=data["player_ids"],
            player_names=data["player_names"],
            trump_mode=data["trump_mode"],
            dealer_idx=data["dealer_idx"],
            group_chat_id=data.get("group_chat_id"),
            group_msg_id=data.get("group_msg_id")
        )
        game.state = data["state"]
        game.hands = [[Card.from_string(c) for c in hand] for hand in data["hands"]]
        game.current_turn = data["current_turn"]
        game.starter_idx = data["starter_idx"]
        
        game.trump_suit = Suit.from_string(data["trump_suit"]) if data["trump_suit"] else None
        game.is_trump_revealed = data["is_trump_revealed"]
        game.hidden_trump_selector_idx = data["hidden_trump_selector_idx"]
        game.trump_revealer_idx = data["trump_revealer_idx"]
        
        game.current_trick = [{"seat_index": p["seat_index"], "card": Card.from_string(p["card"])} for p in data["current_trick"]]
        game.tricks_history = data["tricks_history"]
        game.center_pile = [Card.from_string(c) for c in data["center_pile"]]
        
        game.team1_mindis = data["team1_mindis"]
        game.team2_mindis = data["team2_mindis"]
        game.team1_tricks = data["team1_tricks"]
        game.team2_tricks = data["team2_tricks"]
        game.last_trick_winner = data["last_trick_winner"]
        game.hidden_hukum_card = data.get("hidden_hukum_card")
        
        return game
