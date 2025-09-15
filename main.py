# main.py (aiogram 3.x)
import asyncio
import logging
import os

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import LOG_TO_CONSOLE, VOICE_WORKERS_COUNT
from bot.handlers import register_handlers  # <-- корректный импорт
from services.voice_queue import get_voice_queue

load_dotenv(override=True)

handlers = [logging.FileHandler("bot_debug.log", encoding="utf-8")]
if LOG_TO_CONSOLE:
    handlers.append(logging.StreamHandler())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=handlers,
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN не задан в .env")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

voice_queue = None

async def on_startup():
    global voice_queue
    loop = asyncio.get_running_loop()
    voice_queue = get_voice_queue(bot, loop)

    google_key = os.getenv("GOOGLE_API_KEY")
    if not google_key:
        logger.warning("GOOGLE_API_KEY не найден. Транскрибация может не работать.")
    else:
        logger.info("GOOGLE_API_KEY загружен.")

    register_handlers(dp)
    logger.info(f"Очередь обработки голоса запускается с {VOICE_WORKERS_COUNT} воркерами.")
    voice_queue.start()

async def on_shutdown():
    if voice_queue:
        voice_queue.stop()
    await bot.session.close()
    logger.info("Бот остановлен.")

async def main():
    await on_startup()
    try:
        await dp.start_polling(bot)
    finally:
        await on_shutdown()

if __name__ == "__main__":
    asyncio.run(main())
