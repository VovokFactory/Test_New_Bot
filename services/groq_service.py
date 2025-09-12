# services/groq_service.py
"""Сервис для генерации ответов моделями через Groq API."""
import logging
import base64
import os
import re # Добавлен импорт re
from typing import List, Dict, Any, Optional
from groq import Groq # Импорт клиента Groq
from config import CURRENT_ROLE_SETTINGS
from services.context_service import (
    get_context, add_to_context, get_chat_model,
    is_role_context_initialized, set_role_initialized,
    get_model_limit_for_chat # Импортируем для проверки длины контекста
)

# Получаем API-ключ напрямую из переменных окружения
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Настройка логгирования
logger = logging.getLogger(__name__)

# --- Функции для работы с длиной контекста (скопированы и адаптированы из openrouter_service.py) ---
def estimate_tokens(text: str) -> int:
    """Очень грубая оценка количества токенов. ~1 токен = 4 символа."""
    return len(text) // 4

def truncate_context_groq(messages: List[Dict[str, Any]], max_tokens: int, new_message_tokens: int) -> List[Dict[str, Any]]:
    """
    Обрезает контекст для Groq, если общий размер превышает максимальный.
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
# --- Конец функций для работы с длиной контекста ---

# --- Новая функция для обработки ответа от Groq ---
def process_groq_response(groq_raw_answer: str) -> str:
    """
    Обрабатывает "сырой" ответ от Groq:
    1. Находит теги <think>...</think>.
    2. Схлопывает содержимое в одну строку.
    3. Оборачивает его в <tg-spoiler>.
    4. Убирает теги Gemma, если вдруг модель их вернула.
    5. Очищает результат от лишних пустых строк.
    """
    # 1. Обработка тегов <think>
    think_match = re.search(r"<think>(.*?)</think>", groq_raw_answer, flags=re.DOTALL)
    if think_match:
        # Извлекаем содержимое тегов <think>
        think_content = think_match.group(1)
        # Схлопываем многострочный текст в одну строку
        think_content_spoiler = think_content.replace("\n", " ").replace("\r", " ").strip()
        # Заменяем весь блок <think>...</think> на строку со спойлером
        processed_answer = re.sub(
            r"<think>.*?</think>", 
            f'Процесс размышлений (скрыт): <tg-spoiler>{think_content_spoiler}</tg-spoiler>\n\n', 
            groq_raw_answer, 
            flags=re.DOTALL
        )
    else:
        # Если тегов <think> нет, просто убираем возможные остатки тегов (на всякий случай)
        processed_answer = re.sub(r"</?think>", "", groq_raw_answer)

    # 2. Убираем теги Gemma (на случай, если модель как-то их вернула)
    processed_answer = re.sub(r"<start_of_turn>.*?<end_of_turn>\s*", "", processed_answer, flags=re.DOTALL)
    processed_answer = processed_answer.replace("<start_of_turn>", "").replace("<end_of_turn>", "")
    
    # 3. Очищаем от лишних пустых строк в начале и конце
    processed_answer = processed_answer.strip()

    return processed_answer
# --- Конец новой функции ---

def generate_response_groq(chat_id: int, prompt: str, image_bytes: Optional[bytes] = None) -> str:
    """
    Генерация ответа с помощью модели через Groq API.
    
    Args:
        chat_id: ID чата
        prompt: Текст запроса
        image_bytes: Байты изображения (опционально)
        
    Returns:
        str: Ответ от модели
    """
    if not GROQ_API_KEY:
        error_msg = "❌ API-ключ Groq не установлен. Установите переменную окружения GROQ_API_KEY."
        logger.error(error_msg)
        return error_msg

    # Groq API не поддерживает изображения напрямую через chat.completions.create
    # https:// console.groq.com/docs/vision
    # На момент последнего обновления, Groq поддерживает изображения только для модели llava-v1.5-7b-4096-preview
    # и требует специального формата сообщений.
    # Для универсальности и упрощения, мы будем игнорировать изображения для моделей Groq,
    # или можно реализовать специальную логику для llava-v1.5-7b-4096-preview.
    # Пока что просто логируем и игнорируем.
    if image_bytes:
        logger.warning("Groq API: изображения в текущей реализации не поддерживаются для большинства моделей. Игнорируем изображение.")
        # Можно вернуть сообщение пользователю:
        # return "❌ Groq API: изображения не поддерживаются выбранной моделью."

    try:
        model_id = get_chat_model(chat_id)
        
        # --- Проверка длины контекста ---
        max_context_length = get_model_limit_for_chat(chat_id)
        logger.debug(f"Максимальная длина контекста для чата {chat_id} (модель '{model_id}'): {max_context_length}")

        # --- Подготовка текущего сообщения ---
        user_message_content = prompt # Groq ожидает строку для текста
        
        # --- Подготовка контекста ---
        context_messages = get_context(chat_id)
        logger.debug(f"Получено {len(context_messages)} сообщений из контекста.")

        # Преобразуем контекст в формат Groq (OpenAI)
        groq_messages = []
        for msg in context_messages:
            role = msg['role']
            content = msg['content']
            # Groq использует 'user' и 'assistant'
            groq_role = 'user' if role == 'user' else 'assistant'
            groq_messages.append({"role": groq_role, "content": content})

        # --- Обрезка контекста ---
        estimated_prompt_tokens = estimate_tokens(prompt)
        # estimated_image_tokens = 256 if image_bytes else 0 # Игнорируем изображения
        total_new_tokens = estimated_prompt_tokens # + estimated_image_tokens

        try:
            truncated_messages = truncate_context_groq(
                groq_messages, 
                max_context_length, 
                total_new_tokens
            )
            groq_messages = truncated_messages
            logger.debug(f"Контекст после обрезки: {len(groq_messages)} сообщений.")
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
        final_messages.extend(groq_messages)
        final_messages.append({"role": "user", "content": user_message_content})

        # --- Отправка запроса ---
        client = Groq(api_key=GROQ_API_KEY) # Создаем клиент с ключом
        
        logger.info(f"Отправляем запрос к модели Groq '{model_id}'...")
        # logger.debug(f"Запрос к Groq: messages={final_messages}") # Для отладки

        # Groq.ChatCompletion.create -> client.chat.completions.create (v1.0+)
        chat_completion = client.chat.completions.create(
            messages=final_messages,
            model=model_id,
            # Можно добавить другие параметры, например:
            # temperature=0.7,
            # max_tokens=1000,
        )

        # --- Обработка ответа ---
        if chat_completion.choices and len(chat_completion.choices) > 0:
            choice = chat_completion.choices[0]
            if choice.message and choice.message.content:
                groq_raw_answer = choice.message.content.strip() # <-- Получаем "сырой" ответ
            else:
                groq_raw_answer = "Извините, не удалось сформулировать ответ (пустой ответ от модели Groq)."
                logger.warning("Groq вернул пустой или некорректный ответ.")
        else:
            groq_raw_answer = "Извините, не удалось сформулировать ответ (некорректная структура ответа от Groq)."
            logger.warning("Некорректная структура ответа от Groq.")

        # === Обработка ответа с помощью новой функции ===
        groq_answer = process_groq_response(groq_raw_answer) # <-- Обрабатываем ответ
        # === Конец обработки ответа ===

        # --- Сохранение в контекст ---
        # ВАЖНО: Сохраняем в историю "сырой" ответ, так как он может содержать теги,
        # которые нужны для формирования будущих промптов (например, для Gemma)
        # или для отладки.
        add_to_context(chat_id, 'user', prompt) # Сохраняем оригинальный текст запроса
        add_to_context(chat_id, 'assistant', groq_raw_answer) # <-- Сохраняем СЫРОЙ ответ

        logger.info(f"Ответ от модели Groq получен и обработан. Длина (сырого): {len(groq_raw_answer)} символов.")
        # Возвращаем ОБРАБОТАННЫЙ ответ пользователю
        return groq_answer # <-- Возвращаем обработанный ответ

    except Exception as e:
        error_msg = f"❌ Ошибка генерации (Groq): {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg
