# services/gemini_service.py
"""Сервис для генерации ответов моделями семейства Gemini."""
import logging
from datetime import datetime
from google import genai
from google.genai import types
# Импортируем настройки роли из config и функции из context_service
from config import CURRENT_ROLE_SETTINGS
from services.context_service import (
    get_context, add_to_context, get_chat_model,
    is_role_context_initialized, set_role_initialized,
    get_model_limit_for_chat, # Импортируем новую функцию для получения лимита

)
from utils.helpers import process_content

logger = logging.getLogger(__name__)

# --- Добавленный код: Функции для работы с длиной контекста ---
# Примечание: Оценка для Gemini потенциально может быть точнее, если использовать count_tokens,
# но для совместимости и простоты используем аналогичную грубую оценку.
# В будущем эту функцию можно улучшить, используя client.models.count_tokens.

def estimate_content_tokens(parts) -> int:
    """
    Очень простая оценка количества токенов в содержимом для Gemini.
    Это приблизительная оценка.
    Здесь мы предполагаем ~1 токен = 4 символа для текста.
    Для изображений делаем грубую оценку (например, 256 "токенов").
    """
    total_tokens = 0
    for part in parts:
        if hasattr(part, 'text') and part.text:
            # Очень грубая оценка: 1 токен ~ 4 символа
            total_tokens += len(part.text) // 4
        elif hasattr(part, 'inline_data') and part.inline_data and part.inline_data.data:
            # Грубая оценка для изображения
            total_tokens += 256 # Примерное значение для изображения
    return total_tokens

def truncate_context(context_messages, max_context_tokens, prompt_tokens, image_tokens):
    """
    Обрезает контекст, если общий размер превышает максимальный.
    Удаляет самые старые сообщения.
    Адаптировано для формата контекста Gemini (список словарей с 'role' и 'parts').
    """
    if not context_messages:
        return context_messages

    # Оценка токенов в текущем запросе (новое сообщение пользователя)
    current_request_tokens = prompt_tokens + image_tokens
    if current_request_tokens > max_context_tokens:
        # Случай 2: Новое сообщение само по себе слишком велико
        logger.warning(f"Новое сообщение слишком велико ({current_request_tokens} токенов) для контекстного окна ({max_context_tokens}).")
        raise ValueError("Ваш запрос (включая изображение) слишком велик для обработки моделью.")

    # Оценка токенов в существующем контексте
    context_tokens = 0
    for msg in context_messages:
        # Оцениваем токены во всех частях сообщения
        msg_parts = msg.get('parts', [])
        for part in msg_parts:
             if hasattr(part, 'text') and part.text:
                 context_tokens += len(part.text) // 4
             elif hasattr(part, 'inline_data') and part.inline_data and part.inline_data.data:
                 context_tokens += 256

    total_tokens_needed = context_tokens + current_request_tokens

    # Если всё в порядке, возвращаем контекст без изменений
    if total_tokens_needed <= max_context_tokens:
        return context_messages

    # Случай 1: Нужно обрезать существующий контекст
    logger.info(f"Общий контекст ({total_tokens_needed} токенов) превышает лимит ({max_context_tokens}), обрезаем...")
    
    # Простая стратегия: удаляем сообщения с начала (самые старые)
    truncated_context = list(context_messages) # Копируем список
    while truncated_context and total_tokens_needed > max_context_tokens:
        removed_msg = truncated_context.pop(0) # Удаляем самое старое сообщение
        removed_parts = removed_msg.get('parts', [])
        removed_tokens = 0
        for part in removed_parts:
             if hasattr(part, 'text') and part.text:
                 removed_tokens += len(part.text) // 4
             elif hasattr(part, 'inline_data') and part.inline_data and part.inline_data.data:
                 removed_tokens += 256
        total_tokens_needed -= removed_tokens
        logger.debug(f"Удалено сообщение из контекста ({removed_tokens} токенов).")

    if not truncated_context and total_tokens_needed > max_context_tokens:
         # Это маловероятно, но на случай, если даже пустой контекст не помогает
         logger.error("Даже после очистки контекста запрос всё ещё слишком велик.")
         raise ValueError("Запрос слишком велик даже после очистки истории.")

    logger.info(f"Контекст обрезан. Новый размер: ~{total_tokens_needed} токенов.")
    return truncated_context
