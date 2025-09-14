# utils/helpers.py
import re
import logging
from typing import Optional
from aiogram import Bot
from google.genai import types
import requests

logger = logging.getLogger(__name__)

def clean_html_tags(text: str) -> str:
    """Удаление HTML тегов из текста"""
    for tag in ['b', 'i', 'u', 's', 'code', 'pre']:
        text = re.sub(fr'<{tag}>(.*?)(?=</{tag}>|$)', r'\1', text, flags=re.DOTALL)
        text = re.sub(fr'</{tag}>', '', text)
    return text

def safe_html(text: str) -> str:
    """Безопасное форматирование HTML для Telegram"""
    # Базовое экранирование
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    # Простая конвертация Markdown-подобной разметки в HTML
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
    text = re.sub(r'`(.*?)`', r'<code>\1</code>', text)
    return clean_html_tags(text)

def split_long(text: str, chunk: int = 4000):
    """Разделение длинного текста на части"""
    for i in range(0, len(text), chunk):
        yield text[i:i + chunk]

async def send_response(
    bot: Bot,
    chat_id: int,
    text: str,
    reply_to_message_id: Optional[int] = None
):
    """Отправка текстового ответа с обработкой форматирования (ASYNC для aiogram 3)"""
    try:
        safe_text = safe_html(text)
        chunks = list(split_long(safe_text))
        for i, chunk in enumerate(chunks):
            if i == 0 and reply_to_message_id:
                await bot.send_message(
                    chat_id=chat_id,
                    text=chunk,
                    reply_to_message_id=reply_to_message_id,
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
            else:
                await bot.send_message(
                    chat_id=chat_id,
                    text=chunk,
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
    except Exception as e:
        error_msg = f"⚠️ Ошибка форматирования: {str(e)}\n{text}"
        # Резервная отправка без форматирования
        await bot.send_message(chat_id, error_msg, parse_mode=None)

async def send_command_response(
    bot: Bot,
    chat_id: int,
    text: str,
    reply_to_message_id: Optional[int] = None,
    reply_markup=None
):
    """Отправка командного ответа (ASYNC для aiogram 3)"""
    try:
        chunks = list(split_long(text))
        for i, chunk in enumerate(chunks):
            params = {
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": 'HTML',
                "disable_web_page_preview": True
            }
            if i == 0 and reply_to_message_id:
                params["reply_to_message_id"] = reply_to_message_id
            if i == 0 and reply_markup is not None:
                params["reply_markup"] = reply_markup
            await bot.send_message(**params)
    except Exception as e:
        error_msg = f"⚠️ Ошибка отправки: {str(e)}\n{text}"
        await bot.send_message(chat_id, error_msg, parse_mode=None)

def process_content(content):
    """Обработка содержимого для мультимодальности (для сервисов модели)"""
    parts = []
    if isinstance(content, list):
        for item in content:
            if item.get('type') == 'text':
                parts.append(types.Part(text=item['text']))
            else:
                image_url = item['image_url']['url']
                image_response = requests.get(image_url)
                # Приведение к Part через inline_data
                parts.append(types.Part.from_bytes(data=image_response.content, mime_type="image/jpeg"))
        return parts
    else:
        return [types.Part(text=str(content))]  # Оборачиваем в Part
