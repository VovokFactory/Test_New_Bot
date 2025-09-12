# bot/handlers/photo_handler.py
import logging
from telebot import TeleBot
from services.model_service import generate_model_response
from utils.helpers import send_response
# Импортируем функции для работы с аудио
from services.audio_service import send_audio_with_progress # <-- ДОБАВИТЬ
# Импортируем функцию для проверки режима дублирования
from services.context_service import get_voice_mode # <-- ДОБАВИТЬ

logger = logging.getLogger(__name__)

def register_photo_handler(bot: TeleBot):
    """Регистрация обработчика фото сообщений"""
    
    @bot.message_handler(content_types=['photo'])
    def handle_photo(message):
        chat_id = message.chat.id
        
        try:
            # Отправляем временное сообщение о том, что бот "думает"
            progress_message = bot.reply_to(
                message, 
                " _Анализирую изображение..._", 
                parse_mode='Markdown'
            )


            
            # Получаем фото
            file_info = bot.get_file(message.photo[-1].file_id)
            img_bytes = bot.download_file(file_info.file_path)
            
            repl = bot.send_message(chat_id, "🔎")

            # Получаем подпись или используем стандартный промпт
            prompt = message.caption or "Опиши это изображение"
            
            # Генерация ответа
            answer = generate_model_response(chat_id, prompt, img_bytes)

            bot.edit_message_text(
                chat_id=chat_id,
                message_id=repl.message_id,
                text="🔎Изображение изучено. 📝 Ответ готов!"
        )

            
            # Удаляем временное сообщение перед отправкой ответа
            bot.delete_message(chat_id=chat_id, message_id=progress_message.id)
            
            # Отправка ответа
            send_response(bot, chat_id, answer, reply_to=message.id)
            
            # TODO: Добавить проверку режима дублирования
            if get_voice_mode(chat_id):
                send_audio_with_progress(chat_id, message, answer, bot) # TODO: Добавить проверку режима дублирования

        except Exception as e:
            logger.error(f"Ошибка обработки фото: {e}")
            bot.reply_to(message, f"❌ Ошибка обработки фото: {str(e)}")