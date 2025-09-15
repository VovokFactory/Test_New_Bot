# bot/handlers/photo_handler.py
import asyncio
import logging
from aiogram import Router, F
from aiogram.types import Message
from services.model_service import generate_model_response

logger = logging.getLogger(__name__)

photo_router = Router()

MAX_MSG_LEN = 4000

def _split_text(text: str, chunk: int = MAX_MSG_LEN):
    for i in range(0, len(text), chunk):
        yield text[i:i + chunk]

@photo_router.message(F.photo)
async def handle_photo(message: Message):
    chat_id = message.chat.id

    try:
        # 1) Статус
        status_msg = await message.reply("_Анализирую изображение..._", parse_mode="Markdown")  # отдельный текст [1]  # noqa: E501
        # 2) Эмодзи поиска
        icon_msg = await message.bot.send_message(chat_id, "🔎")  # отдельный эмодзи [2]  # noqa: E501

        # Скачиваем самое большое фото
        photo = message.photo[-1]
        file_info = await message.bot.get_file(photo.file_id)  # получение file_path [2]  # noqa: E501
        file_obj = await message.bot.download_file(file_info.file_path)  # скачивание файла [2]  # noqa: E501
        image_bytes = file_obj.read() if hasattr(file_obj, "read") else file_obj  # bytes для модели [2]  # noqa: E501

        user_text = message.caption if message.caption else "Опиши это изображение"

        # Генерация (sync -> to_thread) с image_bytes
        response_text = await asyncio.to_thread(generate_model_response, chat_id, user_text, image_bytes)  # не блокируем loop [3][4]  # noqa: E501

        # Ответ
        if not response_text:
            await message.reply("❌ Не удалось проанализировать изображение.")
        else:
            first = True
            for chunk in _split_text(response_text):
                if first:
                    await message.reply(chunk, disable_web_page_preview=True)
                    first = False
                else:
                    await message.answer(chunk, disable_web_page_preview=True)

        # Удаляем плейсхолдеры
        for mid in (getattr(status_msg, "message_id", None), getattr(icon_msg, "message_id", None)):
            if mid:
                try:
                    await message.bot.delete_message(chat_id, mid)  # удаляем оба [1]  # noqa: E501
                except Exception:
                    pass

    except Exception as e:
        logger.error(f"Ошибка при обработке фото: {e}", exc_info=True)
        await message.reply("❌ Произошла ошибка при анализе изображения")
