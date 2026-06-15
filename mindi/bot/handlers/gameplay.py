import logging
import asyncio
from typing import List, Dict, Any, Optional
from pyrogram import filters
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InlineQueryResultArticle, InlineQueryResultPhoto, InputTextMessageContent
from mindi.bot.bot import bot
from mindi.cache.redis_client import get_redis_client, set_cache, get_cache, delete_cache
from mindi.game.card import Card, Suit, Rank
from mindi.game.engine import MindiGame, GameState
from mindi.game.ai import get_ai_move
from mindi.database.db import AsyncSessionLocal
from mindi.database.models import User, Match, MatchPlayer
from sqlalchemy import select

logger = logging.getLogger(__name__)

# K-Factor for ELO
K_FACTOR = 32

def get_card_image_url(card: Card) -> str:
    """Generates a free card image URL from deckofcardsapi.com."""
    suit_map = {Suit.SPADES: "S", Suit.HEARTS: "H", Suit.DIAMONDS: "D", Suit.CLUBS: "C"}
    rank_map = {
        Rank.ACE: "A", Rank.TWO: "2", Rank.THREE: "3", Rank.FOUR: "4", Rank.FIVE: "5",
        Rank.SIX: "6", Rank.SEVEN: "7", Rank.EIGHT: "8", Rank.NINE: "9", Rank.TEN: "0",
        Rank.JACK: "J", Rank.QUEEN: "Q", Rank.KING: "K"
    }
    s = suit_map[card.suit]
    r = rank_map[card.rank]
    return f"https://deckofcardsapi.com/static/img/{r}{s}.png"


def format_hand_keyboard(game: MindiGame, seat_idx: int, is_hukum_selection: bool = False) -> InlineKeyboardMarkup:
    """Formats the player's hand as a grid of buttons. Disables illegal moves if it is their turn."""
    hand = game.hands[seat_idx]
    is_my_turn = (game.current_turn == seat_idx) or is_hukum_selection
    
    legal_cards = hand if is_hukum_selection else (game.get_legal_moves(seat_idx) if is_my_turn else [])
    
    rows = []
    current_row = []
    
    for card in hand:
        card_str = card.to_string()
        is_legal = card in legal_cards
        
        if is_hukum_selection:
            callback_data = f"game:sethukum:{game.match_id}:{card_str}"
            btn_text = card_str
        else:
            if is_my_turn and is_legal:
                callback_data = f"game:play:{game.match_id}:{card_str}"
                btn_text = card_str
            else:
                callback_data = "game:noop"
                btn_text = f"❌ {card_str}" if is_my_turn else card_str
            
        current_row.append(InlineKeyboardButton(btn_text, callback_data=callback_data))
        
        if len(current_row) == 4:
            rows.append(current_row)
            current_row = []
            
    if current_row:
        rows.append(current_row)
        
    return InlineKeyboardMarkup(rows)

