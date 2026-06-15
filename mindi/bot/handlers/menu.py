import logging
from pyrogram import filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, desc
from mindi.bot.bot import bot
from mindi.database.db import AsyncSessionLocal
from mindi.database.models import User

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

@bot.on_message(group=-1)
async def log_all_messages(client, message: Message):
    logger.info(f"GLOBAL LOGGER: Received message: chat_id={message.chat.id}, chat_type={message.chat.type}, text={message.text}")
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
