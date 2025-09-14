# bot/handlers/settings_handler.py - aiogram 3.x version
import logging
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from services.context_service import get_voice_mode, toggle_voice_mode, get_context_info

logger = logging.getLogger(__name__)

settings_router = Router()

@settings_router.message(Command('settings'))
async def settings_menu(message: Message):
    """Главное меню настроек"""
    chat_id = message.chat.id
    voice_mode = get_voice_mode(chat_id)
    context_info = get_context_info(chat_id)
    
    voice_status = "🔊 Включен" if voice_mode else "🔇 Выключен"
    
    settings_text = f"""
⚙️ **Настройки бота**

🔊 Режим озвучивания: {voice_status}
💬 Сообщений в контексте: {context_info.get('message_count', 0)}
📝 Токенов использовано: {context_info.get('token_count', 0)}
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🔊 Переключить озвучивание", 
            callback_data="toggle_voice"
        )],
        [InlineKeyboardButton(
            text="🗑 Очистить контекст", 
            callback_data="clear_context"
        )],
        [InlineKeyboardButton(
            text="📊 Статистика", 
            callback_data="show_stats"
        )],
        [InlineKeyboardButton(
            text="❌ Закрыть", 
            callback_data="close_settings"
        )]
    ])
    
    await message.reply(settings_text, reply_markup=keyboard, parse_mode="Markdown")

@settings_router.callback_query(F.data == "toggle_voice")
async def toggle_voice_callback(callback: CallbackQuery):
    """Переключение режима озвучивания"""
    chat_id = callback.message.chat.id
    new_mode = toggle_voice_mode(chat_id)
    
    status = "включен" if new_mode else "выключен"
    await callback.answer(f"🔊 Режим озвучивания {status}")
    
    # Обновляем меню настроек
    await settings_menu(callback.message)

@settings_router.callback_query(F.data == "clear_context")
async def clear_context_callback(callback: CallbackQuery):
    """Очистка контекста"""
    from services.context_service import clear_context
    chat_id = callback.message.chat.id
    clear_context(chat_id)
    
    await callback.answer("🗑 Контекст очищен")
    await settings_menu(callback.message)

@settings_router.callback_query(F.data == "show_stats")
async def show_stats_callback(callback: CallbackQuery):
    """Показать статистику"""
    chat_id = callback.message.chat.id
    context_info = get_context_info(chat_id)
    
    stats_text = f"""
📊 **Статистика чата**

💬 Всего сообщений: {context_info.get('total_messages', 0)}
📝 Токенов использовано: {context_info.get('token_count', 0)}
🕐 Время последнего сообщения: {context_info.get('last_message_time', 'Нет данных')}
🤖 Текущая модель: {context_info.get('current_model', 'Неизвестно')}
"""
    
    await callback.message.edit_text(stats_text, parse_mode="Markdown")
    
    # Кнопка возврата к настройкам
    back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад к настройкам", callback_data="back_to_settings")]
    ])
    await callback.message.edit_reply_markup(reply_markup=back_keyboard)

@settings_router.callback_query(F.data == "back_to_settings")
async def back_to_settings_callback(callback: CallbackQuery):
    """Возврат к меню настроек"""
    await settings_menu(callback.message)

@settings_router.callback_query(F.data == "close_settings")
async def close_settings_callback(callback: CallbackQuery):
    """Закрытие меню настроек"""
    await callback.message.delete()
    await callback.answer("Настройки закрыты")