# --- Конец добавленного кода ---

def generate_response_gemini(chat_id: int, prompt: str, image_bytes: bytes = None) -> str:
    """Генерация ответа с помощью модели Gemini."""
    try:
        model_id = get_chat_model(chat_id)
        client = genai.Client()

        # --- Добавленный код: Проверка длины контекста ---
        # 1. Получить лимит контекста для модели этого чата (из кэша или с запросом)
        max_context_length = get_model_limit_for_chat(chat_id)
        logger.debug(f"Максимальная длина контекста для чата {chat_id} (модель '{model_id}'): {max_context_length}")

        # 2. Подготовить текущий ввод для оценки его размера
        current_parts_for_estimation = [types.Part(text=prompt)]
        if image_bytes:
            current_parts_for_estimation.append(types.Part(
                inline_data=types.Blob(mime_type='image/jpeg', data=image_bytes)
            ))

        # 3. Оценить размер токенов в новом сообщении
        estimated_prompt_tokens = estimate_content_tokens([types.Part(text=prompt)])
        estimated_image_tokens = estimate_content_tokens([types.Part(inline_data=types.Blob(mime_type='image/jpeg', data=image_bytes))]) if image_bytes else 0
        logger.debug(f"Оценка токенов: Prompt={estimated_prompt_tokens}, Image={estimated_image_tokens}")

        # 4. Получить текущий контекст
        # Формируем контекст в формате Gemini
        ctx = []
        raw_context_messages = get_context(chat_id) # Получаем сырые сообщения из контекста
        for m in raw_context_messages:
            processed_content = process_content(m['content'])
            ctx.append({
                'role': 'user' if m['role'] == 'user' else 'model',
                'parts': processed_content
            })
        
        logger.debug(f"Получено {len(raw_context_messages)} сообщений из контекста.")

        # 5. Попытка обрезать контекст, если необходимо
        try:
            # Обрезаем контекст, если нужно, или выбрасываем исключение, если новое сообщение слишком велико
            # Передаем ctx в формате Gemini
            truncated_context_messages = truncate_context(
                ctx, 
                max_context_length, 
                estimated_prompt_tokens, 
                estimated_image_tokens
            )
            # Если truncate_context не выбросило исключение, значит всё в порядке или контекст обрезан
            ctx = truncated_context_messages # Используем обрезанный контекст
            logger.debug(f"Контекст после обрезки: {len(ctx)} сообщений.")
        except ValueError as ve:
            # Это означает, что новое сообщение слишком велико или ошибка после обрезки
            logger.error(f"Ошибка длины контекста: {ve}")
            return f"❌ {str(ve)}" # Возвращаем сообщение пользователю
        # --- Конец добавленного кода ---

        # --- Остальной код (с небольшими изменениями для использования обрезанного контекста) ---

        # Подготавливаем текущий ввод (повторно, так как он может понадобиться для логов)
        current_parts = [types.Part(text=prompt)]
        if image_bytes:
            logger.debug(f"[DEBUG] Размер image_bytes: {len(image_bytes)} байт")
            image_part = types.Part(
                inline_data=types.Blob(
                    mime_type='image/jpeg',
                    data=image_bytes
                )
            )
            current_parts.append(image_part)

        # Настройка роли (если задана)
        if CURRENT_ROLE_SETTINGS.get('name'):
            logger.info(f"Используется роль: {CURRENT_ROLE_SETTINGS['name']}")
            if not is_role_context_initialized(chat_id):
                logger.info(f"Инициализируем контекст для роли '{CURRENT_ROLE_SETTINGS['name']}' в чате {chat_id}")
                if CURRENT_ROLE_SETTINGS.get('knowledge_base'):
                    kb_text = f"[БАЗА ЗНАНИЙ РОЛИ {CURRENT_ROLE_SETTINGS['name']}]\n{CURRENT_ROLE_SETTINGS['knowledge_base']}"
                    current_parts.insert(0, types.Part(text=kb_text))
                    logger.info(f"База знаний роли добавлена к первому запросу в чате {chat_id}")
                    logger.debug(f"СОДЕРЖАНИЕ БАЗЫ ЗНАНИЙ:\n{CURRENT_ROLE_SETTINGS['knowledge_base'][:500]}...")
                set_role_initialized(chat_id)
        else:
            logger.info("Используется стандартный режим.")

        current_input = {'role': 'user', 'parts': current_parts}
        # Используем обрезанный контекст ctx
        contents = ctx + [current_input] 

        # === ЛОГИРОВАНИЕ ВСЕГО КОНТЕКСТА ===
        logger.debug(f"ПОЛНЫЙ КОНТЕКСТ (contents) для чата {chat_id} (для Gemini):")
        for i, msg in enumerate(contents):
            role = msg.get('role', 'unknown')
            parts = msg.get('parts', [])
            logger.debug(f"  [{i}] Роль: {role}")
            for j, part in enumerate(parts):
                try:
                    if hasattr(part, 'text') and part.text is not None:
                        text_preview = part.text[:300] + "..." if len(part.text) > 300 else part.text
                        logger.debug(f"      Часть {j}: TEXT ({len(part.text)} символов) -> {text_preview}")
                    elif hasattr(part, 'inline_data') and part.inline_data:
                        data = getattr(part.inline_data, 'data', None)
                        size = len(data) if data else 0
                        mime_type = getattr(part.inline_data, 'mime_type', 'unknown')
                        logger.debug(f"      Часть {j}: INLINE_DATA (mime_type: {mime_type}, size: {size} bytes)")
                    else:
                        logger.debug(f"      Часть {j}: НЕИЗВЕСТНЫЙ ТИП ({type(part)})")
                except Exception as log_error:
                    logger.warning(f"⚠️ Ошибка при логгировании части {j}: {log_error}")

        # Конфигурация запроса
        config_kwargs = {
            'system_instruction': f"Сегодня - {datetime.now().strftime('%d.%m.%Y')}",
            'tools': [types.Tool(google_search=types.GoogleSearch())]
        }

        if CURRENT_ROLE_SETTINGS.get('name'):
            instructions_text = CURRENT_ROLE_SETTINGS.get('instructions', '')
            if instructions_text:
                config_kwargs['system_instruction'] += f"\n\n{instructions_text}"

        logger.debug(f"SYSTEM INSTRUCTION для чата {chat_id} (для Gemini):\n{config_kwargs['system_instruction']}")

        # Отправка запроса
        logger.info(f"Отправляем запрос к модели Gemini '{model_id}'...")
        response = client.models.generate_content(
            model=model_id,
            contents=contents,
            config=types.GenerateContentConfig(**config_kwargs)
        )

        # Извлечение ответа
        if hasattr(response, 'text') and response.text:
            gemini_answer = response.text
        elif response.candidates and response.candidates[0].content.parts:
            part = response.candidates[0].content.parts[0]
            gemini_answer = getattr(part, 'text', '') or "Извините, не удалось сформулировать ответ."
        else:
            gemini_answer = "Извините, не удалось сформулировать ответ."

        # Сохраняем историю
        # Сохраняем оригинальный запрос пользователя
        add_to_context(chat_id, 'user', prompt)
        # Сохраняем ответ модели
        add_to_context(chat_id, 'assistant', gemini_answer)

        logger.info(f"Ответ от модели Gemini получен. Длина: {len(gemini_answer)} символов.")
        return gemini_answer

    except Exception as e:
        logger.error(f"Ошибка генерации ответа (Gemini): {e}", exc_info=True)
        return f"❌ Ошибка генерации (Gemini): {str(e)}"
