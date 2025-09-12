# main.py
import logging
from config import LOG_TO_CONSOLE
from dotenv import load_dotenv
import os

# Загрузка переменных окружения в самом начале
load_dotenv(override=True)

# Настройка логирования после загрузки .env
log_handlers = [logging.FileHandler("bot_debug.log", encoding='utf-8')]

if LOG_TO_CONSOLE:
    from logging import StreamHandler
    log_handlers.append(StreamHandler())

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=log_handlers
)

logger = logging.getLogger(__name__)

# Импорт после настройки логирования и загрузки .env
from telebot import TeleBot
from bot.handlers import register_handlers
# Импорт для работы с очередью
from services.voice_queue import get_voice_queue


# Получение токена после загрузки .env
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN не найден в .env файле!")

# Создание экземпляра бота
bot = TeleBot(TELEGRAM_TOKEN)

# Инициализация очереди обработки голоса (но еще не запускаем)
voice_queue = get_voice_queue(bot)

# Регистрация обработчиков
register_handlers(bot)

# Запуск очереди обработки голоса ПОСЛЕ регистрации всех хендлеров
voice_queue.start()

# Временный тестовый код в bot.py или handlers.py
test_message = """Процесс размышлений (скрыт): <tg-spoiler>Тут содержимое тега think, например, внутренний монолог модели. Модель пыталась понять запрос пользователя и сформулировать план ответа.</tg-spoiler>

Основной ответ модели после think-тегов. Этот текст должен отображаться всегда, а текст в тегах spoiler будет скрыт до нажатия."""
#bot.send_message(chat_id=1420597113, text=test_message, parse_mode='HTML')


if __name__ == '__main__':
    from config import VOICE_WORKERS_COUNT
    from mod_llm import DEFAULT_MODEL, MODELS
    print(f"Бот запущен с моделью по умолчанию: {DEFAULT_MODEL}")
    print("Доступные модели:")
    for model in MODELS:
        print(f"- {model['name']} ({model['id']})")
    print(f"\nОчередь обработки голоса запущена с {VOICE_WORKERS_COUNT} воркерами.")
    print("Ожидание сообщений...")
    
    try:
        bot.infinity_polling()
    except KeyboardInterrupt:
        print("\nПолучен сигнал остановки (Ctrl+C). Завершаем работу...")
    finally:
        # Останавливаем очередь при завершении работы бота
        voice_queue.stop()
        print("Бот остановлен.")