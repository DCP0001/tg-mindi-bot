import logging
import random
from pyrogram import filters
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ChatType
from mindi.bot.bot import bot
from mindi.cache.redis_client import get_redis_client, set_cache, get_cache, delete_cache
from mindi.cache.matchmaker import add_to_queue, remove_from_queue, check_and_create_match, get_queue_players
from mindi.game.engine import MindiGame, GameState
from mindi.database.db import AsyncSessionLocal
from mindi.database.models import User, Match, MatchPlayer
from sqlalchemy import select

logger = logging.getLogger(__name__)

# Helper to format player names in lobbies
def format_lobby_players(players_list) -> str:
    lines = []
    for i, p in enumerate(players_list, 1):
        lines.append(f"{i}. **{p['name']}**")
    for i in range(len(players_list) + 1, 5):
        lines.append(f"{i}. *Waiting for player...*")
    return "\n".join(lines)

def get_lobby_keyboard(lobby_data: dict) -> InlineKeyboardMarkup:
    lobby_id = lobby_data["lobby_id"]
    trump_mode = lobby_data["trump_mode"]
    
    open_indicator = " ✅" if trump_mode == "open" else ""
    hidden_indicator = " ✅" if trump_mode == "hidden" else ""
    
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Join", callback_data=f"lobby:join:{lobby_id}"),
            InlineKeyboardButton("Leave", callback_data=f"lobby:leave:{lobby_id}")
        ],
        [
            InlineKeyboardButton(f"🔓 Open Hukam{open_indicator}", callback_data=f"lobby:set_trump:open:{lobby_id}"),
            InlineKeyboardButton(f"🤫 Hidden Hukam{hidden_indicator}", callback_data=f"lobby:set_trump:hidden:{lobby_id}")
        ],
        [
            InlineKeyboardButton("🚀 Start Game (Host)", callback_data=f"lobby:start:{lobby_id}")
        ]
    ])

# Start game helper (used by both Matchmaking and Table Lobbies)
async def initialize_and_start_game(match_id: str, players_info: list, mode: str, trump_mode: str, group_chat_id: int = None):
    # Initialize Game Engine
    player_ids = [p["id"] for p in players_info]
    player_names = [p["name"] for p in players_info]
    
    # Random dealer selection
    dealer_idx = random.randint(0, 3)
    
    game = MindiGame(
        match_id=match_id,
        player_ids=player_ids,
        player_names=player_names,
        trump_mode=trump_mode,
        dealer_idx=dealer_idx,
        group_chat_id=group_chat_id
    )
    game.start_game()
    
    # If running in a Telegram group, send active game message to group
    if group_chat_id:
        try:
            dealer_id = player_ids[dealer_idx]
            dealer_mention = f"[{player_names[dealer_idx]}](tg://user?id={dealer_id})" if dealer_id > 0 else f"**{player_names[dealer_idx]}**"
            start_msg = await bot.send_message(
                chat_id=group_chat_id,
                text=f"🎮 **Mindi Match {match_id} Starting!**\nMode: `{mode.upper()}` | Trump: `{trump_mode.upper()}`\nDealer: {dealer_mention}\n\n*Dealing cards...*"
            )
            game.group_msg_id = start_msg.id
        except Exception as e:
            logger.error(f"Failed to send start message to group {group_chat_id}: {e}")
            
    # Save game to Cache
    await set_cache(f"mindi:game:{match_id}", game.to_dict())
    
    # Persist Match structure in PostgreSQL
    async with AsyncSessionLocal() as session:
        # Create match entry
        db_match = Match(
            mode=mode,
            status="playing",
            trump_mode=trump_mode,
            group_chat_id=group_chat_id
        )
        session.add(db_match)
        await session.flush()  # Populates db_match.id
        
        # Link players to match
        for idx, p_info in enumerate(players_info):
            user_res = await session.execute(select(User).filter(User.telegram_id == p_info["id"]))
            db_user = user_res.scalars().first()
            
            user_id = db_user.id if db_user else None
            team = 1 if idx in [0, 2] else 2
            
            match_player = MatchPlayer(
                match_id=db_match.id,
                user_id=user_id,
                team=team,
                seat_index=idx,
                is_ai=(p_info["id"] <= 0)
            )
            session.add(match_player)
            
            # Map player active game
            await set_cache(f"mindi:player_game:{p_info['id']}", match_id)
            
        await session.commit()

    # Process next step
    if game.state == GameState.SELECTING_TRUMP:
        selector_name = game.player_names[game.hidden_trump_selector_idx]
        selector_id = game.player_ids[game.hidden_trump_selector_idx]
        
        if group_chat_id:
            try:
                selector_mention = f"[{selector_name}](tg://user?id={selector_id})" if selector_id > 0 else f"**{selector_name}**"
                await bot.send_message(
                    chat_id=group_chat_id,
                    text=(
                        f"🤫 **Hidden Hukam Mode!**\n"
                        f"Dealer's partner {selector_mention} must now select the Hidden Hukam card!\n"
                        f"👉 {selector_mention}: Click the inline button below to choose your card privately."
                    ),
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton(
                            "🤫 Select Hidden Hukam Card",
                            switch_inline_query_current_chat=f"{match_id}:hukum"
                        )]
                    ])
                )
            except Exception as e:
                logger.error(f"Failed to send hidden trump selection prompt: {e}")
        else:
            if selector_id > 0:
                try:
                    await bot.send_message(
                        chat_id=selector_id,
                        text=(
                            f"🤫 **Hidden Hukam Selection - Match {match_id}**\n"
                            f"You are the dealer's partner! Choose a card from your hand to set as the Hidden Hukam:"
                        )
                    )
                except Exception as e:
                    logger.error(f"Failed to send hidden trump DM prompt: {e}")
    else:
        # Playing state (Open Hukam) - start gameplay!
        from mindi.bot.handlers.gameplay import start_game_round
        await start_game_round(game)


