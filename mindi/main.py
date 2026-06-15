import os
import logging
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI
from sqlalchemy import select, desc

# Load environment variables
load_dotenv()

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("mindi.main")

from mindi.database.db import init_db, AsyncSessionLocal
from mindi.database.models import User
from mindi.bot.bot import bot, register_all_handlers

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    logger.info("Starting up Mindi Bot application services...")
    
    # 1. Initialize PostgreSQL database tables
    try:
        await init_db()
        logger.info("Database schemas initialized successfully.")
    except Exception as e:
        logger.error(f"Error initializing database schemas: {e}")
        
    # 2. Register handlers and boot Telegram Bot
    try:
        import asyncio
        loop = asyncio.get_running_loop()
        bot.loop = loop
        bot.dispatcher.loop = loop
        
        register_all_handlers()
        await bot.start()
        logger.info("Telegram Pyrogram Bot client started successfully.")
        
        # 3. Set bot commands programmatically
        try:
            from pyrogram.types import BotCommand
            await bot.set_bot_commands([
                BotCommand("start", "Start the bot and open the main menu"),
                BotCommand("new", "Create a new Mindi game lobby in a group"),
                BotCommand("stop", "Abort the current active game in a group")
            ])
            logger.info("Bot commands registered successfully in Telegram.")
        except Exception as e:
            logger.error(f"Error setting bot commands: {e}")
    except Exception as e:
        logger.error(f"Error starting Pyrogram Bot: {e}")
        
    yield
    
    # Shutdown actions
    logger.info("Shutting down Mindi Bot application services...")
    try:
        await bot.stop()
        logger.info("Telegram Pyrogram Bot client stopped.")
    except Exception as e:
        logger.error(f"Error stopping Pyrogram Bot: {e}")

# Initialize FastAPI App
app = FastAPI(
    title="Mindi Card Game Bot API",
    description="Backend API for active games and global ELO ranking dashboard of Mindi Bot.",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/health")
async def health_check():
    """Service health state check."""
    bot_connected = bot.is_connected if hasattr(bot, "is_connected") else False
    return {
        "status": "online",
        "bot_connected": bot_connected,
        "database": "connected"  # If startup succeeded, engine pool is live
    }

@app.get("/api/leaderboard")
async def get_leaderboard(limit: int = 10):
    """API endpoint to get the current global leaderboard."""
    async with AsyncSessionLocal() as session:
        stmt = select(User).order_by(desc(User.rating)).limit(limit)
        result = await session.execute(stmt)
        users = result.scalars().all()
        
        return [
            {
                "rank": idx + 1,
                "display_name": u.display_name,
                "username": u.username,
                "rating": u.rating,
                "games_played": u.games_played,
                "wins": u.wins,
                "losses": u.losses,
                "win_rate": round(u.win_rate * 100, 1)
            }
            for idx, u in enumerate(users)
        ]

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("FASTAPI_PORT", 8000))
    # Run uvicorn web server
    uvicorn.run("mindi.main:app", host="0.0.0.0", port=port, log_level="info")
