from typing import List, Dict, Optional, Tuple
from mindi.game.card import Card, Suit, Rank

def validate_move(hand: List[Card], card_played: Card, led_suit: Optional[Suit]) -> Tuple[bool, str]:
    """
    Validates if playing card_played from hand is legal under Mindi rules.
    Returns (is_valid, error_message).
    """
    if card_played not in hand:
        return False, "Card is not in your hand."

    if led_suit is None:
        # First player of the trick can lead any card
        return True, ""

    # Player must follow suit if they have a card of the led suit
    has_led_suit = any(c.suit == led_suit for c in hand)
    if has_led_suit and card_played.suit != led_suit:
        return False, f"You must follow suit. You have {led_suit.value} cards in your hand."

    return True, ""

def determine_trick_winner(
    trick_plays: List[Dict], 
    led_suit: Suit, 
    trump_suit: Optional[Suit], 
    is_trump_revealed: bool
) -> int:
    """
    Determines the seat index of the winner of the trick.
    Each item in trick_plays is {"seat_index": int, "card": Card}.
    
    Rules:
    - If trump is revealed and trump cards are played, the highest trump card wins.
    - Otherwise, the highest card of the led suit wins.
    """
    if not trick_plays:
        raise ValueError("Trick plays list cannot be empty.")

    winning_play = trick_plays[0]
    
    # We compare cards sequentially to see which one beats the current winner
    for play in trick_plays[1:]:
        current_win_card = winning_play["card"]
        new_card = play["card"]

        # Check if new card beats current winning card
        beats = False
        
        if is_trump_revealed and trump_suit:
            # If the new card is trump and the current winning card is not trump
            if new_card.suit == trump_suit and current_win_card.suit != trump_suit:
                beats = True
            # If both are trump cards
            elif new_card.suit == trump_suit and current_win_card.suit == trump_suit:
                if new_card.get_order_value() > current_win_card.get_order_value():
                    beats = True
            # If neither is a trump card, and new card matches led suit
            elif new_card.suit == led_suit and current_win_card.suit == led_suit:
                if new_card.get_order_value() > current_win_card.get_order_value():
                    beats = True
            # If new card matches led suit but current win card is not led suit and not trump
            elif new_card.suit == led_suit and current_win_card.suit != led_suit and current_win_card.suit != trump_suit:
                beats = True
        else:
            # Trump not revealed or not set yet
            if new_card.suit == led_suit and current_win_card.suit == led_suit:
                if new_card.get_order_value() > current_win_card.get_order_value():
                    beats = True
            elif new_card.suit == led_suit and current_win_card.suit != led_suit:
                # This case shouldn't happen unless current_win_card didn't match led suit,
                # which can only happen if the first card led wasn't followed (impossible).
                beats = True

        if beats:
            winning_play = play

    return winning_play["seat_index"]

def calculate_game_result(
    team1_mindis: int, 
    team2_mindis: int, 
    team1_tricks: int, 
    team2_tricks: int
) -> Dict:
    """
    Calculates who won the game, whether a Coat was scored, and the ELO shift metrics.
    Team 1 = Players 0 & 2
    Team 2 = Players 1 & 3
    
    A team wins if they capture more than 2 Mindis (10s).
    If they capture exactly 2 Mindis each, the team with the most tricks wins.
    If they capture 4 Mindis, it is a Coat (whitewash).
    """
    total_mindis = team1_mindis + team2_mindis
    if total_mindis != 4:
        raise ValueError(f"Total mindis must equal 4, got {total_mindis}")

    winner_team = None
    is_coat = False

    if team1_mindis > team2_mindis:
        winner_team = 1
        if team1_mindis == 4:
            is_coat = True
    elif team2_mindis > team1_mindis:
        winner_team = 2
        if team2_mindis == 4:
            is_coat = True
    else:
        # 2 Mindis each. Winner decided by trick counts
        if team1_tricks > team2_tricks:
            winner_team = 1
        elif team2_tricks > team1_tricks:
            winner_team = 2
        else:
            # Extreme tiebreaker (e.g. whoever won the last trick, let's default to Team 1 or last trick winner)
            # We'll default to Team 1 for simplicity, but trick count is odd (13), so a trick tie is impossible.
            winner_team = 1

    return {
        "winner_team": winner_team,
        "is_coat": is_coat,
        "team1_mindis": team1_mindis,
        "team2_mindis": team2_mindis,
        "team1_tricks": team1_tricks,
        "team2_tricks": team2_tricks
    }