async def update_player_hand_message(player_id: int, game: MindiGame):
    """Edits or sends the private hand message in the player's DM."""
    try:
        seat_idx = game.get_player_seat(player_id)
    except ValueError:
        return
        
    is_hukum_selection = (game.state == GameState.SELECTING_TRUMP and game.hidden_trump_selector_idx == seat_idx)
    is_my_turn = (game.current_turn == seat_idx) or is_hukum_selection
    
    if game.state == GameState.SELECTING_TRUMP:
        if is_hukum_selection:
            status_text = (
                f"🤫 **Hidden Hukam Selection - Match {game.match_id}**\n"
                f"You are the dealer's partner! Please choose a card from your hand below to serve as the Hidden Hukam:"
            )
            markup = format_hand_keyboard(game, seat_idx, is_hukum_selection=True)
        else:
            selector_name = game.player_names[game.hidden_trump_selector_idx]
            status_text = (
                f"⏳ **Match {game.match_id}**\n"
                f"Waiting for dealer's partner (**{selector_name}**) to select the Hidden Hukam card..."
            )
            markup = None
    else:
        trump_status = "Not Selected"
        if game.trump_suit:
            status_suffix = "Revealed" if game.is_trump_revealed else "Hidden"
            trump_status = f"{game.trump_suit.value} ({status_suffix})"
            
        status_text = (
            f"🃏 **Your Hand - Match {game.match_id}**\n"
            f"👑 Trump Suit: `{trump_status}`\n\n"
        )
        
        if is_my_turn:
            status_text += "🚨 **YOUR TURN!** Play a legal card:"
        else:
            current_turn_name = game.player_names[game.current_turn]
            status_text += f"⌛ Waiting for **{current_turn_name}** to play..."

        markup = format_hand_keyboard(game, seat_idx, is_hukum_selection=False)
        
    msg_id = await get_cache(f"mindi:player_hand_msg:{player_id}")
    success = False
    if msg_id:
        try:
            await bot.edit_message_text(
                chat_id=player_id,
                message_id=msg_id,
                text=status_text,
                reply_markup=markup
            )
            success = True
        except Exception:
            pass
            
    if not success:
        try:
            msg = await bot.send_message(
                chat_id=player_id,
                text=status_text,
                reply_markup=markup
            )
            await set_cache(f"mindi:player_hand_msg:{player_id}", msg.id)
        except Exception as e:
            logger.error(f"Failed to send hand message to {player_id}: {e}")

async def update_group_game_message(game: MindiGame, trick_result_msg: str = ""):
    """Edits the active group message with the game state and the inline query button."""
    plays_text = []
    for p in game.current_trick:
        name = game.player_names[p["seat_index"]]
        plays_text.append(f"• **{name}** played `{p['card'].to_string()}`")
        
    plays_str = "\n".join(plays_text) if plays_text else "*No cards played yet.*"
    
    trump_str = "None"
    if game.trump_suit:
        trump_str = f"{game.trump_suit.value} (Revealed)" if game.is_trump_revealed else "Hidden"
        
    t1_p1 = game.player_names[0]
    t1_p2 = game.player_names[2]
    t2_p1 = game.player_names[1]
    t2_p2 = game.player_names[3]

    status_text = (
        f"📊 **Mindi Match: {game.match_id}**\n\n"
        f"{trick_result_msg}\n"
        f"🃏 **Current Trick:**\n{plays_str}\n\n"
        f"👑 Trump Suit: `{trump_str}`\n"
        f"👥 **Scores (captured Mindis / Tricks won):**\n"
        f"• **Team 1** ({t1_p1} & {t1_p2}): `{game.team1_mindis}` Mindis | `{game.team1_tricks}` Tricks\n"
        f"• **Team 2** ({t2_p1} & {t2_p2}): `{game.team2_mindis}` Mindis | `{game.team2_tricks}` Tricks\n\n"
    )
    
    markup = None
    if game.state == GameState.PLAYING:
        current_player = game.player_names[game.current_turn]
        current_player_id = game.player_ids[game.current_turn]
        current_player_mention = f"[{current_player}](tg://user?id={current_player_id})" if current_player_id > 0 else f"**{current_player}**"
        status_text += f"🚨 Turn: {current_player_mention} (Click the button below to choose your card privately):"
        
        # Determine if we should show the [ 🔓 Reveal Hidden Hukam ] button
        led_suit = game.get_led_suit()
        show_reveal_button = False
        if led_suit is not None and game.trump_mode == "hidden" and not game.is_trump_revealed:
            # Check if this player has no cards of the led suit
            current_hand = game.hands[game.current_turn]
            has_led_suit = any(c.suit == led_suit for c in current_hand)
            if not has_led_suit:
                show_reveal_button = True
                
        buttons = []
        if show_reveal_button:
            buttons.append([InlineKeyboardButton("🔓 Reveal Hidden Hukam", callback_data=f"game:reveal_hukum:{game.match_id}")])
            
        buttons.append([InlineKeyboardButton("🎴 Play a Card", switch_inline_query_current_chat=game.match_id)])
        markup = InlineKeyboardMarkup(buttons)
    elif game.state == GameState.COMPLETED:
        pass
        
    try:
        if game.group_msg_id:
            try:
                await bot.delete_messages(chat_id=game.group_chat_id, message_ids=game.group_msg_id)
            except Exception:
                pass
        msg = await bot.send_message(
            chat_id=game.group_chat_id,
            text=status_text,
            reply_markup=markup
        )
        game.group_msg_id = msg.id
        await set_cache(f"mindi:game:{game.match_id}", game.to_dict())
    except Exception as e:
        logger.error(f"Failed to send group message: {e}")

