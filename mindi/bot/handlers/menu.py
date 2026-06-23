import os
import asyncio
import logging
from pyrogram import filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ChatType, ChatMemberStatus
from sqlalchemy import select, desc, delete
from mindi.bot.bot import bot
from mindi.database.db import AsyncSessionLocal
from mindi.database.models import User, TrackedChat

logger = logging.getLogger(__name__)

# Main menu keyboard markup
def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Rules 📖", callback_data="menu:rules")
        ],
        [
            InlineKeyboardButton("👤 My Profile", callback_data="menu:profile"),
            InlineKeyboardButton("🏆 Leaderboard", callback_data="menu:leaderboard")
        ]
    ])

async def get_or_create_user(session, tg_user) -> User:
    """Helper to upsert a user into the DB when they interact with the bot."""
    stmt = select(User).filter(User.telegram_id == tg_user.id)
    result = await session.execute(stmt)
    db_user = result.scalars().first()
    
    display_name = tg_user.first_name
    if tg_user.last_name:
        display_name += f" {tg_user.last_name}"
        
    if not db_user:
        db_user = User(
            telegram_id=tg_user.id,
            username=tg_user.username,
            display_name=display_name
        )
        session.add(db_user)
        await session.commit()
        logger.info(f"Registered new user: {display_name} ({tg_user.id})")
    else:
        # Update display name / username if changed
        db_user.username = tg_user.username
        db_user.display_name = display_name
        await session.commit()
    return db_user

async def track_chat_id(session, chat):
    """Upsert chat details into tracked_chats table."""
    if chat.type in [ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL]:
        stmt = select(TrackedChat).filter(TrackedChat.chat_id == chat.id)
        result = await session.execute(stmt)
        db_chat = result.scalars().first()
        if not db_chat:
            db_chat = TrackedChat(
                chat_id=chat.id,
                chat_type=str(chat.type),
                title=chat.title
            )
            session.add(db_chat)
            await session.commit()
            logger.info(f"Started tracking new chat: {chat.title} ({chat.id})")

@bot.on_message(group=-1)
async def log_all_messages(client, message: Message):
    logger.info(f"GLOBAL LOGGER: Received message: chat_id={message.chat.id}, chat_type={message.chat.type}, text={message.text}")
    if message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL]:
        try:
            async with AsyncSessionLocal() as session:
                await track_chat_id(session, message.chat)
        except Exception as e:
            logger.error(f"Error tracking chat {message.chat.id}: {e}")
    message.continue_propagation()

@bot.on_callback_query(group=-1)
async def log_all_callbacks(client, callback_query: CallbackQuery):
    logger.info(f"GLOBAL LOGGER: Received callback: data={callback_query.data}, from_user={callback_query.from_user.id}")
    callback_query.continue_propagation()

@bot.on_message(filters.command("start") & filters.private)
async def on_start_command(client, message: Message):
    async with AsyncSessionLocal() as session:
        db_user = await get_or_create_user(session, message.from_user)
        welcome_text = (
            f"👋 **Welcome to Mindi Bot, {db_user.display_name}!**\n\n"
            "Mindi (also known as Dehla Pakad) is an exciting Indian trick-taking card game. "
            "Team up with a partner, capture the 10s (Mindis), and coat your opponents!\n\n"
            "🎮 Choose an option below to start playing:"
        )
        await message.reply_text(
            text=welcome_text,
            reply_markup=get_main_menu_keyboard()
        )

@bot.on_callback_query(filters.regex(r"^menu:main$"))
async def on_menu_main(client, callback_query: CallbackQuery):
    await callback_query.message.edit_text(
        text="🎮 **Mindi Main Menu**\nChoose an option below to start playing:",
        reply_markup=get_main_menu_keyboard()
    )

@bot.on_callback_query(filters.regex(r"^menu:profile$"))
async def on_menu_profile(client, callback_query: CallbackQuery):
    tg_user = callback_query.from_user
    async with AsyncSessionLocal() as session:
        db_user = await get_or_create_user(session, tg_user)
        
        profile_text = (
            f"👤 **Player Profile: {db_user.display_name}**\n\n"
            f"🏆 **ELO Rating:** `{db_user.rating}`\n"
            f"📈 **Highest Rating:** `{db_user.highest_rating}`\n"
            f"🎮 **Games Played:** `{db_user.games_played}`\n"
            f"✅ **Wins:** `{db_user.wins}`\n"
            f"❌ **Losses:** `{db_user.losses}`\n"
            f"📊 **Win Rate:** `{db_user.win_rate * 100:.1f}%`\n"
            f"🌟 **Total Mindis Captured:** `{db_user.total_points}`"
        )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="menu:main")]
        ])
        await callback_query.message.edit_text(text=profile_text, reply_markup=keyboard)

@bot.on_callback_query(filters.regex(r"^menu:rules$"))
async def on_menu_rules(client, callback_query: CallbackQuery):
    rules_text = (
        "📖 **Mindi (Dehla Pakad) Rules**\n\n"
        "1. **Players & Teams**: 4 players, 2 teams (partners sit opposite each other: 0 & 2 vs 1 & 3).\n\n"
        "2. **The Objective**: Capture maximum 10-value cards (Mindis) in a round. There are 4 Mindis in the deck.\n\n"
        "3. **Dehla Pakad Rule**: Trick cards accumulate in the center. A player only collects the accumulated cards when they win **two consecutive tricks**. The winner of the final (13th) trick collects any remaining cards in the center.\n\n"
        "4. **Trump (Hukam)**:\n"
        "   - **Open Hukam**: The trump suit is decided when a player cannot follow suit; the suit of the card they play becomes the trump suit.\n"
        "   - **Hidden Hukam**: The dealer's partner selects a hidden trump suit at the start. It is revealed only when a player cannot follow suit.\n\n"
        "5. **Coat (Whitewash)**: If a team wins all 4 Mindis, it is a **Coat**. Coating the dealer's team is a major victory!"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="menu:main")]
    ])
    await callback_query.message.edit_text(text=rules_text, reply_markup=keyboard)