@bot.on_message(filters.command(["new", "create"]) & filters.group)
async def on_create_table_command(client, message):
    logger.info(f"Received /new or /create command in group chat {message.chat.id} from user {message.from_user.id}")
    player_id = message.from_user.id
    player_name = message.from_user.first_name
    group_chat_id = message.chat.id
    
    # Check active game
    active_game = await get_cache(f"mindi:player_game:{player_id}")
    if active_game:
        await message.reply_text("⚠️ You are already in an active game!")
        return
        
    lobby_id = f"LOBBY-{random.randint(1000, 9999)}"
    lobby_data = {
        "lobby_id": lobby_id,
        "host_id": player_id,
        "players": [{"id": player_id, "name": player_name}],
        "trump_mode": "open",
        "mode": "casual",
        "group_chat_id": group_chat_id
    }
    
    await set_cache(f"mindi:lobby:{lobby_id}", lobby_data, expire_seconds=3600)
    
    lobby_text = (
        f"➕ **Private Table Created!**\n"
        f"🆔 Table Code: `{lobby_id}`\n\n"
        f"⚙️ **Settings:**\n"
        f"• Mode: `CASUAL`\n"
        f"• Trump: `{lobby_data['trump_mode'].upper()} HUKAM`\n\n"
        f"👥 **Lobby Players (1/4):**\n"
        f"{format_lobby_players(lobby_data['players'])}"
    )
    
    await message.reply_text(text=lobby_text, reply_markup=get_lobby_keyboard(lobby_data))


@bot.on_callback_query(filters.regex(r"^lobby:join:(.+)$"))
async def on_join_lobby(client, callback_query: CallbackQuery):
    lobby_id = callback_query.matches[0].group(1)
    player_id = callback_query.from_user.id
    player_name = callback_query.from_user.first_name
    
    lobby_data = await get_cache(f"mindi:lobby:{lobby_id}")
    if not lobby_data:
        await callback_query.answer("⚠️ This table lobby has expired or is invalid.", show_alert=True)
        return
        
    # Check if already joined
    joined_ids = [p["id"] for p in lobby_data["players"]]
    if player_id in joined_ids:
        await callback_query.answer("You are already in this lobby!")
        return
        
    if len(lobby_data["players"]) >= 4:
        await callback_query.answer("⚠️ Table is full!", show_alert=True)
        return
        
    lobby_data["players"].append({"id": player_id, "name": player_name})
    await set_cache(f"mindi:lobby:{lobby_id}", lobby_data, expire_seconds=3600)
    
    # Redraw keyboard and players
    lobby_text = (
        f"➕ **Private Table Details**\n"
        f"🆔 Table Code: `{lobby_id}`\n\n"
        f"⚙️ **Settings:**\n"
        f"• Mode: `{lobby_data['mode'].upper()}`\n"
        f"• Trump: `{lobby_data['trump_mode'].upper()} HUKAM`\n\n"
        f"👥 **Lobby Players ({len(lobby_data['players'])}/4):**\n"
        f"{format_lobby_players(lobby_data['players'])}"
    )
    
    await callback_query.message.edit_text(text=lobby_text, reply_markup=get_lobby_keyboard(lobby_data))


