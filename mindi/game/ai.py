import random
from typing import List, Optional
from mindi.game.card import Card, Suit, Rank
from mindi.game.engine import MindiGame
from mindi.game.rules import determine_trick_winner

def get_ai_move(game: MindiGame, seat_idx: int, level: str = "medium") -> Card:
    """
    Selects a card for the AI player at seat_idx to play.
    Levels: 'easy', 'medium', 'hard'.
    """
    legal_moves = game.get_legal_moves(seat_idx)
    if not legal_moves:
        raise ValueError(f"No legal moves for seat {seat_idx}")
    
    if len(legal_moves) == 1:
        return legal_moves[0]
        
    level = level.lower()
    
    if level == "easy":
        return random.choice(legal_moves)
    
    # Common helper calculations
    led_suit = game.get_led_suit()
    trump_suit = game.trump_suit
    is_trump_revealed = game.is_trump_revealed
    
    # Partner seat
    partner_idx = (seat_idx + 2) % 4
    
    # Check if teammate is currently winning the trick
    teammate_winning = False
    current_winning_seat = None
    if game.current_trick:
        current_winning_seat = determine_trick_winner(
            game.current_trick,
            led_suit=game.current_trick[0]["card"].suit,
            trump_suit=trump_suit,
            is_trump_revealed=is_trump_revealed
        )
        if current_winning_seat == partner_idx:
            teammate_winning = True

    # ------------------ MEDIUM / HARD STRATEGY ------------------
    # 1. AI is leading the trick (first to play)
    if led_suit is None:
        # If we have Aces or Kings, lead them to try and win.
        # Prefer leading non-trump suits unless we only have trump.
        non_trump_high = [c for c in legal_moves if c.rank in [Rank.ACE, Rank.KING] and c.suit != trump_suit]
        if non_trump_high:
            return random.choice(non_trump_high)
        
        # Avoid leading 10s directly unless we are confident or forced
        safe_leads = [c for c in legal_moves if c.rank != Rank.TEN]
        if safe_leads:
            # Lead highest card from safe list
            return max(safe_leads, key=lambda c: c.get_order_value())
        
        # Fallback to absolute highest
        return max(legal_moves, key=lambda c: c.get_order_value())

    # 2. AI is following suit
    is_following_suit = legal_moves[0].suit == led_suit
    if is_following_suit:
        # Teammate is already winning: play our lowest card of the suit (save big cards)
        if teammate_winning:
            return min(legal_moves, key=lambda c: c.get_order_value())
            
        # Try to win: find cards that can win the trick
        winning_cards = []
        for card in legal_moves:
            temp_trick = list(game.current_trick) + [{"seat_index": seat_idx, "card": card}]
            winner = determine_trick_winner(temp_trick, led_suit, trump_suit, is_trump_revealed)
            if winner == seat_idx:
                winning_cards.append(card)
                
        if winning_cards:
            # Play the lowest winning card to conserve high cards (e.g. if Q beats J, play Q rather than A)
            # If Hard level, and we are last to play, and a Mindi is in the trick, make sure to win.
            if level == "hard" and any(c["card"].is_mindi for c in game.current_trick):
                # Win with lowest possible winning card
                return min(winning_cards, key=lambda c: c.get_order_value())
            return min(winning_cards, key=lambda c: c.get_order_value())
        else:
            # Can't win anyway: discard lowest card
            return min(legal_moves, key=lambda c: c.get_order_value())

    # 3. AI is cutting (cannot follow suit)
    # Here, legal_moves contains cards of other suits because we have no cards of the led_suit.
    
    # Case A: Trump is not yet declared/revealed
    if not is_trump_revealed:
        if game.trump_mode == "hidden":
            # If we know the hidden trump suit, and we have a card of it, play it to reveal trump and win
            if trump_suit:
                trump_cards = [c for c in legal_moves if c.suit == trump_suit]
                if trump_cards and not teammate_winning:
                    # Reveal trump and play highest trump card
                    return max(trump_cards, key=lambda c: c.get_order_value())
            # Otherwise, discard lowest card of some other suit (not 10s)
            safe_discards = [c for c in legal_moves if c.rank != Rank.TEN]
            if safe_discards:
                return min(safe_discards, key=lambda c: c.get_order_value())
            return min(legal_moves, key=lambda c: c.get_order_value())
            
        elif game.trump_mode == "open":
            # First cut determines the trump suit.
            # Declare the suit we have the most of, or a strong suit, as trump.
            # Find suit frequencies in hand
            suit_counts = {}
            for c in game.hands[seat_idx]:
                suit_counts[c.suit] = suit_counts.get(c.suit, 0) + 1
            # Sort suits by count descending
            best_suits = sorted(suit_counts.keys(), key=lambda s: suit_counts[s], reverse=True)
            for best_suit in best_suits:
                suit_cards = [c for c in legal_moves if c.suit == best_suit and c.rank != Rank.TEN]
                if suit_cards:
                    # Play highest non-ten of our best suit to make it trump
                    return max(suit_cards, key=lambda c: c.get_order_value())
            return min(legal_moves, key=lambda c: c.get_order_value())

    # Case B: Trump is active and revealed
    trump_cards = [c for c in legal_moves if c.suit == trump_suit]
    if trump_cards and not teammate_winning:
        # Teammate is not winning, play trump to cut and try to win
        # Play lowest trump card that can win
        winning_trumps = []
        for tc in trump_cards:
            temp_trick = list(game.current_trick) + [{"seat_index": seat_idx, "card": tc}]
            winner = determine_trick_winner(temp_trick, led_suit, trump_suit, is_trump_revealed)
            if winner == seat_idx:
                winning_trumps.append(tc)
        if winning_trumps:
            return min(winning_trumps, key=lambda c: c.get_order_value())
        # If none can win, just play the lowest trump if we want to get rid of it, or keep it.
        # Usually, don't waste trump if it can't win. Discard lowest non-trump.
        
    # If teammate is already winning, or we don't have trump/can't win with trump:
    # Discard a card.
    # Prefer discarding 10s (Mindis) to our partner if partner is guaranteed to win!
    if teammate_winning and current_winning_seat is not None:
        # Check if teammate is guaranteed to win (i.e. we are last to play, or teammate's card is unbeatable)
        is_last_play = len(game.current_trick) == 3
        if is_last_play:
            # Partner is winning and we are playing last. Give them a Mindi if we have one!
            mindis = [c for c in legal_moves if c.is_mindi]
            if mindis:
                return mindis[0]
                
    # Otherwise, discard lowest non-value card
    safe_discards = [c for c in legal_moves if not c.is_mindi and c.suit != trump_suit]
    if safe_discards:
        return min(safe_discards, key=lambda c: c.get_order_value())
        
    # Standard fallback: lowest card
    return min(legal_moves, key=lambda c: c.get_order_value())
