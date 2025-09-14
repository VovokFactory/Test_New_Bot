from aiogram import Router
from .start_handler import start_router
from .voice_handler import voice_router
from .text_handler import text_router
from .photo_handler import photo_router
from .settings_handler import settings_router
from .model_handler import model_router

def register_handlers(dp: Router) -> None:
    dp.include_router(start_router)
    dp.include_router(settings_router)
    dp.include_router(model_router)
    dp.include_router(voice_router)
    dp.include_router(photo_router)
    dp.include_router(text_router)


