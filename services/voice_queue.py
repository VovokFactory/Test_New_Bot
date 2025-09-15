# services/voice_queue.py
import asyncio
import logging
import os
from typing import Optional, Tuple
from aiogram import Bot
from config import VOICE_WORKERS_COUNT
from audio_utils import process_voice_message
from services.model_service import generate_model_response
from utils.helpers import send_response
from services.audio_service import send_audio_with_progress
from services.context_service import get_voice_mode

logger = logging.getLogger(__name__)

class VoiceQueue:
    """
    Очередь асинхронной обработки голосовых для aiogram 3.x

    Сценарий:
      1) В хэндлере уже отправлены два сообщения: статус "распознаю речь..." и отдельный 🎤.
      2) После транскрибации: УДАЛЯЕМ 🎤, редактируем статус на:
         "🎤Распознано:\n<текст>\nФормулирую ответ".
      3) Отдельным сообщением отправляем 📝.
      4) После генерации: удаляем 📝 и редактируем статус: "Ответ получен".
      5) Итоговый ответ отправляем как reply к исходному голосовому.
    """

    def __init__(self, bot: Bot, loop: asyncio.AbstractEventLoop):
        self.bot = bot
        self.loop = loop
        # Элементы очереди: (voice_message, status_msg, icon_voice_msg)
        self.queue: asyncio.Queue[Tuple] = asyncio.Queue()
        self.workers: list[asyncio.Task] = []
        self.running = False
        self.google_api_key = os.getenv("GOOGLE_API_KEY")

    def start(self):
        if self.running:
            return
        self.running = True
        for i in range(VOICE_WORKERS_COUNT):
            self.workers.append(asyncio.create_task(self._worker(f"worker-{i+1}")))
        logger.info(f"Запущено {len(self.workers)} воркеров обработки голоса")

    def stop(self):
        if not self.running:
            return
        self.running = False
        for w in self.workers:
            w.cancel()
        self.workers.clear()
        logger.info("Очередь обработки голоса остановлена")

    def add_message(self, voice_message, status_msg, icon_voice_msg):
        # Кладём задачу с обоими плейсхолдерами
        asyncio.create_task(self.queue.put((voice_message, status_msg, icon_voice_msg)))

    async def _worker(self, name: str):
        logger.info(f"{name}: запущен")
        while self.running:
            try:
                voice_message, status_msg, icon_voice_msg = await asyncio.wait_for(
                    self.queue.get(), timeout=1.0
                )
            except asyncio.TimeoutError:
                continue

            try:
                chat_id = voice_message.chat.id

                # 1) Транскрибация (асинхронная)
                text = await process_voice_message(self.bot, voice_message, self.google_api_key)
                if not isinstance(text, str) or text.strip().startswith("❌"):
                    # Ошибка транскрибации: удаляем 🎤, обновляем статус и выходим
                    await self._safe_delete(chat_id, getattr(icon_voice_msg, "message_id", None))
                    try:
                        await status_msg.edit_text(f"❌ Ошибка транскрибации: {text}")
                    except Exception:
                        pass
                    continue

                # Удаляем стартовый эмодзи СРАЗУ ПОСЛЕ транскрибации (требование)
                await self._safe_delete(chat_id, getattr(icon_voice_msg, "message_id", None))

                # Обновляем статус на распознанный текст + формирование ответа
                recognized_block = f"🎤Распознано:\n{text.strip()}\nФормулирую ответ"
                try:
                    await status_msg.edit_text(recognized_block)
                except Exception:
                    pass

                # 2) Отдельный плейсхолдер для этапа генерации ответа
                icon_answer_msg = await self.bot.send_message(chat_id, "📝")

                # 3) Генерация ответа (синхронная → отдельный поток, чтобы не блокировать UI)
                response = await asyncio.to_thread(generate_model_response, chat_id, text, None)

                # Удаляем 📝 независимо от результата
                await self._safe_delete(chat_id, getattr(icon_answer_msg, "message_id", None))

                if not response:
                    # Обновляем статус, если ответ не получен
                    try:
                        await status_msg.edit_text(
                            recognized_block.replace("Формулирую ответ", "Ответ не получен")
                        )
                    except Exception:
                        pass
                    continue

                # 4) Меняем "Формулирую ответ" → "Ответ получен"
                try:
                    await status_msg.edit_text(
                        recognized_block.replace("Формулирую ответ", "Ответ получен")
                    )
                except Exception:
                    pass

                # Отправляем итоговый ответ как reply к голосовому
                await send_response(self.bot, chat_id, response, voice_message.message_id)

                # Озвучка по режиму
                if get_voice_mode(chat_id) and response:
                    await send_audio_with_progress(
                        self.bot, chat_id, response, voice_message.message_id
                    )

            except Exception as e:
                logger.error(f"{name}: {e}", exc_info=True)
                # На всякий случай пробуем убрать эмодзи, если остались
                try:
                    await self._safe_delete(voice_message.chat.id, getattr(icon_voice_msg, "message_id", None))
                except Exception:
                    pass
            finally:
                self.queue.task_done()
        logger.info(f"{name}: остановлен")

    async def _safe_delete(self, chat_id: int, message_id: Optional[int]):
        if not message_id:
            return
        try:
            await self.bot.delete_message(chat_id, message_id)
        except Exception:
            # игнорируем ограничения/тайминги Telegram при удалении
            pass

# Синглтон очереди
_voice_queue_instance: Optional[VoiceQueue] = None

def get_voice_queue(bot: Bot = None, loop: asyncio.AbstractEventLoop = None) -> Optional[VoiceQueue]:
    global _voice_queue_instance
    if _voice_queue_instance is None and bot is not None and loop is not None:
        _voice_queue_instance = VoiceQueue(bot, loop)
    return _voice_queue_instance