async def update_game_ui(game: MindiGame, trick_result_msg: str = ""):
    """Updates both the group game board or all individual player private hand keyboards in DM."""
    if game.group_chat_id:
        await update_group_game_message(game, trick_result_msg)
    else:
        # DM Game fallback
        tasks = []
        for pid in game.player_ids:
            if pid > 0:
                tasks.append(update_player_hand_message(pid, game))
        if tasks:
            await asyncio.gather(*tasks)

async def start_game_round(game: MindiGame):
    """Starts the gameplay loop."""
    await update_game_ui(game)
    
    # Broadcast starter info if DM game
    if not game.group_chat_id:
        await broadcast_trick_status(game)
        
    # Check if first player is AI
    await check_and_run_ai_turns(game)

async def broadcast_trick_status(game: MindiGame, trick_result_msg: str = ""):
    """Broadcasts trick status to DMs (only used in DM-based matchmaking fallback)."""
    plays_text = []
    for p in game.current_trick:
        name = game.player_names[p["seat_index"]]
        plays_text.append(f"• **{name}** played `{p['card'].to_string()}`")
        
    plays_str = "\n".join(plays_text) if plays_text else "*No cards played yet.*"
    
    trump_str = "None"
    if game.trump_suit:
        trump_str = f"{game.trump_suit.value} (Revealed)" if game.is_trump_revealed else "Hidden"
        
    t1_p1 = game.player_names[0]
    t1_p2 = game.player_names[2]
    t2_p1 = game.player_names[1]
    t2_p2 = game.player_names[3]

    status_text = (
        f"📊 **Match Status: {game.match_id}**\n\n"
        f"{trick_result_msg}\n"
        f"🃏 **Current Trick:**\n{plays_str}\n\n"
        f"👑 Trump Suit: `{trump_str}`\n"
        f"👥 **Scores (captured Mindis / Tricks):**\n"
        f"• **Team 1** ({t1_p1} & {t1_p2}): `{game.team1_mindis}` Mindis | `{game.team1_tricks}` Tricks\n"
        f"• **Team 2** ({t2_p1} & {t2_p2}): `{game.team2_mindis}` Mindis | `{game.team2_tricks}` Tricks\n\n"
    )
    
    if game.state == GameState.PLAYING:
        current_player = game.player_names[game.current_turn]
        status_text += f"🚨 Next turn: **{current_player}**"
        
    for pid in game.player_ids:
        if pid > 0:
            try:
                await bot.send_message(chat_id=pid, text=status_text)
            except Exception:
                pass

