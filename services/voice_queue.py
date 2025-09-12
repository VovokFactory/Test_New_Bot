# services/voice_queue.py
import queue
import threading
import time
import logging
import os
from typing import List
from telebot import TeleBot
from config import VOICE_WORKERS_COUNT
# Импортируем функцию из audio_utils
from audio_utils import process_voice_message
# Импортируем НОВУЮ нейтральную функцию из model_service вместо старой из gemini_service
from services.model_service import generate_model_response # <-- ИЗМЕНЕНО
# Импортируем функции из других сервисов
from utils.helpers import send_response
from services.audio_service import send_audio_response, send_audio_with_progress
# Импортируем функцию для получения состояния voice_mode
from services.context_service import get_voice_mode

logger = logging.getLogger(__name__)

class VoiceProcessingQueue:
    """Очередь для параллельной обработки голосовых сообщений с несколькими воркерами."""

    def __init__(self, bot: TeleBot):
        """
        Инициализирует очередь и запускает потоки обработчиков (воркеров).

        Args:
            bot (TeleBot): Экземпляр бота для отправки сообщений.
        """
        self.bot = bot
        self._queue = queue.Queue()
        self._worker_threads: List[threading.Thread] = []
        self._stop_event = threading.Event()
        self.is_running = False
        # Получаем количество воркеров из конфига
        self.num_workers = max(1, VOICE_WORKERS_COUNT) # Минимум 1 воркер

    def start(self):
        """Запускает потоки обработчиков (воркеров) очереди."""
        if not self.is_running:
            self._stop_event.clear()
            self._worker_threads = []
            for i in range(self.num_workers):
                worker_thread = threading.Thread(
                    target=self._worker,
                    name=f"VoiceWorker-{i+1}",
                    daemon=True
                )
                worker_thread.start()
                self._worker_threads.append(worker_thread)
                logger.info(f"Запущен воркер очереди обработки голоса: VoiceWorker-{i+1}")

            self.is_running = True
            logger.info(f"Очередь обработки голоса запущена с {self.num_workers} воркерами.")

    def stop(self):
        """Останавливает потоки обработчиков (воркеров) очереди."""
        if self.is_running:
            self._stop_event.set()
            # Положим "ядовитые таблетки" в очередь для каждого воркера, чтобы разбудить их
            for _ in range(self.num_workers):
                self._queue.put(None)

            # Ждем завершения всех воркеров
            for worker_thread in self._worker_threads:
                if worker_thread.is_alive():
                    worker_thread.join(timeout=5) # Ждем максимум 5 секунд на каждый

            self._worker_threads = []
            self.is_running = False
            logger.info("Все воркеры очереди обработки голоса остановлены.")

    def add(self, chat_id: int, message, api_key: str, progress_message_id: int = None):
        """
        Добавляет голосовое сообщение в очередь на обработку.

        Args:
            chat_id (int): ID чата.
            message: Объект сообщения Telegram.
            api_key (str): API ключ Google.
            progress_message_id (int, optional): ID сообщения для отображения прогресса.
        """
        item = {
            'chat_id': chat_id,
            'message': message,
            'api_key': api_key,
            'timestamp': time.time(),
            'progress_message_id': progress_message_id # Добавляем ID сообщения прогресса
        }
        self._queue.put(item)
        logger.info(f"Голосовое сообщение из чата {chat_id} добавлено в очередь. Размер очереди: {self._queue.qsize()}")

    def _worker(self):
        """Основной цикл обработчика очереди (выполняется в отдельном потоке/воркере)."""
        worker_name = threading.current_thread().name
        logger.info(f"{worker_name} начал работу.")
        while not self._stop_event.is_set():
            try:
                # Ждем элемент из очереди до тех пор, пока не будет сигнал остановки
                # Используем timeout для периодической проверки stop_event
                item = self._queue.get(timeout=1)

                # "Ядовитая таблетка" для остановки
                if item is None:
                    logger.info(f"{worker_name} получил 'ядовитую таблетку', завершает работу.")
                    break

                chat_id = item['chat_id']
                message = item['message']
                api_key = item['api_key']
                progress_message_id = item.get('progress_message_id')

                logger.info(f"{worker_name} начинает обработку голосового сообщения из чата {chat_id}...")
                self._process_voice_item(chat_id, message, api_key, progress_message_id)
                self._queue.task_done()
                logger.info(f"{worker_name} завершил обработку голосового сообщения из чата {chat_id}.")

            except queue.Empty:
                # Timeout истек, проверяем stop_event и продолжаем цикл
                continue
            except Exception as e:
                logger.error(f"{worker_name}: Неожиданная ошибка: {e}", exc_info=True)
                # Не останавливаем worker из-за одной ошибки, продолжаем цикл
        logger.info(f"{worker_name} завершил работу.")

    def _process_voice_item(self, chat_id: int, message, api_key: str, progress_message_id: int = None):
        """
        Обрабатывает одно голосовое сообщение.

        Args:
            chat_id (int): ID чата.
            message: Объект сообщения Telegram.
            api_key (str): API ключ Google.
            progress_message_id (int, optional): ID сообщения для отображения прогресса.
        """
        # progress_message_id может быть None, если вызван не из бота напрямую
        try:
            # 1. Если progress_message_id не задан, создаем новое сообщение
            #    (на случай, если функция вызвана нестандартным способом)
            if progress_message_id is None:
                 progress_msg = self.bot.reply_to(
                    message,
                    "_Распознаю речь из очереди..._",
                    parse_mode='Markdown'
                )
                 progress_message_id = progress_msg.id
                 logger.info(f"Создано новое сообщение прогресса {progress_message_id} для чата {chat_id}")

            repl = self.bot.send_message(chat_id, "🎤")

            # 2. Обработка голоса через нашу функцию
            #    Сообщение "Распознаю речь..." уже отображается
            text = process_voice_message(self.bot, message, api_key) # Передаем bot и api_key

            if text and not text.startswith("❌"):
                # 3. Обновляем сообщение: "Распознано: ... Формулирую ответ..."
                try:
                    self.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=progress_message_id,
                        text=f"🎤*Распознано:* {text}\n_Формулирую ответ..._",
                        parse_mode='Markdown'
                    )
                    self.bot.delete_message(chat_id, repl.id)  # Удаляем сообщение "🎤"
                    repl = self.bot.send_message(chat_id, "📝")

                    logger.info(f"Обновлено сообщение прогресса {progress_message_id} для чата {chat_id}: Распознано")
                except Exception as e:
                    logger.warning(f"Не удалось обновить сообщение о прогрессе 'Распознано' для чата {chat_id}: {e}")

                # 4. Генерация ответа - ИСПОЛЬЗУЕМ НОВУЮ НЕЙТРАЛЬНУЮ ФУНКЦИЮ
                # answer = generate_response(chat_id, text) # <-- СТАРОЕ
                answer = generate_model_response(chat_id, text) # <-- НОВОЕ

                # 5. Отправка текстового ответа
                send_response(self.bot, chat_id, answer, reply_to=message.id) # Передаем bot


                # 6. Финальное обновление сообщения прогресса: "Распознано: ..."
                try:
                    self.bot.delete_message(chat_id, repl.id)
                    self.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=progress_message_id,
                        text=f"🎤*Распознано:*\n{text}\n📝_Ответ получен_",
                        parse_mode='Markdown'
                   )
                    logger.info(f"Финальное обновление сообщения прогресса {progress_message_id} для чата {chat_id}")
                except Exception as e:
                    logger.warning(f"Не удалось обновить финальное сообщение о прогрессе для чата {chat_id}: {e}")

                # 7. Отправка аудиоответа, если включен режим дублирования
                if get_voice_mode(chat_id): # Предполагается, что функция в services/context_service.py
                    # Отправляем аудио с прогрессом
                    send_audio_with_progress(chat_id, message, answer, self.bot) # Передаем bot

            else:
                # Ошибка распознавания
                error_text = text if text else "Не удалось распознать голосовое сообщение."
                try:
                    self.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=progress_message_id,
                        text=error_text
                    )
                except Exception as e:
                    logger.warning(f"Не удалось обновить сообщение об ошибке для чата {chat_id}: {e}")
                logger.info(f"Ошибка распознавания для чата {chat_id}: {error_text}")

        except Exception as e:
            logger.error(f"Ошибка обработки элемента очереди для чата {chat_id}: {e}", exc_info=True)
            try:
                # Пытаемся сообщить об ошибке пользователю
                if progress_message_id:
                    # Если уже было создано сообщение о прогрессе, обновляем его
                    self.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=progress_message_id,
                        text=f"❌ Критическая ошибка обработки голосового сообщения: {str(e)}"
                    )
                else:
                    # Иначе отправляем новое сообщение
                    self.bot.reply_to(message, f"❌ Критическая ошибка обработки голосового сообщения: {str(e)}")
            except Exception as reply_e:
                logger.error(f"Не удалось отправить сообщение об ошибке пользователю {chat_id}: {reply_e}")

# Глобальный экземпляр очереди
voice_queue_instance = None

def get_voice_queue(bot: TeleBot = None):
    """
    Получает (или создает) глобальный экземпляр очереди.

    Args:
        bot (TeleBot, optional): Экземпляр бота. Требуется при первом вызове.

    Returns:
        VoiceProcessingQueue: Экземпляр очереди.

    Raises:
        ValueError: Если bot не предоставлен при первом вызове.
    """
    global voice_queue_instance
    if voice_queue_instance is None:
        if bot is None:
            raise ValueError("Экземпляр бота (bot) должен быть предоставлен при первом вызове get_voice_queue.")
        voice_queue_instance = VoiceProcessingQueue(bot)
    return voice_queue_instance
