# bot/handlers/text_handler.py
import logging
from telebot import TeleBot
from services.model_service import generate_model_response
from utils.helpers import send_response
# Импортируем функции для работы с аудио
from services.audio_service import send_audio_with_progress # <-- ДОБАВИТЬ
# Импортируем функцию для проверки режима дублирования
from services.context_service import get_voice_mode # <-- ДОБАВИТЬ


logger = logging.getLogger(__name__)

def register_text_handler(bot: TeleBot):
    """Регистрация обработчика текстовых сообщений"""
    
    @bot.message_handler(content_types=['text'])
    def handle_text(message):
        # Игнорируем команды
        if message.text.startswith('/'):
            return
            
        chat_id = message.chat.id
        
        try:
            # Вывести "Генерирую ответ..."
            bot.send_chat_action(chat_id, 'typing')
            progress_msg = bot.reply_to(
                message, 
                "🧠 _Генерирую ответ..._", 
                reply_to_message_id=message.id, 
                parse_mode='Markdown'
            )
            
            # Генерация ответа
            answer = generate_model_response(chat_id, message.text)
            
            # Отправка ответа
            send_response(bot, chat_id, answer, reply_to=message.id)
            
            # TODO: Добавить проверку режима дублирования
            if get_voice_mode(chat_id):
                send_audio_with_progress(chat_id, message, answer, bot)
            
            # Удалить промежуточное сообщение
            bot.delete_message(chat_id, progress_msg.id)
            
        except Exception as e:
            logger.error(f"Ошибка обработки текстового сообщения: {e}")
