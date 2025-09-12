# services/gemma_service.py
import logging
from datetime import datetime
from google import genai
from google.genai import types
from config import CURRENT_ROLE_SETTINGS # Импортируем настройки роли
from services.context_service import (
    get_context, add_to_context, get_chat_model,
    is_role_context_initialized, set_role_initialized,
    get_model_limit_for_chat # Импортируем новую функцию для получения лимита

)
from utils.helpers import process_content
logger = logging.getLogger(__name__)

# --- Добавленный код: Функции для работы с длиной контекста ---
def estimate_content_tokens(parts) -> int:
    """
    Очень простая оценка количества токенов в содержимом.
    Это приблизительная оценка. Для точного подсчета нужно использовать
    токенизатор модели.
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
            # Это очень приблизительно и зависит от размера/сложности изображения
            # TODO: Использовать client.models.count_tokens, если возможно
            # Предположим, что данные изображения (bytes) находятся в part.inline_data.data
            # Оценим размер данных. Это не точно, но лучше, чем ничего.
            # Например, 100KB ~= 25600 токенов? Это очень прикидочно.
            # Лучше использовать фиксированное значение или оценку по размеру.
            # Попробуем оценить по размеру байтов. 1 токен ~= 4 байта? Нет, это не так.
            # Лучше использовать фиксированную оценку для изображений.
            total_tokens += 256 # Примерное значение для изображения
    return total_tokens

def truncate_context(context_messages, max_context_tokens, prompt_tokens, image_tokens):
    """
    Обрезает контекст, если общий размер превышает максимальный.
    Удаляет самые старые сообщения.
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
        # Грубая оценка длины сообщения в токенах
        msg_text = msg.get('content', '')
        msg_tokens = len(msg_text) // 4
        context_tokens += msg_tokens

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
        removed_text = removed_msg.get('content', '')
        removed_tokens = len(removed_text) // 4
        total_tokens_needed -= removed_tokens
        logger.debug(f"Удалено сообщение из контекста ({removed_tokens} токенов).")

    if not truncated_context and total_tokens_needed > max_context_tokens:
         # Это маловероятно, но на случай, если даже пустой контекст не помогает
         logger.error("Даже после очистки контекста запрос всё ещё слишком велик.")
         raise ValueError("Запрос слишком велик даже после очистки истории.")

    logger.info(f"Контекст обрезан. Новый размер: ~{total_tokens_needed} токенов.")
    return truncated_context
# --- Конец добавленного кода ---

def _format_gemma_prompt(context_messages, current_user_message_parts, instructions_text=None, knowledge_base_text=None):
    """
    Форматирует промпт для модели Gemma согласно её спецификации.
    Использует <start_of_turn> и <end_of_turn>.
    """
    prompt_parts = []
    # 1. Добавляем инструкции, если они есть, в самом начале как первый пользовательский ввод
    # См. https://ai.google.dev/gemma/docs/core/prompt-structure#system_instructions
    # "Please provide system-level instructions directly in the initial user prompt..."
    if instructions_text:
        # Объединяем инструкции с первым пользовательским сообщением или создаем отдельное сообщение
        system_instruction_part = f"[ИНСТРУКЦИИ РОЛИ]\n{instructions_text}"
        prompt_parts.append(f"<start_of_turn>user\n{system_instruction_part}")
        # Базу знаний, если она есть, добавляем после инструкций в том же сообщении
        if knowledge_base_text:
             kb_part = f"\n[БАЗА ЗНАНИЙ РОЛИ]\n{knowledge_base_text}"
             prompt_parts[-1] += kb_part # Добавляем к последнему (инструкции) элементу
        prompt_parts[-1] += "\n<end_of_turn>" # Завершаем первый пользовательский ход
    else:
        # Если инструкций нет, базу знаний добавляем как первый пользовательский ввод
        if knowledge_base_text:
            kb_part = f"<start_of_turn>user\n[БАЗА ЗНАНИЙ РОЛИ]\n{knowledge_base_text}\n<end_of_turn>"
            prompt_parts.append(kb_part)
        # Если нет ни инструкций, ни базы знаний, ничего не добавляем в начало
    # 2. Добавляем историю контекста
    for msg in context_messages:
        role = msg['role']
        content = msg['content']
        # Gemma поддерживает только 'user' и 'model'
        gemma_role = 'user' if role == 'user' else 'model'
        prompt_parts.append(f"<start_of_turn>{gemma_role}\n{content}\n<end_of_turn>")
    # 3. Добавляем текущее сообщение пользователя
    # Объединяем все части текущего сообщения в одну строку
    current_user_text = ""
    for part in current_user_message_parts:
        if hasattr(part, 'text') and part.text is not None:
            current_user_text += part.text
        # Изображения и другие данные могут требовать специальной обработки
        # Пока предполагаем, что они уже в правильном формате для Contents
        # и будут добавлены отдельно в generate_content
    if current_user_text: # Добавляем только если есть текст
        prompt_parts.append(f"<start_of_turn>user\n{current_user_text}")
    # 4. Добавляем начало хода модели, чтобы модель знала, что нужно продолжить
    prompt_parts.append("<start_of_turn>model")
    # 5. Объединяем все части в один промпт
    full_prompt = "".join(prompt_parts)
    logger.debug(f"Сформированный промпт для Gemma:\n{full_prompt}")
    return full_prompt

