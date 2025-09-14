# bot/handlers/voice_handler.py - aiogram 3.x version
"""Обработчик голосовых сообщений для aiogram 3.x"""
import logging
import os
from aiogram import Router, F
from aiogram.types import Message
from services.voice_queue import get_voice_queue

logger = logging.getLogger(__name__)

voice_router = Router()

@voice_router.message(F.voice)
async def handle_voice(message: Message):
    """
    Обрабатывает входящие голосовые сообщения.
    Добавляет сообщение в очередь для асинхронной обработки.
    """
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        username = message.from_user.username or "Unknown"
        
        logger.info(f"Получено голосовое сообщение от пользователя {username} (ID: {user_id}) в чате {chat_id}")
        
        # Получаем очередь обработки голоса
        voice_queue = get_voice_queue()
        
        if voice_queue is None:
            logger.error("Очередь обработки голоса не инициализирована")
            await message.reply("❌ Сервис обработки голосовых сообщений временно недоступен")
            return
        
        # Отправляем уведомление о начале обработки
        processing_message = await message.reply("🎤 Обрабатываю голосовое сообщение...")
        
        # Добавляем сообщение в очередь
        voice_queue.add_message(message, processing_message)
        
        logger.info(f"Голосовое сообщение от {username} добавлено в очередь обработки")
        
    except Exception as e:
        logger.error(f"Ошибка при обработке голосового сообщения: {e}", exc_info=True)
        await message.reply("❌ Произошла ошибка при обработке голосового сообщения")

@voice_router.message(F.audio)
async def handle_audio(message: Message):
    """Обработчик аудиофайлов"""
    await message.reply(
        "🎵 Я пока не поддерживаю обработку аудиофайлов.\n"
        "Пожалуйста, отправьте голосовое сообщение вместо аудиофайла."
    )

@voice_router.message(F.video_note)
async def handle_video_note(message: Message):
    """Обработчик кружочков (видеосообщений)"""
    await message.reply(
        "📹 Видеосообщения пока не поддерживаются.\n"
        "Пожалуйста, отправьте голосовое сообщение."
    )