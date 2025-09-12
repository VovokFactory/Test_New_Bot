# services/audio_service.py
"""Сервис для работы с аудио"""

import logging
import os
from telebot import TeleBot
from audio_utils import generate_audio_to_opus, process_voice_message


logger = logging.getLogger(__name__)

def process_voice_message_service(bot: TeleBot, message) -> str:
    """Обработка голосового сообщения"""
    return process_voice_message(bot, message)

def send_audio_response(chat_id: int, text: str, bot: TeleBot):
    """Отправка голосового сообщения через audio_utils"""
    repl = bot.send_message(chat_id, "🎙")
    logger.info(f"Sending audio for: {text[:50]}...")
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    # TODO: Получать модель из настроек чата
    success, result = generate_audio_to_opus(text, "gemini-2.5-flash-preview-tts", GOOGLE_API_KEY)
    if success:
        audio_path = result
        try:
            # Проверяем существование файла
            if not os.path.exists(audio_path):
                error_msg = f"❌ Аудио файл не найден: {audio_path}"
                logger.error(error_msg)
                bot.send_message(chat_id, error_msg)
                return
            # Проверяем размер файла
            file_size = os.path.getsize(audio_path)
            logger.info(f"Audio file size: {file_size} bytes")
            if file_size == 0:
                error_msg = "❌ Аудио файл пустой"
                logger.error(error_msg)
                bot.send_message(chat_id, error_msg)
                return
            # Отправляем файл
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=repl.message_id,
                text="🎙 Голосовой ответ готов!"
        )
            with open(audio_path, 'rb') as audio_file:
                bot.send_audio(chat_id, audio_file)
                logger.info("Audio sent successfully")
            # Удаляем временный файл
            os.remove(audio_path)
            logger.info("Temporary file removed")
        except Exception as e:
            error_msg = f"❌ Ошибка отправки аудио: {str(e)}"
            logger.exception(error_msg)
            bot.send_message(chat_id, error_msg)
    else:
        error_msg = f"❌ Ошибка генерации аудио: {result}"
        logger.error(error_msg)
        bot.send_message(chat_id, error_msg)

def send_audio_with_progress(chat_id: int, message, answer: str, bot: TeleBot):
    """Отправка аудио с прогрессом"""
    # 1. Анимация и сообщение о начале озвучивания
    bot.send_chat_action(chat_id, 'record_audio')  # Анимация "Запись аудио"
    progress_audio = bot.reply_to(
        message,
        "_Озвучиваю аудиоверсию... Это может занять несколько минут_",
        reply_to_message_id=message.id,
        parse_mode='Markdown'
    )
    

    # 2. Генерация и отправка аудио
    send_audio_response(chat_id, answer, bot)
    # 3. Удалить промежуточное сообщение
    bot.delete_message(chat_id, progress_audio.id)
