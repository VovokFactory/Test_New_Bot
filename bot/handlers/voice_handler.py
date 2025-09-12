# bot/handlers/voice_handler.py
"""Обработчик голосовых сообщений."""
import logging
import os
from telebot import TeleBot
# Импортируем очередь обработки голоса
from services.voice_queue import get_voice_queue

logger = logging.getLogger(__name__)

def register_voice_handler(bot: TeleBot):
    """Регистрация обработчика голосовых сообщений."""

    @bot.message_handler(content_types=['voice'])
    def handle_voice(message):
        """
        Обрабатывает входящие голосовые сообщения.
        
        Вместо немедленной обработки, сообщение добавляется в очередь,
        что позволяет обрабатывать несколько голосовых сообщений параллельно
        и не блокировать основной поток бота.
        """
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        logger.info(f"Получено голосовое сообщение от пользователя {user_id} в чате {chat_id}")

        try:
            # 1. Получаем API ключ Google из переменных окружения
            google_api_key = os.getenv("GOOGLE_API_KEY")
            if not google_api_key:
                error_msg = "❌ GOOGLE_API_KEY не найден. Проверьте .env файл."
                logger.error(f"{error_msg} (Чат {chat_id}, Пользователь {user_id})")
                bot.reply_to(message, error_msg)
                return

            # 2. Получаем экземпляр очереди обработки голоса
            # Очередь должна быть уже инициализирована в main.py
            try:
                voice_queue = get_voice_queue()
            except ValueError as e:
                # Это произойдет, если очередь не была инициализирована с ботом
                error_msg = "❌ Очередь обработки голоса не инициализирована."
                logger.critical(f"{error_msg} (Чат {chat_id}, Пользователь {user_id})")
                bot.reply_to(message, error_msg)
                return

            # 3. Сразу показываем пользователю, что сообщение принято
            # Это улучшает UX, так как пользователь сразу видит отклик
            bot.send_chat_action(chat_id, 'record_voice') # Анимация "распознаю голос"
            progress_message = bot.reply_to(
                message,
                "_Распознаю речь..._", # Сообщение, которое будет обновлено воркером
                reply_to_message_id=message.id,
                parse_mode='Markdown'
            )
            progress_message_id = progress_message.id



            
            logger.debug(f"Создано сообщение прогресса {progress_message_id} для чата {chat_id}")

            # 4. Добавляем задачу в очередь на обработку
            # Передаем ID сообщения о прогрессе, чтобы воркер мог его обновлять
            voice_queue.add(chat_id, message, google_api_key, progress_message_id)
            
            logger.info(
                f"Голосовое сообщение от пользователя {user_id} в чате {chat_id} "
                f"поставлено в очередь. Progress message ID: {progress_message_id}"
            )
            
            # 5. Не отправляем отдельное сообщение "добавлено в очередь"
            #    Пользователь уже видит "Распознаю речь...", и воркер обновит это сообщение.
            
        except Exception as e:
            logger.error(
                f"Критическая ошибка при постановке голосового сообщения в очередь "
                f"для чата {chat_id}, пользователя {user_id}: {e}", 
                exc_info=True
            )
            
            # Пытаемся обновить сообщение о прогрессе или отправить новое сообщение об ошибке
            try:
                if 'progress_message_id' in locals():
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=progress_message_id,
                        text=f"❌ Критическая ошибка постановки в очередь: {str(e)}"
                    )
                else:
                    bot.reply_to(message, f"❌ Критическая ошибка постановки в очередь: {str(e)}")
            except Exception as edit_error:
                logger.error(
                    f"Не удалось отправить сообщение об ошибке в чат {chat_id}: {edit_error}"
                )
                # Последний фолбэк - просто залогировать, пользователь увидит зависшее сообщение
