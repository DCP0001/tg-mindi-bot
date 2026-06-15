import os
import logging
from pyrogram import Client

logger = logging.getLogger(__name__)

API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_API_HASH")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not API_ID or not API_HASH or not BOT_TOKEN:
    logger.warning("Telegram Bot credentials (TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_BOT_TOKEN) not set completely in env.")

# Configure Pyrogram Client
bot = Client(
    "mindi_bot",
    api_id=int(API_ID) if API_ID else 12345,
    api_hash=API_HASH if API_HASH else "placeholder_hash",
    bot_token=BOT_TOKEN if BOT_TOKEN else "placeholder_token",
    workdir=os.getcwd()
)

def register_all_handlers():
    """Importing handlers registers them with the Pyrogram bot client decorator."""
    import mindi.bot.handlers.menu
    import mindi.bot.handlers.lobby
    import mindi.bot.handlers.gameplay
    logger.info("Successfully registered all bot handlers.")
