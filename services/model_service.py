# services/model_service.py
"""Нейтральная точка входа для генерации ответов моделью."""
import logging
from mod_llm import get_model_family

logger = logging.getLogger(__name__)

def generate_model_response(chat_id: int, prompt: str, image_bytes: bytes = None) -> str:
    """
    Генерация ответа. Выбирает правильный сервис в зависимости от модели.
    
    Args:
        chat_id: ID чата
        prompt: Текст запроса
        image_bytes: Байты изображения (опционально)
    
    Returns:
        str: Ответ от модели
    """
    # Определяем семейство модели
    from services.context_service import get_chat_model # Импортируем тут, чтобы избежать циклических импортов на этапе определения модуля
    model_id = get_chat_model(chat_id)
    model_family = get_model_family(model_id)
    
    logger.info(f"Выбрана модель '{model_id}' семейства '{model_family}' для генерации ответа.")
    
    if model_family == "gemma":
        # Импортируем здесь, чтобы избежать потенциальных проблем и циклических зависимостей
        from services.gemma_service import generate_response_gemma
        logger.debug("Вызов generate_response_gemma...")
        return generate_response_gemma(chat_id, prompt, image_bytes)
    elif model_family == "gemini":
        # Импортируем специфичный сервис для Gemini
        from services.gemini_service import generate_response_gemini
        logger.debug("Вызов generate_response_gemini...")
        return generate_response_gemini(chat_id, prompt, image_bytes)
    elif model_family == "openrouter":
        # Импортируем специфичный сервис для OpenRouter
        from services.openrouter_service import generate_response_openrouter
        logger.debug("Вызов generate_response_openrouter...")
        return generate_response_openrouter(chat_id, prompt, image_bytes)
    elif model_family == "groq": # <-- Добавлено
        from services.groq_service import generate_response_groq
        logger.debug("Вызов generate_response_groq...")
        return generate_response_groq(chat_id, prompt, image_bytes) # <-- Добавлено

    else:
        error_msg = f"❌ Неподдерживаемое семейство моделей: {model_family} (модель: {model_id})"
        logger.error(error_msg)
        return error_msg
