# services/openrouter_service.py
"""Сервис для генерации ответов моделями через OpenRouter API."""
import logging
import base64
import requests
import os # Добавлен импорт os
from typing import List, Dict, Any, Optional
from config import  CURRENT_ROLE_SETTINGS
from services.context_service import (
    get_context, add_to_context, get_chat_model,
    is_role_context_initialized, set_role_initialized,
    get_model_limit_for_chat # Импортируем для проверки длины контекста
)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Для оценки длины токенов (приблизительно)
# Можно использовать библиотеку tiktoken позже для большей точности
def estimate_tokens(text: str) -> int:
    """Очень грубая оценка количества токенов. ~1 токен = 4 символа."""
    return len(text) // 4

def truncate_context_openrouter(messages: List[Dict[str, Any]], max_tokens: int, new_message_tokens: int) -> List[Dict[str, Any]]:
    """
    Обрезает контекст для OpenRouter, если общий размер превышает максимальный.
    Удаляет самые старые сообщения.
    """
    if not messages:
        return messages

    if new_message_tokens > max_tokens:
        raise ValueError("Ваш запрос слишком велик для обработки моделью.")

    # Оценка токенов в существующем контексте
    context_tokens = sum(estimate_tokens(msg.get("content", "")) for msg in messages)

    total_tokens_needed = context_tokens + new_message_tokens

    if total_tokens_needed <= max_tokens:
        return messages

    logger.info(f"Общий контекст ({total_tokens_needed} токенов) превышает лимит ({max_tokens}), обрезаем...")
    
    truncated_messages = list(messages)
    while truncated_messages and total_tokens_needed > max_tokens:
        removed_msg = truncated_messages.pop(0)
        removed_tokens = estimate_tokens(removed_msg.get("content", ""))
        total_tokens_needed -= removed_tokens
        logger.debug(f"Удалено сообщение из контекста ({removed_tokens} токенов).")

    if not truncated_messages and total_tokens_needed > max_tokens:
        logger.error("Даже после очистки контекста запрос всё ещё слишком велик.")
        raise ValueError("Запрос слишком велик даже после очистки истории.")

    logger.info(f"Контекст обрезан. Новый размер: ~{total_tokens_needed} токенов.")
    return truncated_messages

logger = logging.getLogger(__name__)