def generate_response_gemma(chat_id: int, prompt: str, image_bytes: bytes = None) -> str:
    """
    Генерация ответа с помощью модели Gemma через Gemini API.
    Args:
        chat_id: ID чата
        prompt: Текст запроса
        image_bytes: Байты изображения (опционально)
    Returns:
        str: Ответ от модели
    """
    try:
        model_id = get_chat_model(chat_id)
        client = genai.Client()
        
        # --- Добавленный код: Проверка длины контекста ---
        # 1. Получить лимит контекста для модели этого чата (из кэша или с запросом)
        max_context_length = get_model_limit_for_chat(chat_id)
        logger.debug(f"Максимальная длина контекста для чата {chat_id} (модель '{model_id}'): {max_context_length}")

        # 2. Подготовить текущий ввод для оценки его размера
        # current_parts_for_estimation = [types.Part(text=prompt)] # Уже не нужно, сразу оцениваем
        # if image_bytes:
        #     current_parts_for_estimation.append(types.Part(
        #         inline_data=types.Blob(mime_type='image/jpeg', data=image_bytes)
        #     ))

        # 3. Оценить размер токенов в новом сообщении
        estimated_prompt_tokens = estimate_content_tokens([types.Part(text=prompt)])
        estimated_image_tokens = estimate_content_tokens([types.Part(inline_data=types.Blob(mime_type='image/jpeg', data=image_bytes))]) if image_bytes else 0
        logger.debug(f"Оценка токенов: Prompt={estimated_prompt_tokens}, Image={estimated_image_tokens}")

        # 4. Получить текущий контекст
        context_messages = get_context(chat_id)
        logger.debug(f"Получено {len(context_messages)} сообщений из контекста.")

        # 5. Попытка обрезать контекст, если необходимо
        try:
            # Обрезаем контекст, если нужно, или выбрасываем исключение, если новое сообщение слишком велико
            truncated_context_messages = truncate_context(
                context_messages, 
                max_context_length, 
                estimated_prompt_tokens, 
                estimated_image_tokens
            )
            # Если truncate_context не выбросило исключение, значит всё в порядке или контекст обрезан
            context_messages = truncated_context_messages
            logger.debug(f"Контекст после обрезки: {len(context_messages)} сообщений.")
        except ValueError as ve:
            # Это означает, что новое сообщение слишком велико или ошибка после обрезки
            logger.error(f"Ошибка длины контекста: {ve}")
            return f"❌ {str(ve)}" # Возвращаем сообщение пользователю
        # --- Конец добавленного кода ---

        # --- Подготовка данных для промпта ---
        # 1. Получаем контекст (уже обрезанный)
        # context_messages = get_context(chat_id) # Уже получили выше
        # 2. Подготавливаем текущий ввод
        current_parts = [types.Part(text=prompt)]
        if image_bytes:
            # Используем Blob для передачи изображения
            image_part = types.Part(
                inline_data=types.Blob(
                    mime_type='image/jpeg', # Уточните MIME-тип, если он другой
                    data=image_bytes
                )
            )
            current_parts.append(image_part)
        # 3. Получаем настройки роли
        instructions_text = None
        knowledge_base_text = None
        if CURRENT_ROLE_SETTINGS.get('name'):
            logger.info(f"Используется роль: {CURRENT_ROLE_SETTINGS['name']} для модели Gemma")
            instructions_text = CURRENT_ROLE_SETTINGS.get('instructions')
            knowledge_base_text = CURRENT_ROLE_SETTINGS.get('knowledge_base')
            # Инициализация (добавление KB к первому запросу)
            if not is_role_context_initialized(chat_id):
                 logger.info(f"Инициализируем контекст для роли '{CURRENT_ROLE_SETTINGS['name']}' в чате {chat_id} (Gemma)")
                 # Помечаем инициализацию
                 set_role_initialized(chat_id)
                 # База знаний будет добавлена в промпт ниже
        else:
            logger.info("Используется стандартный режим для модели Gemma.")
        # --- Формирование промпта и contents ---
        # Для Gemma мы формируем специальный текстовый промпт
        # и передаем его как одну текстовую часть в Contents
        gemma_prompt = _format_gemma_prompt(
            context_messages, 
            current_parts, # Передаем все части, чтобы _format мог обработать текст
            instructions_text, 
            knowledge_base_text
        )
        # Contents для Gemma будет содержать:
        # 1. Сформированный текстовый промпт
        # 2. Опционально, изображение (если оно было)
        gemma_contents = [types.Part(text=gemma_prompt)]
        # Добавляем изображение, если оно было (оно не попадет в текстовый промпт)
        if image_bytes:
            # Убираем текстовую часть с промптом, если есть изображение,
            # и передаем промпт и изображение отдельно
            # См. примеры в https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api
            # Нужно передать и текст, и изображение в parts
            # Но промпт уже содержит текст, а изображение - отдельно.
            # Лучше передать промпт как текст, а изображение как отдельную часть.
            # Но API ожидает список parts. 
            # Давайте пересоздадим contents.
            gemma_contents = [types.Part(text=gemma_prompt)]
            if image_bytes:
                 # Добавляем изображение как отдельную часть
                 image_part = types.Part(
                    inline_data=types.Blob(
                        mime_type='image/jpeg',
                        data=image_bytes
                    )
                 )
                 gemma_contents.append(image_part) # Промпт + изображение
        # --- Подготовка конфигурации ---
        # ВАЖНО: Модели Gemma НЕ поддерживают system_instruction и tools!
        # См. https://ai.google.dev/gemma/docs/core/prompt-structure#unsupported_features
        config_kwargs = {
            # 'system_instruction' НЕ используется
            # 'tools' НЕ используется
            # Можно добавить другие параметры, если они поддерживаются
            # Например, температура, top_p и т.д.
        }
        # --- Генерация ответа ---
        logger.info(f"Отправляем запрос к модели Gemma '{model_id}'...")
        response = client.models.generate_content(
            model=model_id,
            contents=gemma_contents, # Передаем сформированные contents
            config=types.GenerateContentConfig(**config_kwargs)
        )
        # --- Обработка ответа ---
        try:
            if hasattr(response, 'text') and response.text is not None:
                gemma_raw_answer = response.text.strip()
            elif (
                hasattr(response, 'candidates') and response.candidates and
                hasattr(response.candidates[0], 'content') and
                response.candidates[0].content and
                hasattr(response.candidates[0].content, 'parts') and
                response.candidates[0].content.parts and
                response.candidates[0].content.parts[0].text is not None
            ):
                gemma_raw_answer = response.candidates[0].content.parts[0].text.strip()
            else:
                gemma_raw_answer = "Извините, не удалось сформулировать ответ (пустой ответ от модели Gemma)."
                logger.warning("Gemma вернула пустой или некорректный ответ.")
        except Exception as e:
            gemma_raw_answer = "Произошла ошибка при обработке ответа модели Gemma."
            logger.exception(f"Ошибка при извлечении текста из ответа Gemma: {e}")
        # === ДОБАВИТЬ ЭТИ СТРОКИ ===
        # Очищаем ответ перед отправкой пользователю
        import re
        # Создаем копию для пользователя, очищенную от тегов
        gemma_clean_answer = gemma_raw_answer
        # Удаляем все вхождения полных блоков тегов (<start_of_turn>...<end_of_turn>)
        gemma_clean_answer = re.sub(r"<start_of_turn>.*?<end_of_turn>\s*", "", gemma_clean_answer, flags=re.DOTALL)
        # На случай, если остались отдельные теги (например, <start_of_turn>model в конце промпта)
        gemma_clean_answer = gemma_clean_answer.replace("<start_of_turn>", "").replace("<end_of_turn>", "")
        # Также можно удалить возможные артефакты, например, "user\n" или "model\n" в начале/конце
        gemma_clean_answer = gemma_clean_answer.strip()
        # ===========================
        logger.info(f"Ответ от модели Gemma получен. Длина (сырого): {len(gemma_raw_answer)} символов.")
        # --- Сохранение в контекст ---
        # Сохраняем оригинальный запрос пользователя (без тегов)
        add_to_context(chat_id, 'user', prompt)
        # Сохраняем СЫРОЙ ответ модели (с тегами) в контекст, так как _format_gemma_prompt ожидает их
        add_to_context(chat_id, 'assistant', gemma_raw_answer) # <-- Сохраняем с тегами
        # Возвращаем ОЧИЩЕННЫЙ ответ пользователю
        return gemma_clean_answer # <-- Возвращаем без тегов
    except Exception as e:
        logger.error(f"Ошибка генерации ответа моделью Gemma: {e}", exc_info=True)
        return f"❌ Ошибка генерации (Gemma): {str(e)}"