async def process_game_completion(game: MindiGame, result: dict):
    """Handles ELO calculation and posts results to group or DMs."""
    winner_team = result["winner_team"]
    is_coat = result["is_coat"]
    
    rating_changes = await update_elo_ratings(game, winner_team)
    
    t1_p1 = game.player_names[0]
    t1_p2 = game.player_names[2]
    t2_p1 = game.player_names[1]
    t2_p2 = game.player_names[3]
    
    winner_names = f"{t1_p1} & {t1_p2}" if winner_team == 1 else f"{t2_p1} & {t2_p2}"
    
    summary = (
        f"🏁 **GAME OVER - Match {game.match_id}!**\n\n"
        f"🏆 **Winner: Team {winner_team}** ({winner_names}) "
        f"{'💥 (COAT / WHITEWASH!)' if is_coat else ''}\n\n"
        f"📊 **Final Score:**\n"
        f"• **Team 1** ({t1_p1} & {t1_p2}): `{game.team1_mindis}` Mindis | `{game.team1_tricks}` Tricks\n"
        f"• **Team 2** ({t2_p1} & {t2_p2}): `{game.team2_mindis}` Mindis | `{game.team2_tricks}` Tricks\n\n"
        f"📈 **ELO Changes:**\n"
    )
    
    for idx, pid in enumerate(game.player_ids):
        name = game.player_names[idx]
        change = rating_changes.get(pid, 0)
        change_str = f"+{change}" if change >= 0 else f"{change}"
        if pid > 0:
            summary += f"• **{name}**: `{change_str}` ELO\n"
        else:
            summary += f"• **{name} (AI)**: `--`\n"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚪 Return to Main Menu", callback_data="menu:main")]
    ])
    
    if game.group_chat_id:
        try:
            await bot.send_message(chat_id=game.group_chat_id, text=summary, reply_markup=keyboard)
        except Exception:
            pass
            
    for pid in game.player_ids:
        if pid > 0:
            try:
                if not game.group_chat_id:
                    await bot.send_message(chat_id=pid, text=summary, reply_markup=keyboard)
            except Exception:
                pass
            await delete_cache(f"mindi:player_game:{pid}")
            await delete_cache(f"mindi:player_hand_msg:{pid}")
            
    await delete_cache(f"mindi:game:{game.match_id}")

async def update_elo_ratings(game: MindiGame, winner_team: int) -> Dict[int, int]:
    """Applies ELO score rating adjustments to users database."""
    rating_changes = {}
    human_ids = [pid for pid in game.player_ids if pid > 0]
    if not human_ids:
        return {}
        
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(User).filter(User.telegram_id.in_(human_ids)))
        users = {u.telegram_id: u for u in res.scalars().all()}
        
        t1_ratings = []
        t2_ratings = []
        for idx, pid in enumerate(game.player_ids):
            rating = users[pid].rating if pid in users else 1000
            if idx in [0, 2]:
                t1_ratings.append(rating)
            else:
                t2_ratings.append(rating)
                
        avg_r1 = sum(t1_ratings) / 2
        avg_r2 = sum(t2_ratings) / 2
        
        exp1 = 1 / (1 + 10 ** ((avg_r2 - avg_r1) / 400))
        s1 = 1 if winner_team == 1 else 0
        shift_t1 = int(K_FACTOR * (s1 - exp1))
        shift_t2 = -shift_t1
        
        for idx, pid in enumerate(game.player_ids):
            if pid <= 0:
                continue
            won = (winner_team == 1 and idx in [0, 2]) or (winner_team == 2 and idx in [1, 3])
            change = shift_t1 if idx in [0, 2] else shift_t2
            mindis = game.team1_mindis if idx in [0, 2] else game.team2_mindis
            
            rating_changes[pid] = change
            if pid in users:
                db_user = users[pid]
                db_user.update_stats(won=won, rating_change=change, mindis_captured=mindis)
                
        # Update match status in Postgres
        match_res = await session.execute(
            select(Match).filter(Match.status == "playing").order_by(Match.id.desc()).limit(1)
        )
        db_match = match_res.scalars().first()
        if db_match:
            db_match.status = "completed"
            db_match.winner_team = winner_team
            db_match.trump_suit = game.trump_suit.value if game.trump_suit else None
            db_match.is_trump_revealed = game.is_trump_revealed
            
        await session.commit()
        
    return rating_changes

