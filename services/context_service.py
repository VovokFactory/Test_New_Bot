# services/context_service.py
import logging
from collections import defaultdict
from datetime import datetime, timedelta
# Импортируем DEFAULT_MODEL и функции из mod_llm
from mod_llm import DEFAULT_MODEL, get_model_info

from config import MAX_HISTORY, CONTEXT_TIMEOUT
# Импортируем новые модели данных
from models.chat_models import ChatMessage, ChatSettings

logger = logging.getLogger(__name__)

# --- Обновлённые хранилища ---
# chat_contexts теперь будет хранить ChatContext напрямую, если вы перейдёте на это полностью
# Пока оставим как есть для совместимости, но можно обновить
chat_contexts = defaultdict(list) 

# chat_settings теперь будет хранить экземпляры ChatSettings
# chat_settings = defaultdict(dict) # Устаревшее
chat_settings: defaultdict[int, ChatSettings] = defaultdict(ChatSettings)

# chat_models теперь не нужно, так как модель хранится в chat_settings
# chat_models = defaultdict(lambda: DEFAULT_MODEL) # Устаревшее

# voice_states можно тоже перенести в ChatSettings, но пока оставим отдельно
voice_states = defaultdict(bool)  # Словарь для отслеживания режима дублирования
# --- Конец обновлённых хранилищ ---

# --- Обновлённые функции для работы с настройками ---
def get_chat_settings(chat_id: int) -> ChatSettings:
    """Получение настроек чата"""
    # defaultdict автоматически создаст ChatSettings() при первом обращении
    return chat_settings[chat_id] 

def set_max_history(chat_id: int, value: int):
    """Установка максимальной глубины истории"""
    chat_settings[chat_id].max_history = value

def set_context_ttl(chat_id: int, value: int):
    """Установка времени жизни контекста"""
    chat_settings[chat_id].context_ttl = value

def set_role_initialized(chat_id: int):
    """Помечает, что контекст для роли в этом чате инициализирован"""
    # Предположим, это состояние будет храниться в chat_settings
    # Можно добавить специальное поле, например, в словарь внутри settings
    # Для простоты, пока оставим как есть, или добавим в ChatSettings нужное поле
    # chat_settings[chat_id].role_initialized = True
    # Пока используем старый способ для совместимости
    chat_settings[chat_id].__dict__['role_initialized'] = True

def is_role_context_initialized(chat_id: int) -> bool:
    """Проверяет, был ли инициализирован контекст для роли в этом чате"""
    # return chat_settings[chat_id].role_initialized # Если добавили в ChatSettings
    # Пока используем старый способ для совместимости
    return chat_settings[chat_id].__dict__.get('role_initialized', False)

# --- Обновлённые функции для работы с моделью ---
def get_chat_model_info(chat_id: int) -> dict:
    """
    Получение информации о модели для конкретного чата.
    Возвращает словарь с информацией о модели.
    """
    return chat_settings[chat_id].current_model

def get_chat_model(chat_id: int) -> str:
    """
    Получение ID модели для конкретного чата.
    (Совместимость со старым API)
    """
    return chat_settings[chat_id].current_model.get("id", DEFAULT_MODEL)

def set_chat_model(chat_id: int, model_id: str):
    """
    Установка модели для конкретного чата.
    """
    # 1. Получаем полную информацию о модели из mod_llm
    model_info = get_model_info(model_id)
    
    if model_info:
        # 2. Обновляем информацию в настройках чата
        # Это копирует все поля из model_info в current_model чата
        # Делаем копию, чтобы не мутировать оригинальный словарь из MODELS
        chat_settings[chat_id].current_model = model_info.copy()
        logger.info(f"Модель для чата {chat_id} установлена на '{model_id}'")
    else:
        logger.warning(f"Попытка установить неизвестную модель '{model_id}' для чата {chat_id}. Используется DEFAULT_MODEL.")
        # Устанавливаем модель по умолчанию
        default_model_info = get_model_info(DEFAULT_MODEL)
        if default_model_info:
            chat_settings[chat_id].current_model = default_model_info.copy()
        else:
            # На всякий случай, если DEFAULT_MODEL тоже не найден
            chat_settings[chat_id].current_model = {"id": DEFAULT_MODEL}

# --- Функции для работы с голосом ---
def get_voice_mode(chat_id: int) -> bool:
    """Получение состояния голосового режима"""
    return chat_settings[chat_id].voice_mode

def toggle_voice_mode(chat_id: int) -> bool:
    """Переключение голосового режима"""
    chat_settings[chat_id].voice_mode = not chat_settings[chat_id].voice_mode
    return chat_settings[chat_id].voice_mode
# --- Конец обновлённых функций для работы с голосом ---

# --- Остальные функции (get_context, add_to_context, clear_chat_history) ---
# Эти функции в основном работают с chat_contexts и напрямую не затрагивают модель.
# Их можно оставить без изменений, если вы не переносите контекст в ChatContext.
# ... (оставляем их как есть) ...
def get_context(chat_id: int) -> list:
    """
    Получение контекста диалога для чата с учетом настроек
    
    Args:
        chat_id: ID чата
    
    Returns:
        list: Отфильтрованный контекст
    """
    # Инициализируем пустой список если chat_id отсутствует
    if chat_id not in chat_contexts:
        chat_contexts[chat_id] = []
    
    now = datetime.now()
    settings = chat_settings[chat_id] # Получаем ChatSettings
    max_history = settings.max_history # Берем из объекта
    context_ttl = settings.context_ttl # Берем из объекта
    
    # Фильтруем сообщения по времени и ограничению истории
    filtered_context = [
        m for m in chat_contexts[chat_id]
        if now - m['timestamp'] < timedelta(seconds=context_ttl)
    ]
    
    # Возвращаем последние max_history сообщений
    return filtered_context[-max_history:] if max_history else filtered_context

def add_to_context(chat_id: int, role: str, content: str):
    """
    Добавление сообщения в контекст диалога
    
    Args:
        chat_id: ID чата
        role: Роль (user/assistant)
        content: Содержание сообщения
    """
    # Инициализируем пустой список если chat_id отсутствует
    if chat_id not in chat_contexts:
        chat_contexts[chat_id] = []
    
    # Добавляем сообщение с текущим временем
    chat_contexts[chat_id].append({
        'role': role,
        'content': content,
        'timestamp': datetime.now(),
    })

def clear_chat_history(chat_id: int):
    """Очистка истории диалога для чата"""
    chat_contexts[chat_id] = []
# --- Конец остальных функций ---

# --- Обновлённая функция для получения лимита модели ---
def get_model_limit_for_chat(chat_id: int) -> int:
    """
    Получает лимит контекста для модели, назначенной конкретному чату,
    из локальной конфигурации, хранящейся в настройках чата.
    """
    # Получаем информацию о модели прямо из настроек чата
    model_info = get_chat_model_info(chat_id)
    
    # Извлекаем лимит
    limit = model_info.get('input_token_limit')
    
    if limit is not None:
        logger.debug(f"Лимит контекста для чата {chat_id} (модель {model_info.get('id')}): {limit} (из настроек чата)")
        return limit
    else:
        # Если лимит не найден в информации о модели (что странно, если она из mod_llm)
        logger.warning(f"Лимит контекста для модели '{model_info.get('id')}' не найден в информации о модели. Используется значение по умолчанию.")
        default_limit = 32768
        return default_limit
# --- Конец обновлённой функции для получения лимита модели ---