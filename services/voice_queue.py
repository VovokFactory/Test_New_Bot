# services/voice_queue.py
import asyncio
import logging
import os
from typing import Optional, Tuple
from aiogram import Bot
from config import VOICE_WORKERS_COUNT
from audio_utils import process_voice_message
from services.model_service import generate_model_response
from utils.helpers import send_response  # ВАЖНО: это async-версия из utils/helpers.py
from services.audio_service import send_audio_with_progress
from services.context_service import get_voice_mode

logger = logging.getLogger(__name__)

class VoiceQueue:
    """Очередь для асинхронной обработки голосовых сообщений в aiogram 3.x"""

    def __init__(self, bot: Bot, loop: asyncio.AbstractEventLoop):
        self.bot = bot
        self.loop = loop
        self.queue: asyncio.Queue[Tuple] = asyncio.Queue()
        self.workers: list[asyncio.Task] = []
        self.running = False

        self.google_api_key = os.getenv("GOOGLE_API_KEY")
        if not self.google_api_key:
            logger.error("GOOGLE_API_KEY не найден в переменных окружения")

    def start(self):
        if self.running:
            logger.warning("Очередь уже запущена")
            return
        self.running = True
        logger.info(f"Запуск очереди обработки голоса с {VOICE_WORKERS_COUNT} воркерами")
        for i in range(VOICE_WORKERS_COUNT):
            worker = asyncio.create_task(self._worker(f"worker-{i+1}"))
            self.workers.append(worker)
        logger.info(f"Запущено {len(self.workers)} воркеров")

    def stop(self):
        if not self.running:
            return
        logger.info("Остановка очереди обработки голоса...")
        self.running = False
        for worker in self.workers:
            worker.cancel()
        self.workers.clear()
        logger.info("Очередь обработки голоса остановлена")

    def add_message(self, voice_message, processing_message):
        if not self.running:
            logger.error("Очередь не запущена")
            return
        asyncio.create_task(self.queue.put((voice_message, processing_message)))
        logger.debug("Сообщение добавлено в очередь")

    async def _worker(self, worker_name: str):
        logger.info(f"Воркер {worker_name} запущен")
        while self.running:
            try:
                voice_message, processing_message = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                logger.info(f"{worker_name}: Начинаю обработку голосового сообщения")
                await self._process_voice_message(voice_message, processing_message, worker_name)
                self.queue.task_done()
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                logger.info(f"Воркер {worker_name} отменен")
                break
            except Exception as e:
                logger.error(f"Ошибка в воркере {worker_name}: {e}", exc_info=True)
                continue
        logger.info(f"Воркер {worker_name} остановлен")

    async def _process_voice_message(self, voice_message, processing_message, worker_name: str):
        chat_id = voice_message.chat.id
        user_id = voice_message.from_user.id
        username = voice_message.from_user.username or "Unknown"

        try:
            # 1) Транскрипция (async)
            logger.info(f"{worker_name}: Транскрибирую сообщение от {username}")
            if not self.google_api_key:
                await processing_message.edit_text("❌ API ключ Google не настроен")
                return

            transcribed_text = await process_voice_message(self.bot, voice_message, self.google_api_key)

            if not isinstance(transcribed_text, str) or transcribed_text.strip().startswith("❌"):
                await processing_message.edit_text(f"❌ Ошибка транскрибации: {transcribed_text}")
                return

            # Показать формат как на скрине: блок "Распознано: <текст>" и далее статус ответа
            recognized_block = f"🖋 Распознано:\n{transcribed_text.strip()}"
            await processing_message.edit_text(recognized_block)  # редактируем, НЕ удаляем [2][6]

            # 2) Генерация ответа (sync → to_thread)
            logger.info(f"{worker_name}: Генерирую ответ")
            # На время генерации показываем статус
            try:
                await processing_message.edit_text(f"{recognized_block}\n\n📝 Формулирую ответ...")
            except Exception:
                pass

            # ВАЖНО: правильный порядок аргументов и вынос в поток [7][9]
            response_text = await asyncio.to_thread(generate_model_response, chat_id, transcribed_text, None)

            if not response_text:
                await processing_message.edit_text(f"{recognized_block}\n\n❌ Не удалось сгенерировать ответ")
                return

            # 3) Обновить прогресс "Ответ получен"
            try:
                await processing_message.edit_text(f"{recognized_block}\n\n📝 Ответ получен")
            except Exception:
                pass

            # 4) Текст ответа всегда как reply на оригинальное голосовое
            await send_response(self.bot, chat_id, response_text, voice_message.message_id)

            # 5) Опциональная озвучка
            if get_voice_mode(chat_id):
                await send_audio_with_progress(
                    bot=self.bot,
                    chat_id=chat_id,
                    text=response_text,
                    reply_to_message_id=voice_message.message_id
                )

            logger.info(f"{worker_name}: Обработка завершена для {username}")

        except Exception as e:
            logger.error(f"{worker_name}: Ошибка при обработке сообщения от {username}: {e}", exc_info=True)
            try:
                await processing_message.edit_text("❌ Произошла ошибка при обработке голосового сообщения")
            except Exception:
                pass


# Глобальный синглтон-экземпляр очереди
_voice_queue_instance: Optional[VoiceQueue] = None

def get_voice_queue(bot: Bot = None, loop: asyncio.AbstractEventLoop = None) -> Optional[VoiceQueue]:
    global _voice_queue_instance
    if _voice_queue_instance is None and bot is not None and loop is not None:
        _voice_queue_instance = VoiceQueue(bot, loop)
    return _voice_queue_instance