@bot.on_callback_query(filters.regex(r"^lobby:leave:(.+)$"))
async def on_leave_lobby(client, callback_query: CallbackQuery):
    lobby_id = callback_query.matches[0].group(1)
    player_id = callback_query.from_user.id
    
    lobby_data = await get_cache(f"mindi:lobby:{lobby_id}")
    if not lobby_data:
        await callback_query.answer("Lobby already closed.")
        return
        
    lobby_data["players"] = [p for p in lobby_data["players"] if p["id"] != player_id]
    
    if not lobby_data["players"]:
        # If last player left, delete the lobby
        await delete_cache(f"mindi:lobby:{lobby_id}")
        await callback_query.message.edit_text("Lobby closed because all players left.")
        return
        
    # Reassign host if the host left
    if lobby_data["host_id"] == player_id:
        lobby_data["host_id"] = lobby_data["players"][0]["id"]
        
    await set_cache(f"mindi:lobby:{lobby_id}", lobby_data, expire_seconds=3600)
    
    lobby_text = (
        f"➕ **Private Table Details**\n"
        f"🆔 Table Code: `{lobby_id}`\n\n"
        f"⚙️ **Settings:**\n"
        f"• Mode: `{lobby_data['mode'].upper()}`\n"
        f"• Trump: `{lobby_data['trump_mode'].upper()} HUKAM`\n\n"
        f"👥 **Lobby Players ({len(lobby_data['players'])}/4):**\n"
        f"{format_lobby_players(lobby_data['players'])}"
    )
    
    await callback_query.message.edit_text(text=lobby_text, reply_markup=get_lobby_keyboard(lobby_data))


@bot.on_callback_query(filters.regex(r"^lobby:set_trump:(open|hidden):(.+)$"))
async def on_set_trump(client, callback_query: CallbackQuery):
    trump_mode = callback_query.matches[0].group(1)
    lobby_id = callback_query.matches[0].group(2)
    player_id = callback_query.from_user.id
    
    lobby_data = await get_cache(f"mindi:lobby:{lobby_id}")
    if not lobby_data:
        return
        
    if lobby_data["host_id"] != player_id:
        await callback_query.answer("⚠️ Only the host can toggle game configurations!", show_alert=True)
        return
        
    lobby_data["trump_mode"] = trump_mode
    await set_cache(f"mindi:lobby:{lobby_id}", lobby_data, expire_seconds=3600)
    await callback_query.answer(f"Switched trump to {trump_mode.upper()} HUKAM.")
    
    # Redraw
    lobby_text = (
        f"➕ **Private Table Details**\n"
        f"🆔 Table Code: `{lobby_id}`\n\n"
        f"⚙️ **Settings:**\n"
        f"• Mode: `{lobby_data['mode'].upper()}`\n"
        f"• Trump: `{lobby_data['trump_mode'].upper()} HUKAM`\n\n"
        f"👥 **Lobby Players ({len(lobby_data['players'])}/4):**\n"
        f"{format_lobby_players(lobby_data['players'])}"
    )
    
    await callback_query.message.edit_text(text=lobby_text, reply_markup=get_lobby_keyboard(lobby_data))


@bot.on_callback_query(filters.regex(r"^lobby:start:(.+)$"))
async def on_start_lobby(client, callback_query: CallbackQuery):
    lobby_id = callback_query.matches[0].group(1)
    player_id = callback_query.from_user.id
    
    lobby_data = await get_cache(f"mindi:lobby:{lobby_id}")
    if not lobby_data:
        return
        
    if lobby_data["host_id"] != player_id:
        await callback_query.answer("⚠️ Only the host can start the game!", show_alert=True)
        return
        
    # If table has less than 4 players, fill remaining with AI bots automatically
    while len(lobby_data["players"]) < 4:
        ai_idx = len(lobby_data["players"])
        ai_id = -(ai_idx + 1)
        lobby_data["players"].append({"id": ai_id, "name": f"Bot {ai_idx} (AI)"})
        
    # Start game
    await delete_cache(f"mindi:lobby:{lobby_id}")
    
    group_chat_id = lobby_data.get("group_chat_id")
    if group_chat_id:
        try:
            await callback_query.message.delete()
        except Exception:
            pass
    else:
        await callback_query.message.edit_text("🎮 Table starting! Check your DM.")
    
    await initialize_and_start_game(
        match_id=f"MND-{random.randint(10000, 99999)}",
        players_info=lobby_data["players"],
        mode=lobby_data["mode"],
        trump_mode=lobby_data["trump_mode"],
        group_chat_id=group_chat_id
    )