def generate_response_openrouter(chat_id: int, prompt: str, image_bytes: Optional[bytes] = None) -> str:
    """
    Генерация ответа с помощью модели через OpenRouter API.
    
    Args:
        chat_id: ID чата
        prompt: Текст запроса
        image_bytes: Байты изображения (опционально)
        
    Returns:
        str: Ответ от модели
    """
    if not OPENROUTER_API_KEY:
        error_msg = "❌ API-ключ OpenRouter не установлен. Установите переменную окружения OPENROUTER_API_KEY."
        logger.error(error_msg)
        return error_msg

    try:
        model_id = get_chat_model(chat_id)
        
        # --- Проверка длины контекста ---
        max_context_length = get_model_limit_for_chat(chat_id)
        logger.debug(f"Максимальная длина контекста для чата {chat_id} (модель '{model_id}'): {max_context_length}")

        # --- Подготовка текущего сообщения ---
        user_message_content = []
        
        # Добавляем текст
        user_message_content.append({"type": "text", "text": prompt})
        
        # Добавляем изображение, если оно есть
        if image_bytes:
            try:
                # Кодируем изображение в base64
                image_base64 = base64.b64encode(image_bytes).decode('utf-8')
                user_message_content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_base64}"
                        # Можно добавить "detail": "high" или "low" при необходимости
                    }
                })
                logger.debug("Изображение добавлено в запрос.")
            except Exception as e:
                logger.error(f"Ошибка кодирования изображения: {e}")
                # Продолжаем без изображения
        
        # --- Подготовка контекста ---
        context_messages = get_context(chat_id)
        logger.debug(f"Получено {len(context_messages)} сообщений из контекста.")

        # Преобразуем контекст в формат OpenAI/OpenRouter
        openrouter_messages = []
        for msg in context_messages:
            role = msg['role']
            content = msg['content']
            # OpenRouter обычно использует 'user' и 'assistant'
            openrouter_role = 'user' if role == 'user' else 'assistant'
            openrouter_messages.append({"role": openrouter_role, "content": content})

        # --- Обрезка контекста ---
        estimated_prompt_tokens = estimate_tokens(prompt)
        estimated_image_tokens = 256 if image_bytes else 0 # Грубая оценка для изображения
        total_new_tokens = estimated_prompt_tokens + estimated_image_tokens

        try:
            truncated_messages = truncate_context_openrouter(
                openrouter_messages, 
                max_context_length, 
                total_new_tokens
            )
            openrouter_messages = truncated_messages
            logger.debug(f"Контекст после обрезки: {len(openrouter_messages)} сообщений.")
        except ValueError as ve:
            logger.error(f"Ошибка длины контекста: {ve}")
            return f"❌ {str(ve)}"

        # --- Настройка роли ---
        system_message = None
        if CURRENT_ROLE_SETTINGS.get('name'):
            logger.info(f"Используется роль: {CURRENT_ROLE_SETTINGS['name']}")
            
            role_parts = []
            instructions = CURRENT_ROLE_SETTINGS.get('instructions')
            knowledge_base = CURRENT_ROLE_SETTINGS.get('knowledge_base')
            
            if instructions:
                role_parts.append(f"[ИНСТРУКЦИИ РОЛИ]\n{instructions}")
            if knowledge_base:
                role_parts.append(f"[БАЗА ЗНАНИЙ РОЛИ]\n{knowledge_base}")
            
            if role_parts:
                system_content = "\n\n".join(role_parts)
                system_message = {"role": "system", "content": system_content}
                logger.debug("Системное сообщение с ролью подготовлено.")
            
            # Инициализация (добавление KB к первому запросу в чате)
            if not is_role_context_initialized(chat_id):
                logger.info(f"Инициализируем контекст для роли '{CURRENT_ROLE_SETTINGS['name']}' в чате {chat_id}")
                set_role_initialized(chat_id)
        else:
            logger.info("Используется стандартный режим.")

        # --- Формирование финального списка сообщений ---
        final_messages = []
        if system_message:
            final_messages.append(system_message)
        final_messages.extend(openrouter_messages)
        final_messages.append({"role": "user", "content": user_message_content})

        # --- Отправка запроса ---
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            # "HTTP-Referer": "YOUR_SITE_URL", # Опционально, для статистики
            # "X-Title": "YOUR_APP_NAME",     # Опционально, для статистики
        }
        payload = {
            "model": model_id,
            "messages": final_messages,
            # Можно добавить другие параметры, например:
            # "temperature": 0.7,
            # "max_tokens": 1000,
            # "stream": False
        }

        logger.info(f"Отправляем запрос к модели OpenRouter '{model_id}'...")
        logger.debug(f"Запрос к OpenRouter: {payload}") # Для отладки, можно удалить

        response = requests.post(url, headers=headers, json=payload, timeout=120) # Таймаут 120 секунд
        response.raise_for_status() # Вызовет исключение для HTTP ошибок 4xx/5xx

        response_data = response.json()
        logger.debug(f"Ответ от OpenRouter: {response_data}") # Для отладки, можно удалить

        # --- Обработка ответа ---
        if "choices" in response_data and len(response_data["choices"]) > 0:
            choice = response_data["choices"][0]
            if "message" in choice and "content" in choice["message"]:
                openrouter_answer = choice["message"]["content"].strip()
            elif "delta" in choice and "content" in choice["delta"]:
                # Для потокового режима (на случай, если включим позже)
                openrouter_answer = choice["delta"]["content"].strip()
            else:
                openrouter_answer = "Извините, не удалось сформулировать ответ (пустой ответ от модели OpenRouter)."
                logger.warning("OpenRouter вернул пустой или некорректный ответ.")
        else:
            openrouter_answer = "Извините, не удалось сформулировать ответ (некорректная структура ответа от OpenRouter)."
            logger.warning("Некорректная структура ответа от OpenRouter.")

        # --- Сохранение в контекст ---
        add_to_context(chat_id, 'user', prompt) # Сохраняем оригинальный текст запроса
        add_to_context(chat_id, 'assistant', openrouter_answer)

        logger.info(f"Ответ от модели OpenRouter получен. Длина: {len(openrouter_answer)} символов.")
        return openrouter_answer

    except requests.exceptions.RequestException as e:
        error_msg = f"❌ Ошибка сети при обращении к OpenRouter API: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg
    except Exception as e:
        error_msg = f"❌ Ошибка генерации (OpenRouter): {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg
