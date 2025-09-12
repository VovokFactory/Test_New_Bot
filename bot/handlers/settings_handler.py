# bot/handlers/settings_handler.py
import logging
from telebot import TeleBot
from config import MAX_HISTORY, CONTEXT_TIMEOUT
from utils.helpers import send_command_response
from services.context_service import (
    get_chat_settings, 
    set_max_history, 
    set_context_ttl, 
    clear_chat_history,
    get_voice_mode
)

logger = logging.getLogger(__name__)

def register_settings_handlers(bot: TeleBot):
    """Регистрация обработчиков настроек"""
    
    @bot.message_handler(commands=['clear'])
    def clear_history(message):
        """Очистка истории диалога"""
        chat_id = message.chat.id
        clear_chat_history(chat_id)
        bot.reply_to(message, "🧹 История диалога очищена!", parse_mode=None)
    
    @bot.message_handler(commands=['settings'])
    def show_settings(message):
        """Показ текущих настроек"""
        chat_id = message.chat.id
        settings = get_chat_settings(chat_id)
        max_history = settings.get('max_history', MAX_HISTORY)
        context_ttl = settings.get('context_ttl', CONTEXT_TIMEOUT)
        voice_mode = get_voice_mode(chat_id)
        voice_status = "включен" if voice_mode else "отключен"
        
        response = (
            "⚙️ <b>Текущие настройки:</b>\n"
            f"• Глубина истории: <b>{max_history}</b> сообщений\n"
            f"• Время жизни контекста: <b>{context_ttl}</b> секунд\n"
            f"• Голосовое дублирование: <b>{voice_status}</b>\n"
            "Используйте /help для информации о командах"
        )
        bot.send_message(chat_id, response, parse_mode='HTML', reply_to_message_id=message.id)
    
    @bot.message_handler(commands=['help'])
    def show_help(message):
        """Показ справки"""
        from config import MAX_HISTORY, CONTEXT_TIMEOUT
        help_text = f"""
📖 <b>Доступные команды:</b>
/start - начать работу с ботом
/help - показать это сообщение
/clear - очистить историю диалога
/settings - показать текущие настройки
⚙️ <b>Настройки контекста:</b>
/set_history [число] - глубина истории (по умолчанию {MAX_HISTORY})
/set_context_ttl [секунды] - время жизни контекста (по умолчанию {CONTEXT_TIMEOUT})
🔄 <b>Смена модели:</b>
/chm - выбрать другую модель Gemini
"""
        send_command_response(bot, message.chat.id, help_text, reply_to=message.id)
    
    @bot.message_handler(commands=['set_history'])
    def handle_set_max_history(message):
        """Установка глубины истории"""
        try:
            # Разбиваем сообщение на части
            parts = message.text.split()
            if len(parts) != 2:
                raise ValueError("Неверное количество аргументов")
            
            value = int(parts[1])
            
            # Проверяем допустимый диапазон (как в оригинале: 1-1000)
            if not (1 <= value <= 1000):
                raise ValueError("Значение должно быть от 1 до 1000")
            
            chat_id = message.chat.id
            set_max_history(chat_id, value)
            bot.reply_to(message, f"✅ Глубина истории установлена: {value} сообщений", parse_mode=None)
        except ValueError as e:
            if "invalid literal" in str(e):
                error_msg = (
                    "❌ Неверный формат команды\n"
                    "Использование: <code>/set_history [число]</code>\n"
                    "Пример: <code>/set_history 10</code>"
                )
            else:
                error_msg = f"❌ Ошибка: {str(e)}"
            bot.send_message(message.chat.id, error_msg, parse_mode='HTML', reply_to_message_id=message.id)
        except Exception as e:
            error_msg = f"❌ Непредвиденная ошибка: {str(e)}"
            bot.send_message(message.chat.id, error_msg, parse_mode='HTML', reply_to_message_id=message.id)
    
    @bot.message_handler(commands=['set_context_ttl'])
    def handle_set_context_ttl(message):
        """Установка времени жизни контекста"""
        try:
            # Разбиваем сообщение на части
            parts = message.text.split()
            if len(parts) != 2:
                raise ValueError("Неверное количество аргументов")
            
            value = int(parts[1])
            
            # Проверяем допустимый диапазон (как в оригинале: 10 сек - 365 дней)
            if not (10 <= value <= 31536000): # 31536000 = 365 * 24 * 60 * 60
                raise ValueError("Значение должно быть от 10 секунд до 31536000 секунд (365 дней)")
            
            chat_id = message.chat.id
            set_context_ttl(chat_id, value)
            # Преобразуем секунды в более читаемый формат для ответа
            if value >= 86400: # >= 1 день
                days = value // 86400
                bot.reply_to(message, f"✅ Время жизни контекста установлено: {value} секунд ({days} дней)", parse_mode=None)
            elif value >= 3600: # >= 1 час
                hours = value // 3600
                bot.reply_to(message, f"✅ Время жизни контекста установлено: {value} секунд ({hours} часов)", parse_mode=None)
            elif value >= 60: # >= 1 минута
                minutes = value // 60
                bot.reply_to(message, f"✅ Время жизни контекста установлено: {value} секунд ({minutes} минут)", parse_mode=None)
            else:
                bot.reply_to(message, f"✅ Время жизни контекста установлено: {value} секунд", parse_mode=None)
        except ValueError as e:
            if "invalid literal" in str(e):
                error_msg = (
                    "❌ Неверный формат команды\n"
                    "Использование: <code>/set_context_ttl [секунды]</code>\n"
                    "Пример: <code>/set_context_ttl 300</code> (5 минут)\n"
                    "Максимум: <code>/set_context_ttl 31536000</code> (365 дней)"
                )
            else:
                error_msg = f"❌ Ошибка: {str(e)}"
            bot.send_message(message.chat.id, error_msg, parse_mode='HTML', reply_to_message_id=message.id)
        except Exception as e:
            error_msg = f"❌ Непредвиденная ошибка: {str(e)}"
            bot.send_message(message.chat.id, error_msg, parse_mode='HTML', reply_to_message_id=message.id)