async def check_and_run_ai_turns(game: MindiGame):
    """Processes AI turns automatically if the next active seat belongs to an AI."""
    while game.state == GameState.PLAYING and game.player_ids[game.current_turn] <= 0:
        await asyncio.sleep(1.0)
        
        ai_seat = game.current_turn
        ai_id = game.player_ids[ai_seat]
        
        try:
            ai_card = get_ai_move(game, ai_seat, level="medium")
            event = game.play_card(ai_id, ai_card)
            
            await set_cache(f"mindi:game:{game.match_id}", game.to_dict())
            
            play_msg = f"🤖 **{game.player_names[ai_seat]} (AI)** played `{ai_card.to_string()}`."
            if event.get("revealed_trump"):
                play_msg += f"\n💥 **Trump Suit Revealed:** `{event['trump_suit']}`!"
                
            if event["next_state"] == "trick_complete":
                trick_result = (
                    f"{play_msg}\n\n"
                    f"🏆 Trick won by **{event['trick_winner_name']}** with `{ai_card.to_string()}`!\n"
                )
                trick_result += f"📥 Collected `{sum(Card.from_string(c).value for c in event['collected_cards'])}` Mindis!"
                
                # Clear buttons temporarily
                if game.group_chat_id:
                    try:
                        if game.group_msg_id:
                            try:
                                await bot.delete_messages(chat_id=game.group_chat_id, message_ids=game.group_msg_id)
                            except Exception:
                                pass
                        msg = await bot.send_message(
                            chat_id=game.group_chat_id,
                            text=f"📊 **Mindi Match: {game.match_id}**\n\n{trick_result}\n\n*Next trick starting...*"
                        )
                        game.group_msg_id = msg.id
                        await set_cache(f"mindi:game:{game.match_id}", game.to_dict())
                    except Exception:
                        pass
                else:
                    await broadcast_trick_status(game, trick_result)
                    
                # Delay for players to see the result
                await asyncio.sleep(1.5)
                await update_game_ui(game)
                
            elif event["next_state"] == "game_completed":
                await process_game_completion(game, event["result"])
                break
            else:
                if not game.group_chat_id:
                    await broadcast_trick_status(game, play_msg)
                await update_game_ui(game)
                
        except Exception as e:
            logger.error(f"Error in AI execution on seat {ai_seat}: {e}")
            break


# ------------------ TELEGRAM HANDLERS ------------------

