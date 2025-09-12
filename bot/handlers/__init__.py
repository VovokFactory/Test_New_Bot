# bot/handlers/__init__.py
from .start_handler import register_start_handler
from .voice_handler import register_voice_handler
from .text_handler import register_text_handler
from .photo_handler import register_photo_handler
from .settings_handler import register_settings_handlers
from .model_handler import register_model_handlers

def register_handlers(bot):
    """Регистрация всех обработчиков"""
    # 1. Сначала регистрируем обработчики команд (специфичные)
    register_start_handler(bot)      # /start
    register_settings_handlers(bot)  # /help, /clear, /settings, /set_history, /set_context_ttl
    register_model_handlers(bot)     # /chm, callbacks
    # 2. Затем регистрируем обработчики команд, которые могут быть в других хендлерах (если есть)
    #    В данном случае /voice_toggle находится в start_handler, что тоже ок.
    # 3. И только потом - обработчики с общими фильтрами
    register_voice_handler(bot)      # голос (content_types=['voice'])
    register_photo_handler(bot)      # фото (content_types=['photo'])
    register_text_handler(bot)       # ВСЕ остальные тексты (content_types=['text'])
