# bot/handlers/start_handler.py
from services.context_service import get_voice_mode, toggle_voice_mode

def register_start_handler(bot):
    @bot.message_handler(commands=['start'])
    def welcome(message):
        bot.reply_to(
            message,
            "🤖 Привет! Я бот на базе Gemini AI.\n"
            "Пришлите текст или фото для анализа.\n"
            "Используйте /help для списка команд",
            parse_mode=None,
        )
    
    @bot.message_handler(commands=['vt'])
    def toggle_voice_mode_handler(message):
        """Переключение режима дублирования"""
        chat_id = message.chat.id
        new_state = toggle_voice_mode(chat_id)
        state = "включен" if new_state else "отключен"
        bot.reply_to(
            message,
            f"🔊 Режим голосового дублирования {state}",
            parse_mode=None
        )