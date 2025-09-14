# bot/handlers/start_handler.py
from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from services.context_service import get_voice_mode, toggle_voice_mode

start_router = Router()

@start_router.message(CommandStart())
async def welcome(message: Message):
    await message.reply(
        "🤖 Привет! Я бот на базе Gemini AI.\n"
        "Пришлите текст или фото для анализа.\n"
        "Используйте /help для списка команд"
    )

@start_router.message(Command("vt"))
async def toggle_voice_transcription_mode(message: Message):
    chat_id = message.chat.id
    new_mode = toggle_voice_mode(chat_id)
    mode_text = "включен" if new_mode else "выключен"
    await message.reply(f"🔊 Режим озвучивания ответов {mode_text}")

@start_router.message(Command("help"))
async def help_command(message: Message):
    help_text = """
🤖 Список команд:

/start - Запустить бота
/help - Показать эту справку
/vt - Переключить режим озвучивания ответов
/model - Управление моделями ИИ
/settings - Настройки бота
/clear - Очистить контекст диалога

📝 Поддерживаемые типы сообщений:
• Текст - обычный диалог
• Голосовые сообщения - транскрибация и ответ
• Фото - анализ изображений
• Документы - анализ файлов
"""
    await message.reply(help_text)

@start_router.message(Command("clear"))
async def clear_context(message: Message):
    from services.context_service import clear_chat_history
    chat_id = message.chat.id
    clear_chat_history(chat_id)
    await message.reply("🗑 Контекст диалога очищен")

