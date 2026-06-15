import pytest
from mindi.game.card import Card, Suit, Rank, create_deck, deal_hands
from mindi.game.rules import validate_move, determine_trick_winner, calculate_game_result
from mindi.game.engine import MindiGame, GameState

def test_deck_creation():
    deck = create_deck()
    assert len(deck) == 52
    assert len(set(deck)) == 52
    
    # Check value of 10s is 1 (Mindi) and others are 0
    mindis = [c for c in deck if c.is_mindi]
    assert len(mindis) == 4
    for m in mindis:
        assert m.value == 1
    
    non_mindis = [c for c in deck if not c.is_mindi]
    assert len(non_mindis) == 48
    for nm in non_mindis:
        assert nm.value == 0

def test_deal_hands():
    deck = create_deck()
    hands = deal_hands(deck)
    assert len(hands) == 4
    for hand in hands:
        assert len(hand) == 13
        
    # Verify no duplicates across hands
    all_dealt_cards = set()
    for hand in hands:
        for card in hand:
            all_dealt_cards.add(card)
    assert len(all_dealt_cards) == 52

def test_move_validation():
    # Hand: ♠2, ♠A, ♥K, ♦10
    hand = [
        Card(Suit.SPADES, Rank.TWO),
        Card(Suit.SPADES, Rank.ACE),
        Card(Suit.HEARTS, Rank.KING),
        Card(Suit.DIAMONDS, Rank.TEN)
    ]
    
    # 1. First player can lead anything
    is_valid, msg = validate_move(hand, Card(Suit.HEARTS, Rank.KING), led_suit=None)
    assert is_valid is True
    
    # 2. Must follow suit if they have it
    is_valid, msg = validate_move(hand, Card(Suit.HEARTS, Rank.KING), led_suit=Suit.SPADES)
    assert is_valid is False
    assert "must follow suit" in msg.lower()
    
    is_valid, msg = validate_move(hand, Card(Suit.SPADES, Rank.TWO), led_suit=Suit.SPADES)
    assert is_valid is True
    
    # 3. Can play anything if they don't have the led suit
    is_valid, msg = validate_move(hand, Card(Suit.HEARTS, Rank.KING), led_suit=Suit.CLUBS)
    assert is_valid is True

def test_determine_trick_winner_no_trump():
    # Led suit: Spades
    # Plays: P0: ♠2, P1: ♠A, P2: ♠10, P3: ♠K
    plays = [
        {"seat_index": 0, "card": Card(Suit.SPADES, Rank.TWO)},
        {"seat_index": 1, "card": Card(Suit.SPADES, Rank.ACE)},
        {"seat_index": 2, "card": Card(Suit.SPADES, Rank.TEN)},
        {"seat_index": 3, "card": Card(Suit.SPADES, Rank.KING)}
    ]
    winner = determine_trick_winner(plays, led_suit=Suit.SPADES, trump_suit=None, is_trump_revealed=False)
    assert winner == 1  # ♠A is highest

def test_determine_trick_winner_with_trump():
    # Led suit: Spades, Trump: Hearts (revealed)
    # Plays: P0: ♠A, P1: ♠10, P2: ♥2, P3: ♠K
    plays = [
        {"seat_index": 0, "card": Card(Suit.SPADES, Rank.ACE)},
        {"seat_index": 1, "card": Card(Suit.SPADES, Rank.TEN)},
        {"seat_index": 2, "card": Card(Suit.HEARTS, Rank.TWO)},  # Trump played
        {"seat_index": 3, "card": Card(Suit.SPADES, Rank.KING)}
    ]
    winner = determine_trick_winner(plays, led_suit=Suit.SPADES, trump_suit=Suit.HEARTS, is_trump_revealed=True)
    assert winner == 2  # Trump beats led suit

def test_determine_trick_winner_highest_trump():
    # Led suit: Spades, Trump: Hearts (revealed)
    # Plays: P0: ♠A, P1: ♥10, P2: ♥K, P3: ♠K
    plays = [
        {"seat_index": 0, "card": Card(Suit.SPADES, Rank.ACE)},
        {"seat_index": 1, "card": Card(Suit.HEARTS, Rank.TEN)},  # Trump
        {"seat_index": 2, "card": Card(Suit.HEARTS, Rank.KING)}, # Higher Trump
        {"seat_index": 3, "card": Card(Suit.SPADES, Rank.KING)}
    ]
    winner = determine_trick_winner(plays, led_suit=Suit.SPADES, trump_suit=Suit.HEARTS, is_trump_revealed=True)
    assert winner == 2  # ♥K is highest trump

def test_game_result_calculation():
    # Team 1 wins by Mindis (3 vs 1)
    res = calculate_game_result(team1_mindis=3, team2_mindis=1, team1_tricks=7, team2_tricks=6)
    assert res["winner_team"] == 1
    assert res["is_coat"] is False
    
    # Team 1 wins by coat (4 vs 0)
    res = calculate_game_result(team1_mindis=4, team2_mindis=0, team1_tricks=9, team2_tricks=4)
    assert res["winner_team"] == 1
    assert res["is_coat"] is True
    
    # Tie Mindis (2 vs 2), Team 2 wins by tricks (5 vs 8)
    res = calculate_game_result(team1_mindis=2, team2_mindis=2, team1_tricks=5, team2_tricks=8)
    assert res["winner_team"] == 2
    assert res["is_coat"] is False

