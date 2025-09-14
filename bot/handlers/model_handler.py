# bot/handlers/model_handler.py - aiogram 3.x version
import logging
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from services.context_service import get_chat_model, set_chat_model
from mod_llm import MODELS, get_model_info

logger = logging.getLogger(__name__)

model_router = Router()

@model_router.message(Command('model'))
async def model_menu(message: Message):
    """Меню выбора модели"""
    chat_id = message.chat.id
    current_model = get_chat_model(chat_id)
    current_model_info = get_model_info(current_model)
    
    model_text = f"""
🤖 **Управление моделями ИИ**

📋 Текущая модель: **{current_model_info['name'] if current_model_info else 'Неизвестно'}**
🔧 ID модели: `{current_model}`

Выберите новую модель из списка ниже:
"""
    
    # Создаем кнопки для каждого семейства моделей
    keyboard_buttons = []
    
    # Группируем модели по семействам
    families = {}
    for model in MODELS:
        family = model['family']
        if family not in families:
            families[family] = []
        families[family].append(model)
    
    # Создаем кнопки для каждого семейства
    for family_name, family_models in families.items():
        family_display = {
            'gemini': '🔮 Gemini',
            'gemma': '💎 Gemma', 
            'openrouter': '🌐 OpenRouter',
            'groq': '⚡ Groq'
        }.get(family_name, f'🤖 {family_name.title()}')
        
        keyboard_buttons.append([InlineKeyboardButton(
            text=family_display,
            callback_data=f"family_{family_name}"
        )])
    
    # Добавляем кнопку закрытия
    keyboard_buttons.append([InlineKeyboardButton(
        text="❌ Закрыть",
        callback_data="close_model_menu"
    )])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await message.reply(model_text, reply_markup=keyboard, parse_mode="Markdown")

@model_router.callback_query(F.data.startswith("family_"))
async def show_family_models(callback: CallbackQuery):
    """Показать модели определенного семейства"""
    family_name = callback.data.split("_")[1]
    
    # Фильтруем модели по семейству
    family_models = [model for model in MODELS if model['family'] == family_name]
    
    if not family_models:
        await callback.answer("❌ Модели не найдены")
        return
    
    family_display = {
        'gemini': '🔮 Gemini',
        'gemma': '💎 Gemma',
        'openrouter': '🌐 OpenRouter', 
        'groq': '⚡ Groq'
    }.get(family_name, f'🤖 {family_name.title()}')
    
    models_text = f"**{family_display} Модели:**\n\n"
    
    keyboard_buttons = []
    
    for model in family_models:
        # Добавляем информацию о модели в текст
        models_text += f"• **{model['name']}**\n"
        models_text += f"  📝 {model['description']}\n"
        models_text += f"  🎯 Лимит: {model['FreeRPD']} RPD\n"
        if model.get('audio_support'):
            models_text += f"  🎵 Поддержка аудио: ✅\n"
        models_text += "\n"
        
        # Создаем кнопку для выбора модели
        keyboard_buttons.append([InlineKeyboardButton(
            text=f"✅ {model['name'][:30]}...",
            callback_data=f"select_{model['id'][:50]}"  # Ограничиваем длину callback_data
        )])
    
    # Кнопка возврата
    keyboard_buttons.append([InlineKeyboardButton(
        text="⬅️ Назад к семействам",
        callback_data="back_to_families"
    )])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await callback.message.edit_text(models_text, reply_markup=keyboard, parse_mode="Markdown")

@model_router.callback_query(F.data.startswith("select_"))
async def select_model(callback: CallbackQuery):
    """Выбор конкретной модели"""
    model_id = callback.data[7:]  # Убираем "select_"
    chat_id = callback.message.chat.id
    
    # Ищем модель по ID
    selected_model = get_model_info(model_id)
    
    if not selected_model:
        await callback.answer("❌ Модель не найдена")
        return
    
    # Устанавливаем новую модель для чата
    set_chat_model(chat_id, model_id)
    
    await callback.answer(f"✅ Выбрана модель: {selected_model['name']}")
    
    # Показываем подтверждение
    success_text = f"""
✅ **Модель успешно изменена!**

🤖 Новая модель: **{selected_model['name']}**
🔧 ID: `{model_id}`
📝 Описание: {selected_model['description']}
🎯 Лимит: {selected_model['FreeRPD']} RPD
🎵 Аудио: {'✅' if selected_model.get('audio_support') else '❌'}

Теперь все ответы будут генерироваться с помощью этой модели.
"""
    
    # Кнопка закрытия
    close_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="close_model_menu")]
    ])
    
    await callback.message.edit_text(success_text, reply_markup=close_keyboard, parse_mode="Markdown")

@model_router.callback_query(F.data == "back_to_families")
async def back_to_families(callback: CallbackQuery):
    """Возврат к выбору семейств"""
    await model_menu(callback.message)

@model_router.callback_query(F.data == "close_model_menu")
async def close_model_menu(callback: CallbackQuery):
    """Закрытие меню моделей"""
    await callback.message.delete()
    await callback.answer("Меню моделей закрыто")