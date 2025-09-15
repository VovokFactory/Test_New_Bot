# bot/handlers/text_handler.py
import os
import asyncio
import logging
from aiogram import Router, F
from aiogram.types import Message
from services.model_service import generate_model_response
from services.context_service import get_voice_mode
from services.audio_service import send_audio_with_progress  # используем общий сервис TTS

logger = logging.getLogger(__name__)

text_router = Router()

MAX_MSG_LEN = 4000

def _split_text(text: str, chunk: int = MAX_MSG_LEN):
    for i in range(0, len(text), chunk):
        yield text[i:i + chunk]

@text_router.message(F.text)
async def handle_text_message(message: Message):
    # Игнорируем команды
    if message.text.startswith('/'):
        return

    chat_id = message.chat.id
    user_input = message.text

    try:
        # 1) Отдельное сообщение статуса
        status_msg = await message.reply("_Формулирую ответ..._", parse_mode="Markdown")  # текст статуса [aiogram editMessageText]  # noqa: E501
        # 2) Отдельный эмодзи (крупный/анимируется, пока один)
        icon_msg = await message.bot.send_message(chat_id, "📝")  # отдельное сообщение-эмодзи  # noqa: E501

        # Генерация (sync -> to_thread), не блокируем event loop
        response_text = await asyncio.to_thread(generate_model_response, chat_id, user_input, None)

        # Отправка ответа
        if not response_text:
            await message.reply("❌ Не удалось сгенерировать ответ.")
        else:
            first = True
            for chunk in _split_text(response_text):
                if first:
                    await message.reply(chunk, disable_web_page_preview=True)
                    first = False
                else:
                    await message.answer(chunk, disable_web_page_preview=True)

        # Удаляем плейсхолдеры текста
        for mid in (getattr(status_msg, "message_id", None), getattr(icon_msg, "message_id", None)):
            if mid:
                try:
                    await message.bot.delete_message(chat_id, mid)
                except Exception:
                    pass

        # Голосовой дубль: теперь ВСЮ логику плейсхолдеров (сначала текст, затем эмодзи)
        # выполняет общий сервис send_audio_with_progress
        if response_text and get_voice_mode(chat_id):
            await send_audio_with_progress(
                bot=message.bot,
                chat_id=chat_id,
                text=response_text,
                reply_to_message_id=message.message_id
            )

    except Exception as e:
        logger.error(f"Ошибка при обработке текста: {e}", exc_info=True)
        await message.reply("❌ Произошла ошибка при обработке сообщения")
