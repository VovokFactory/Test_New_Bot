# utils/helpers.py
# utils/helpers.py
import re
import logging
import requests
from google.genai import types

logger = logging.getLogger(__name__)

def clean_html_tags(text: str) -> str:
    """Удаление HTML тегов из текста"""
    for tag in ['b', 'i', 'u', 's', 'code', 'pre']:
        text = re.sub(fr'<{tag}>(.*?)(?=</{tag}>|$)', r'\1', text, flags=re.DOTALL)
        text = re.sub(fr'</{tag}>', '', text)
    return text

def safe_html(text: str) -> str:
    """Безопасное форматирование HTML для Telegram"""
    text = text.replace('&', '&amp;').replace('<', '<').replace('>', '>')
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
    text = re.sub(r'`(.*?)`', r'<code>\1</code>', text)
    return clean_html_tags(text)

def split_long(text: str, chunk: int = 4000) -> list:
    """Разделение длинного текста на части"""
    for i in range(0, len(text), chunk):
        yield text[i:i + chunk]

def send_response(bot, chat_id: int, text: str, reply_to: int = None):
    """Отправка текстового ответа с обработкой форматирования"""
    try:
        safe_text = safe_html(text)
        chunks = list(split_long(safe_text))
        for i, chunk in enumerate(chunks):
            if i == 0 and reply_to:
                bot.send_message(
                    chat_id,
                    chunk,
                    reply_to_message_id=reply_to,
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
            else:
                bot.send_message(
                    chat_id,
                    chunk,
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
    except Exception as e:
        error_msg = f"⚠️ Ошибка форматирования: {str(e)}\n{text}"
        bot.send_message(chat_id, error_msg, parse_mode=None)

def send_command_response(bot, chat_id: int, text: str, reply_to: int = None, reply_markup=None):
    """Отправка командного ответа"""
    try:
        chunks = list(split_long(text))
        for i, chunk in enumerate(chunks):
            params = {
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": 'HTML',
                "disable_web_page_preview": True
            }
            if i == 0 and reply_to:
                params["reply_to_message_id"] = reply_to
            if i == 0 and reply_markup:
                params["reply_markup"] = reply_markup
            bot.send_message(**params)
    except Exception as e:
        error_msg = f"⚠️ Ошибка отправки: {str(e)}\n{text}"
        bot.send_message(chat_id, error_msg, parse_mode=None)

def process_content(content):
    """Обработка содержимого для контекста"""
    parts = []
    if isinstance(content, list):
        for item in content:
            if item.get('type') == 'text':
                parts.append(types.Part(text=item['text']))
            else:
                image_url = item['image_url']['url']
                image_response = requests.get(image_url)
                parts.append(types.File(content=image_response.content))
        return parts
    else:
        return [types.Part(text=str(content))]  # Оборачиваем в Part