@bot.on_callback_query(filters.regex(r"^menu:leaderboard$"))
async def on_menu_leaderboard(client, callback_query: CallbackQuery):
    async with AsyncSessionLocal() as session:
        stmt = select(User).order_by(desc(User.rating)).limit(10)
        result = await session.execute(stmt)
        top_users = result.scalars().all()
        
        leaderboard_text = "🏆 **Global Leaderboard - Top 10**\n\n"
        
        if not top_users:
            leaderboard_text += "No ranked players yet. Be the first!"
        else:
            for rank, user in enumerate(top_users, 1):
                username_str = f"@{user.username}" if user.username else "User"
                leaderboard_text += f"{rank}. **{user.display_name}** ({username_str}) - ELO: `{user.rating}` (W: {user.wins})\n"
                
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="menu:main")]
        ])
        await callback_query.message.edit_text(text=leaderboard_text, reply_markup=keyboard)


@bot.on_message(filters.command("start") & filters.group)
async def on_start_group_command(client, message: Message):
    welcome_text = (
        "👋 **Hello! I am Mindi Bot.**\n\n"
        "To start a new card game lobby in this group, use the `/new` or `/create` command!\n\n"
        "If you want to view your profile, rules, or the global leaderboard, please message me in a private chat."
    )
    # Safe fallback if client.me is not populated
    username = client.me.username if (hasattr(client, "me") and client.me) else "lulu_mindi_bot"
    await message.reply_text(
        text=welcome_text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 Message Me Privately", url=f"https://t.me/{username}")]
        ])
    )


@bot.on_message(filters.command("help"))
async def on_help_command(client, message: Message):
    help_text = (
        "📖 **Mindi Bot Commands Guide**\n\n"
        "• `/start` - Open the main menu (Private Chat only)\n"
        "• `/new` or `/create` - Start a new casual card game lobby (Group Chats only)\n"
        "• `/stop` - Abort the current active game in this group (Group Chats only)\n"
        "• `/help` - Show this commands guide\n\n"
        "**How to Play Mindi:**\n"
        "1. Capture the 10s (Mindis) in card tricks.\n"
        "2. Team with highest captured Mindis wins the round.\n"
        "3. Capturing all 4 Mindis results in a **Coat** (Whitewash)!"
    )
    if message.chat.type == ChatType.PRIVATE:
        await message.reply_text(
            text=help_text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Menu", callback_data="menu:main")]
            ])
        )
    else:
        await message.reply_text(text=help_text)


async def is_admin(client, chat_id, user_id) -> bool:
    """Check if the user is an admin or owner of the chat/bot."""
    owner_id = os.getenv("BOT_OWNER_ID", "1315149993")
    if str(user_id) == str(owner_id):
        return True
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]
    except Exception:
        return False


@bot.on_message(filters.command("active"))
async def on_active_broadcast_command(client, message: Message):
    # 1. Permission check
    allowed = False
    if message.chat.type == ChatType.CHANNEL:
        # In channels, only admins can post
        allowed = True
    elif message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        # Check if sender is group admin or bot owner
        allowed = await is_admin(client, message.chat.id, message.from_user.id)
    elif message.chat.type == ChatType.PRIVATE:
        # Check if sender is bot owner
        owner_id = os.getenv("BOT_OWNER_ID", "1315149993")
        allowed = (str(message.from_user.id) == str(owner_id))
        
    if not allowed:
        await message.reply_text("⚠️ You do not have permission to run the broadcast command.")
        return
        
    # Get custom message if any, default to "hey there i am active now..."
    text = "hey there i am active now..."
    parts = message.text.split(maxsplit=1)
    if len(parts) > 1:
        text = parts[1]
        
    # 2. Query all tracked chats
    async with AsyncSessionLocal() as session:
        stmt = select(TrackedChat)
        res = await session.execute(stmt)
        chats = res.scalars().all()
        
    if not chats:
        await message.reply_text("No registered groups/channels to broadcast to.")
        return
        
    status_msg = await message.reply_text(f"📢 Starting broadcast to {len(chats)} chats...")
    
    success_count = 0
    fail_count = 0
    for chat in chats:
        try:
            await client.send_message(chat_id=chat.chat_id, text=text)
            success_count += 1
            await asyncio.sleep(0.1)  # Small delay to avoid flood limits
        except Exception as e:
            logger.warning(f"Failed to send broadcast to chat {chat.chat_id} ({chat.title}): {e}")
            fail_count += 1
            # Optionally remove from database if bot was kicked
            if any(err in str(e).lower() for err in ["kicked", "peer_id_invalid", "chat_write_forbidden"]):
                try:
                    async with AsyncSessionLocal() as session:
                        await session.execute(
                            delete(TrackedChat).where(TrackedChat.chat_id == chat.chat_id)
                        )
                        await session.commit()
                except Exception as db_err:
                    logger.error(f"Failed to remove invalid chat {chat.chat_id}: {db_err}")
                    
    await status_msg.edit_text(f"✅ Broadcast complete!\n🟢 Success: {success_count}\n🔴 Failed: {fail_count}")