@bot.on_inline_query()
async def on_inline_query_handler(client, inline_query):
    """Processes inline query requests to fetch and display the player's hand privately in a popup."""
    query_str = inline_query.query.strip()
    player_id = inline_query.from_user.id
    
    is_hukum_query = False
    match_id = None
    if ":" in query_str:
        parts = query_str.split(":")
        if len(parts) == 2 and parts[1] == "hukum":
            is_hukum_query = True
            match_id = parts[0]
            
    if is_hukum_query:
        game_data = await get_cache(f"mindi:game:{match_id}")
        if not game_data:
            results = [
                InlineQueryResultArticle(
                    id="no_game",
                    title="⚠️ No Active Match Found",
                    description="Make sure you are in a game and it has started.",
                    input_message_content=InputTextMessageContent("No active Mindi game.")
                )
            ]
            await inline_query.answer(results, cache_time=0, is_personal=True)
            return
            
        game = MindiGame.from_dict(game_data)
        try:
            seat_idx = game.get_player_seat(player_id)
        except ValueError:
            results = [
                InlineQueryResultArticle(
                    id="not_player",
                    title="⚠️ You are not in this game",
                    description="This match does not contain you as a player.",
                    input_message_content=InputTextMessageContent("I am not a participant in this game.")
                )
            ]
            await inline_query.answer(results, cache_time=0, is_personal=True)
            return
            
        if game.state != GameState.SELECTING_TRUMP:
            results = [
                InlineQueryResultArticle(
                    id="wrong_state",
                    title="⚠️ Game is not in Trump Selection state",
                    description="The game is already playing or lobby.",
                    input_message_content=InputTextMessageContent("Wrong game state.")
                )
            ]
            await inline_query.answer(results, cache_time=0, is_personal=True)
            return
            
        if seat_idx != game.hidden_trump_selector_idx:
            results = [
                InlineQueryResultArticle(
                    id="not_selector",
                    title="⚠️ You are not the dealer's partner",
                    description="Only the dealer's partner can select the Hidden Hukam card.",
                    input_message_content=InputTextMessageContent("I am not the dealer's partner.")
                )
            ]
            await inline_query.answer(results, cache_time=0, is_personal=True)
            return
            
        # Return all 13 cards of the dealer partner
        results = []
        for card in game.hands[seat_idx]:
            card_str = card.to_string()
            img_url = get_card_image_url(card)
            padded_img_url = f"https://images.weserv.nl/?url={img_url}&w=314&h=314&fit=contain"
            results.append(
                InlineQueryResultPhoto(
                    id=f"sethukum:{game.match_id}:{card_str}",
                    photo_url=padded_img_url,
                    thumb_url=padded_img_url,
                    title=card_str,
                    description=f"Set the {card.rank.value} of {card.suit.name} as Hidden Hukam.",
                    input_message_content=InputTextMessageContent(
                        message_text=f"mindi_hukum {game.match_id} {card_str}"
                    )
                )
            )
        await inline_query.answer(results, cache_time=0, is_personal=True)
        return

    # Normal card play inline query
    # 1. Lookup match state
    game_data = await get_cache(f"mindi:game:{query_str}")
    if not game_data:
        # Fallback to search player active match
        m_id = await get_cache(f"mindi:player_game:{player_id}")
        if m_id:
            game_data = await get_cache(f"mindi:game:{m_id}")
            
    if not game_data:
        results = [
            InlineQueryResultArticle(
                id="no_game",
                title="⚠️ No Active Match Found",
                description="Make sure you are in a game and it has started.",
                input_message_content=InputTextMessageContent("No active Mindi game.")
            )
        ]
        await inline_query.answer(results, cache_time=0, is_personal=True)
        return
        
    game = MindiGame.from_dict(game_data)
    try:
        seat_idx = game.get_player_seat(player_id)
    except ValueError:
        results = [
            InlineQueryResultArticle(
                id="not_player",
                title="⚠️ You are not in this game",
                description="This match does not contain you as a player.",
                input_message_content=InputTextMessageContent("I am not a participant in this game.")
            )
        ]
        await inline_query.answer(results, cache_time=0, is_personal=True)
        return
        
    # 2. Check turn
    if game.current_turn != seat_idx:
        current_turn_name = game.player_names[game.current_turn]
        results = [
            InlineQueryResultArticle(
                id="not_turn",
                title="⌛ It is not your turn yet",
                description=f"Waiting for {current_turn_name} to play.",
                input_message_content=InputTextMessageContent(f"Waiting for my turn in match {game.match_id}.")
            )
        ]
        await inline_query.answer(results, cache_time=0, is_personal=True)
        return
        
    # 3. Retrieve legal card plays
    legal_moves = game.get_legal_moves(seat_idx)
    results = []
    
    for card in legal_moves:
        card_str = card.to_string()
        img_url = get_card_image_url(card)
        padded_img_url = f"https://images.weserv.nl/?url={img_url}&w=314&h=314&fit=contain"
        results.append(
            InlineQueryResultPhoto(
                id=f"play:{game.match_id}:{card_str}",
                photo_url=padded_img_url,
                thumb_url=padded_img_url,
                title=card_str,
                description=f"Play the {card.rank.value} of {card.suit.name}",
                input_message_content=InputTextMessageContent(
                    message_text=f"mindi_play {game.match_id} {card_str}"
                )
            )
        )
        
    await inline_query.answer(results, cache_time=0, is_personal=True)


@bot.on_message(filters.regex(r"^mindi_hukum\s+(\S+)\s+(\S+)$") & filters.group)
async def on_set_hukum_command(client, message):
    """Processes Hidden Hukam selection initiated from inline query choice."""
    match_id = message.matches[0].group(1)
    card_str = message.matches[0].group(2)
    player_id = message.from_user.id
    
    logger.info(f"Received mindi_hukum command in group chat {message.chat.id}: {message.text}")
    try:
        await message.delete()
    except Exception:
        pass
        
    game_data = await get_cache(f"mindi:game:{match_id}")
    if not game_data:
        return
        
    game = MindiGame.from_dict(game_data)
    try:
        seat_idx = game.get_player_seat(player_id)
    except ValueError:
        return
        
    if game.state != GameState.SELECTING_TRUMP or seat_idx != game.hidden_trump_selector_idx:
        return
        
    try:
        card = Card.from_string(card_str)
    except ValueError:
        return
        
    success, err = game.select_hidden_trump(seat_idx, card)
    if not success:
        logger.error(f"Failed to select hidden trump: {err}")
        return
        
    await set_cache(f"mindi:game:{match_id}", game.to_dict())
    
    selector_name = game.player_names[seat_idx]
    if game.group_chat_id:
        try:
            await bot.send_message(
                chat_id=game.group_chat_id,
                text=f"🤫 **Hidden Hukam Selected!**\nDealer's partner **{selector_name}** has chosen the Hidden Hukam card. Let the game begin!"
            )
        except Exception as e:
            logger.error(f"Failed to send confirmation to group: {e}")
            
    await start_game_round(game)