def test_consecutive_trick_collection():
    player_ids = [101, 102, 103, 104]
    player_names = ["Alice", "Bob", "Charlie", "David"]
    
    # Start game, dealer=0, starter=1
    game = MindiGame(match_id="TEST-1", player_ids=player_ids, player_names=player_names, trump_mode="open", dealer_idx=0)
    game.state = GameState.PLAYING
    
    # Set custom hands for testing card plays
    # Hand 0: ♠A, ♠Q
    # Hand 1: ♠K, ♠J
    # Hand 2: ♠10, ♠9
    # Hand 3: ♠8, ♠7
    game.hands = [
        [Card(Suit.SPADES, Rank.ACE), Card(Suit.SPADES, Rank.QUEEN)],
        [Card(Suit.SPADES, Rank.KING), Card(Suit.SPADES, Rank.JACK)],
        [Card(Suit.SPADES, Rank.TEN), Card(Suit.SPADES, Rank.NINE)],
        [Card(Suit.SPADES, Rank.EIGHT), Card(Suit.SPADES, Rank.SEVEN)]
    ]
    game.current_turn = 1
    game.starter_idx = 1
    
    # Trick 1: P1 leads ♠K, P2 plays ♠10, P3 plays ♠8, P0 plays ♠A
    # Plays: P1 (♠K), P2 (♠10), P3 (♠8), P0 (♠A)
    # Winner: P0 (Team 1)
    res1 = game.play_card(102, Card(Suit.SPADES, Rank.KING))
    assert res1["success"] is True
    res2 = game.play_card(103, Card(Suit.SPADES, Rank.TEN))
    assert res2["success"] is True
    res3 = game.play_card(104, Card(Suit.SPADES, Rank.EIGHT))
    assert res3["success"] is True
    res4 = game.play_card(101, Card(Suit.SPADES, Rank.ACE))
    assert res4["success"] is True
    assert res4["next_state"] == "trick_complete"
    assert res4["trick_winner"] == 0
    assert res4["collected"] is False  # First trick of game - not collected yet
    
    # Under Dehla Pakad, center pile accumulates cards
    assert len(game.center_pile) == 4
    assert game.team1_mindis == 0
    assert game.team2_mindis == 0
    assert game.last_trick_winner == 0
    
    # Trick 2: Next turn is P0 (Team 1).
    # Hand 0: ♠Q
    # Hand 1: ♠J
    # Hand 2: ♠9
    # Hand 3: ♠7
    # P0 leads ♠Q, P1 plays ♠J, P2 plays ♠9, P3 plays ♠7
    # Winner: P0 (Team 1)
    assert game.current_turn == 0
    game.play_card(101, Card(Suit.SPADES, Rank.QUEEN))
    game.play_card(102, Card(Suit.SPADES, Rank.JACK))
    game.play_card(103, Card(Suit.SPADES, Rank.NINE))
    event = game.play_card(104, Card(Suit.SPADES, Rank.SEVEN))
    
    assert event["next_state"] == "trick_complete"
    assert event["trick_winner"] == 0
    assert event["collected"] is True  # Team 1 wins consecutively - collected!
    
    # Center pile is cleared
    assert len(game.center_pile) == 0
    # Team 1 collects both tricks (including the ♠10 from Trick 1)
    assert game.team1_mindis == 1
    assert game.team2_mindis == 0

def test_hidden_hukum_rules():
    player_ids = [101, 102, 103, 104]
    player_names = ["Alice", "Bob", "Charlie", "David"]
    
    # Dealer is 0, so dealer partner is (0+2)%4 = 2.
    game = MindiGame(match_id="TEST-HIDDEN", player_ids=player_ids, player_names=player_names, trump_mode="hidden", dealer_idx=0)
    game.start_game()
    
    assert game.state == GameState.SELECTING_TRUMP
    assert game.hidden_trump_selector_idx == 2
    
    # Verify that dealer partner has 13 cards
    assert len(game.hands[2]) == 13
    
    # Partner selects a card as Hidden Hukam
    chosen_card = game.hands[2][0]
    success, err = game.select_hidden_trump(2, chosen_card)
    assert success is True
    assert err == ""
    
    # State transitions to PLAYING
    assert game.state == GameState.PLAYING
    assert game.hidden_hukum_card == chosen_card.to_string()
    assert game.trump_suit == chosen_card.suit
    assert game.is_trump_revealed is False
    
    # Dealer partner should now have 12 cards
    assert len(game.hands[2]) == 12
    assert chosen_card not in game.hands[2]
    
    # Let's test the follow suit and reveal rule during gameplay
    # Led suit is Spades. P0 has ♠A. P1 has no Spades, only Hearts.
    # Partner is P2.
    game.hands = [
        [Card(Suit.SPADES, Rank.ACE)], # P0
        [Card(Suit.HEARTS, Rank.ACE)], # P1
        [], # P2 (partner, empty hand for test)
        [Card(Suit.SPADES, Rank.KING)] # P3
    ]
    game.current_turn = 0
    game.starter_idx = 0
    
    # P0 leads ♠A
    res_lead = game.play_card(101, Card(Suit.SPADES, Rank.ACE))
    assert res_lead["success"] is True
    assert game.current_turn == 1
    
    # P1 has no Spades. They cannot follow suit.
    # Therefore, they can reveal the Hidden Hukam.
    # Verify they can call reveal_hidden_hukum
    success, err, card_str = game.reveal_hidden_hukum(1)
    assert success is True
    assert err == ""
    assert card_str == chosen_card.to_string()
    
    # Trump should now be revealed
    assert game.is_trump_revealed is True
    assert game.trump_revealer_idx == 1
    
    # The hidden card should be returned to P2's hand (dealer's partner)
    assert len(game.hands[2]) == 1
    assert game.hands[2][0] == chosen_card

