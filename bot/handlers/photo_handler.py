# bot/handlers/photo_handler.py
import os
import asyncio
import logging
from aiogram import Router, F
from aiogram.types import Message, FSInputFile
from services.model_service import generate_model_response
from services.context_service import get_voice_mode
from audio_utils import generate_audio_to_opus

logger = logging.getLogger(__name__)

photo_router = Router()

MAX_MSG_LEN = 4000

def _split_text(text: str, chunk: int = MAX_MSG_LEN):
    for i in range(0, len(text), chunk):
        yield text[i:i + chunk]

@photo_router.message(F.photo)
async def handle_photo(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = message.from_user.username or "Unknown"

    try:
        await message.bot.send_chat_action(chat_id, "typing")

        # Берём самое большое фото
        photo = message.photo[-1]
        file_info = await message.bot.get_file(photo.file_id)
        file_obj = await message.bot.download_file(file_info.file_path)

        # Преобразуем в bytes
        if hasattr(file_obj, "read"):
            image_bytes = file_obj.read()
        else:
            image_bytes = file_obj

        user_text = message.caption if message.caption else "Опиши это изображение"

        # ВАЖНО: generate_model_response синхронный — запускаем в отдельном потоке.
        # Порядок аргументов: (chat_id: int, prompt: str, image_bytes: bytes | None)
        response_text = await asyncio.to_thread(generate_model_response, chat_id, user_text, image_bytes)

        if not response_text:
            await message.reply("❌ Не удалось проанализировать изображение.")
            return

        # Отправляем ответ частями, если длинный
        first = True
        for chunk in _split_text(response_text):
            if first:
                await message.reply(chunk, disable_web_page_preview=True)
                first = False
            else:
                await message.answer(chunk, disable_web_page_preview=True)

        # Озвучивание (если включено)
        if get_voice_mode(chat_id):
            try:
                await message.bot.send_chat_action(chat_id, "record_voice")
                tts_progress = await message.reply(
                    "_Озвучиваю аудиоверсию... Это может занять некоторое время_",
                    parse_mode="Markdown"
                )

                google_api_key = os.getenv("GOOGLE_API_KEY")
                tts_model = "gemini-2.5-flash-preview-tts"

                ok, result = await generate_audio_to_opus(response_text, tts_model, google_api_key)
                if not ok:
                    await tts_progress.edit_text(f"❌ Ошибка генерации аудио: {result}")
                else:
                    opus_path = result
                    try:
                        audio = FSInputFile(opus_path)
                        await message.bot.send_audio(chat_id, audio, reply_to_message_id=message.message_id)
                        await tts_progress.delete()
                    finally:
                        try:
                            os.remove(opus_path)
                        except Exception as e:
                            logger.warning(f"Не удалось удалить временный аудиофайл: {e}")
            except Exception as e:
                logger.error(f"Ошибка при озвучивании ответа: {e}", exc_info=True)
                try:
                    await message.reply("❌ Не удалось озвучить ответ.")
                except Exception:
                    pass

    except Exception as e:
        logger.error(f"Ошибка при обработке фото: {e}", exc_info=True)
        await message.reply("❌ Произошла ошибка при анализе изображения")