@bot.on_message(filters.regex(r"^mindi_play\s+(\S+)\s+(\S+)$") & filters.group)
async def on_play_command_group(client, message):
    """Processes card plays initiated from the inline query choice message in group chat."""
    match_id = message.matches[0].group(1)
    card_str = message.matches[0].group(2)
    player_id = message.from_user.id
    
    logger.info(f"Received ?play command in group chat {message.chat.id}: {message.text}")
    # Attempt to delete the command message to keep group chat clean
    try:
        await message.delete()
    except Exception:
        pass
        
    game_data = await get_cache(f"mindi:game:{match_id}")
    if not game_data:
        return
        
    game = MindiGame.from_dict(game_data)
    try:
        seat_idx = game.get_player_seat(player_id)
    except ValueError:
        return
        
    if game.current_turn != seat_idx:
        return
        
    try:
        card = Card.from_string(card_str)
    except ValueError:
        return
    
    # Execute play
    event = game.play_card(player_id, card)
    if not event["success"]:
        return
        
    # Save Game state
    await set_cache(f"mindi:game:{match_id}", game.to_dict())
    
    play_msg = f"👤 **{game.player_names[seat_idx]}** played `{card.to_string()}`."
        
    if event.get("revealed_trump"):
        play_msg += f"\n💥 **Trump Suit Revealed:** `{event['trump_suit']}`!"

    if event["next_state"] == "trick_complete":
        trick_result = (
            f"{play_msg}\n\n"
            f"🏆 Trick won by **{event['trick_winner_name']}**!\n"
        )
        trick_result += f"📥 Collected `{sum(Card.from_string(c).value for c in event['collected_cards'])}` Mindis!"
        
        # Display trick result
        if game.group_chat_id:
            try:
                if game.group_msg_id:
                    try:
                        await bot.delete_messages(chat_id=game.group_chat_id, message_ids=game.group_msg_id)
                    except Exception:
                        pass
                msg = await bot.send_message(
                    chat_id=game.group_chat_id,
                    text=f"📊 **Mindi Match: {game.match_id}**\n\n{trick_result}\n\n*Next trick starting...*"
                )
                game.group_msg_id = msg.id
                await set_cache(f"mindi:game:{game.match_id}", game.to_dict())
            except Exception:
                pass
        else:
            await update_game_ui(game)
            
        await asyncio.sleep(1.5)
        await update_game_ui(game)
        
    elif event["next_state"] == "game_completed":
        await process_game_completion(game, event["result"])
        return
        
    else:
        await update_game_ui(game)
        
    # Run AI turns
    await check_and_run_ai_turns(game)


