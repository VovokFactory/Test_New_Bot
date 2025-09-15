# bot/handlers/voice_handler.py
"""Приём голосовых: два раздельных плейсхолдера и передача задачи в очередь."""
import logging
from aiogram import Router, F
from aiogram.types import Message
from services.voice_queue import get_voice_queue

logger = logging.getLogger(__name__)
voice_router = Router()

@voice_router.message(F.voice)
async def handle_voice(message: Message):
    try:
        chat_id = message.chat.id

        # 1) Текстовый статус (отдельное сообщение)
        status_msg = await message.reply("распознаю речь...")  # отдельный текстовый плейсхолдер [2][3]

        # 2) Отдельный эмодзи (анимируется, пока один в сообщении)
        icon_voice_msg = await message.bot.send_message(chat_id, "🎤")  # отдельный эмодзи-плейсхолдер [3]

        queue = get_voice_queue()
        if not queue:
            # Если очередь недоступна — очищаем плейсхолдеры и сообщаем об ошибке
            try:
                await message.bot.delete_message(chat_id, status_msg.message_id)  # удаление статуса [2]
                await message.bot.delete_message(chat_id, icon_voice_msg.message_id)  # удаление эмодзи [2]
            except Exception:
                pass
            await message.reply("❌ Сервис обработки голосовых временно недоступен")  # уведомление [3]
            return

        # Передаём исходное сообщение и оба плейсхолдера в очередь
        queue.add_message(message, status_msg, icon_voice_msg)  # очередь сама управляет жизненным циклом [3]

    except Exception as e:
        logger.error(f"Ошибка при приёме голосового: {e}", exc_info=True)
        await message.reply("❌ Ошибка при обработке голосового сообщения")  # обработка ошибки [3]
