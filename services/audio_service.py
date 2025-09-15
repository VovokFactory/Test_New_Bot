# services/audio_service.py
"""Сервис озвучки: сначала текстовый статус, затем отдельный эмодзи, по готовности — удаление эмодзи, правка статуса и отправка аудио."""
import logging
import os
from aiogram import Bot
from aiogram.types import FSInputFile
from audio_utils import generate_audio_to_opus

logger = logging.getLogger(__name__)

async def send_audio_with_progress(
    bot: Bot,
    chat_id: int,
    text: str,
    reply_to_message_id: int | None = None
):
    # 1) Текстовый статус
    status_msg = await bot.send_message(
        chat_id,
        "Генерирую аудиоответ, это может занять несколько минут..."
    )
    # 2) Отдельный эмодзи (большой/анимируется, пока один)
    icon_msg = await bot.send_message(chat_id, "🎙")

    google_api_key = os.getenv("GOOGLE_API_KEY")
    tts_model = "gemini-2.5-flash-preview-tts"

    ok = False
    result_path_or_error = ""
    try:
        ok, result_path_or_error = await generate_audio_to_opus(text, tts_model, google_api_key)

        # Удаляем эмодзи независимо от успеха
        try:
            await bot.delete_message(chat_id, icon_msg.message_id)
        except Exception:
            pass

        if not ok:
            # Обновляем статус — ошибка
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_msg.message_id,
                    text=f"❌ Ошибка генерации аудио: {result_path_or_error}"
                )
            except Exception:
                pass
            return

        # Обновляем статус — готово
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_msg.message_id,
                text="🎙 Голосовой ответ готов!"
            )
        except Exception:
            pass

        # Отправляем файл
        audio = FSInputFile(result_path_or_error)
        await bot.send_audio(chat_id, audio, reply_to_message_id=reply_to_message_id)

    except Exception as e:
        logger.exception(f"TTS send error: {e}")
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_msg.message_id,
                text=f"❌ Ошибка при отправке аудио: {e}"
            )
        except Exception:
            pass
    finally:
        # Чистим временный файл, если он существует
        try:
            if ok and isinstance(result_path_or_error, str) and os.path.exists(result_path_or_error):
                os.remove(result_path_or_error)
        except Exception:
            pass
