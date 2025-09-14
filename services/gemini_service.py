# services/gemini_service.py
"""Сервис для генерации ответов моделями семейства Gemini."""
import logging
from google import genai
from google.genai import types
from services.context_service import (
    get_context, add_to_context, get_chat_model,
    get_model_limit_for_chat,
)

logger = logging.getLogger(__name__)

def normalize_role(role: str) -> str:
    if not role:
        return "user"
    r = str(role).lower()
    if r in ("assistant", "model"):
        return "model"
    if r in ("system",):
        return "user"
    if r == "user":
        return "user"
    return "user"

def estimate_content_tokens(parts) -> int:
    total = 0
    for part in parts:
        if getattr(part, "text", None):
            total += len(part.text) // 4
        elif getattr(part, "inline_data", None) and getattr(part.inline_data, "data", None):
            total += 256
    return total

def truncate_context(context_messages: list[types.Content],
                     max_ctx_tokens: int,
                     prompt_tokens: int,
                     image_tokens: int) -> list[types.Content]:
    if not context_messages:
        return context_messages

    current_req = prompt_tokens + image_tokens
    if current_req > max_ctx_tokens:
        raise ValueError("Ваш запрос (включая изображение) слишком велик для обработки моделью.")

    ctx_tokens = 0
    for msg in context_messages:
        for part in msg.parts:
            if getattr(part, "text", None):
                ctx_tokens += len(part.text) // 4
            elif getattr(part, "inline_data", None) and getattr(part.inline_data, "data", None):
                ctx_tokens += 256

    total_needed = ctx_tokens + current_req
    if total_needed <= max_ctx_tokens:
        return context_messages

    truncated = list(context_messages)
    while truncated and total_needed > max_ctx_tokens:
        removed = truncated.pop(0)
        removed_tokens = 0
        for part in removed.parts:
            if getattr(part, "text", None):
                removed_tokens += len(part.text) // 4
            elif getattr(part, "inline_data", None) and getattr(part.inline_data, "data", None):
                removed_tokens += 256
        total_needed -= removed_tokens
    return truncated

def generate_response_gemini(chat_id: int, prompt: str, image_bytes: bytes | None = None) -> str:
    """
    Синхронная генерация ответа для семейства Gemini.
    Вызов из async‑кода выполнять через asyncio.to_thread(...).
    """
    try:
        model_id = get_chat_model(chat_id)
        client = genai.Client()

        prompt_str = "" if prompt is None else str(prompt)

        # parts пользователя
        user_parts: list[types.Part] = [types.Part.from_text(text=prompt_str)]
        image_tokens = 0

        # Жёсткая проверка типа для картинки: только bytes; иначе не добавляем
        if isinstance(image_bytes, (bytes, bytearray)) and len(image_bytes) > 0:
            try:
                img_part = types.Part.from_bytes(data=bytes(image_bytes), mime_type="image/jpeg")
            except Exception:
                img_part = types.Part(inline_data=types.Blob(data=bytes(image_bytes), mime_type="image/jpeg"))
            user_parts.append(img_part)
            image_tokens = 256

        # Исторический контекст -> только роли 'user' и 'model'
        history = get_context(chat_id)  # [{'role','content','timestamp'}, ...]
        ctx_contents: list[types.Content] = []
        for m in history:
            role_norm = normalize_role(m.get("role", "user"))
            content_text = str(m.get("content", ""))
            ctx_contents.append(
                types.Content(role=role_norm, parts=[types.Part.from_text(text=content_text)])
            )

        max_ctx_tokens = get_model_limit_for_chat(chat_id)
        prompt_tokens = len(prompt_str) // 4

        trimmed_ctx = truncate_context(ctx_contents, max_ctx_tokens, prompt_tokens, image_tokens)

        contents: list[types.Content] = []
        contents.extend(trimmed_ctx)
        contents.append(types.Content(role="user", parts=user_parts))

        resp = client.models.generate_content(
            model=model_id,
            contents=contents
        )

        # Обновляем контекст (ответ хранить как 'model' для совместимости)
        add_to_context(chat_id, "user", prompt_str)

        text_out = ""
        if getattr(resp, "text", None):
            text_out = resp.text.strip()
        elif getattr(resp, "candidates", None):
            cand = resp.candidates
            if cand and cand.content and cand.content.parts:
                first_part = cand.content.parts
                if getattr(first_part, "text", None):
                    text_out = first_part.text.strip()
                else:
                    text_out = "✅ Ответ получен, но без текстовой части."
            else:
                text_out = "❌ Не удалось получить текст из ответа модели."
        else:
            text_out = "❌ Не удалось получить текст из ответа модели."

        add_to_context(chat_id, "model", text_out)
        return text_out

    except Exception as e:
        logger.error(f"Ошибка генерации ответа (Gemini): {e}", exc_info=True)
        return f"❌ Ошибка генерации ответа: {e}"