@bot.on_callback_query(filters.regex(r"^game:reveal_hukum:(.+)$"))
async def on_reveal_hukum_callback(client, callback_query: CallbackQuery):
    """Processes the Hidden Hukam reveal request when a player cannot follow suit."""
    match_id = callback_query.matches[0].group(1)
    player_id = callback_query.from_user.id
    
    game_data = await get_cache(f"mindi:game:{match_id}")
    if not game_data:
        await callback_query.answer("⚠️ Match not found or expired.", show_alert=True)
        return
        
    game = MindiGame.from_dict(game_data)
    try:
        seat_idx = game.get_player_seat(player_id)
    except ValueError:
        await callback_query.answer("⚠️ You are not in this game.", show_alert=True)
        return
        
    if game.current_turn != seat_idx:
        await callback_query.answer("⚠️ It is not your turn to play or reveal!", show_alert=True)
        return
        
    led_suit = game.get_led_suit()
    if led_suit is None:
        await callback_query.answer("⚠️ You can only reveal Hukam when following suit is required and you don't have it.", show_alert=True)
        return
        
    has_led_suit = any(c.suit == led_suit for c in game.hands[seat_idx])
    if has_led_suit:
        await callback_query.answer("⚠️ You must follow suit! You cannot reveal Hukam.", show_alert=True)
        return
        
    success, err, card_str = game.reveal_hidden_hukum(seat_idx)
    if not success:
        await callback_query.answer(f"⚠️ {err}", show_alert=True)
        return
        
    await set_cache(f"mindi:game:{match_id}", game.to_dict())
    
    partner_name = game.player_names[(game.dealer_idx + 2) % 4]
    reveal_msg = (
        f"🔓 **Hukam Revealed!**\n"
        f"👤 **{game.player_names[seat_idx]}** could not follow suit and chose to reveal the Hidden Hukam!\n"
        f"🃏 The hidden card was `{card_str}`. "
        f"👑 Trump suit is now `{game.trump_suit.value}`!\n"
        f"📥 The card has been returned to **{partner_name}**'s hand."
    )
    
    await callback_query.answer(f"🔓 Revealed Hidden Hukam: {card_str}! Trump suit is {game.trump_suit.name}.")
    
    await update_game_ui(game, trick_result_msg=reveal_msg)


@bot.on_callback_query(filters.regex(r"^game:noop$"))
async def on_noop_callback(client, callback_query: CallbackQuery):
    await callback_query.answer("⚠️ Not a legal card to play or not your turn!", show_alert=False)


@bot.on_message(filters.command(["stop", "cancel", "abort"]) & filters.group)
async def on_stop_game_command(client, message):
    """Aborts/stops the current active game in the group chat."""
    player_id = message.from_user.id
    player_name = message.from_user.first_name
    group_chat_id = message.chat.id
    
    logger.info(f"Received stop/cancel/abort command in group {group_chat_id} from {player_name} ({player_id})")
    
    # 1. Look up the player's active match ID
    match_id = await get_cache(f"mindi:player_game:{player_id}")
    if not match_id:
        await message.reply_text("⚠️ You are not in an active Mindi match!")
        return
        
    game_data = await get_cache(f"mindi:game:{match_id}")
    if not game_data:
        await delete_cache(f"mindi:player_game:{player_id}")
        await message.reply_text("⚠️ No active game data found.")
        return
        
    game = MindiGame.from_dict(game_data)
    
    # Verify the match belongs to this group chat
    if game.group_chat_id != group_chat_id:
        await message.reply_text("⚠️ This match is active in another group chat!")
        return
        
    # 2. Abort match in Postgres DB
    async with AsyncSessionLocal() as session:
        # Match ELO rating calculations are skipped for aborted matches
        db_match_id = match_id.split("-")[-1]
        try:
            db_match_id_int = int(db_match_id)
            match_res = await session.execute(
                select(Match).filter(Match.id == db_match_id_int)
            )
            db_match = match_res.scalars().first()
            if db_match:
                db_match.status = "aborted"
                await session.commit()
        except ValueError:
            pass
            
    # 3. Clear cache keys for all game participants
    for pid in game.player_ids:
        if pid > 0:
            await delete_cache(f"mindi:player_game:{pid}")
            await delete_cache(f"mindi:player_hand_msg:{pid}")
            
    # 4. Delete the game board message to clean up the chat
    if game.group_msg_id:
        try:
            await bot.delete_messages(chat_id=group_chat_id, message_ids=game.group_msg_id)
        except Exception as e:
            logger.warning(f"Failed to delete aborted board message: {e}")
            
    # 5. Remove the game state from cache
    await delete_cache(f"mindi:game:{match_id}")
    
    await message.reply_text(f"🛑 **Match terminated!**\nThe current game has been aborted by **{player_name}**.")
