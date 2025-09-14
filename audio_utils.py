# audio_utils.py - aiogram 3.x version
import os
import tempfile
import logging
import time
import wave
import asyncio
from pydub import AudioSegment
from google import genai
from google.genai import types
from config import TRANSCRIPTION_MODEL, TRANSCRIPTION_PROMPT
from dotenv import load_dotenv

load_dotenv()

# Настройка основного логгера
logger = logging.getLogger('audio_utils')
logger.setLevel(logging.INFO)
if not logger.handlers:
    console_handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

# Настройка отдельного логгера для времени обработки
proc_time_logger = logging.getLogger('processing_time')
proc_time_logger.setLevel(logging.INFO)
if not proc_time_logger.handlers:
    proc_time_handler = logging.FileHandler("processing_time.log", encoding="utf-8")
    proc_time_formatter = logging.Formatter('%(asctime)s - %(message)s')
    proc_time_handler.setFormatter(proc_time_formatter)
    proc_time_logger.addHandler(proc_time_handler)
    proc_time_logger.propagate = False

def get_audio_duration(ogg_file_path):
    """Определяет длительность аудиофайла в секундах"""
    try:
        audio = AudioSegment.from_ogg(ogg_file_path)
        duration_seconds = len(audio) / 1000
        return duration_seconds
    except Exception as e:
        logger.error(f"Ошибка определения длительности: {str(e)}")
        return 0

def transcribe_with_gemini_sync(ogg_file_path, api_key, model_version=None, prompt=None):
    """
    Транскрибация аудио с использованием Gemini API.
    
    Args:
        ogg_file_path (str): Путь к OGG файлу.
        api_key (str): API ключ Google.
        model_version (str, optional): Версия модели для транскрибации.
        prompt (str, optional): Промт для транскрибации.
    
    Returns:
        str: Текст транскрибации или сообщение об ошибке.
    """
    start_time = time.time()
    try:
        model_to_use = model_version if model_version else TRANSCRIPTION_MODEL
        prompt_to_use = prompt if prompt else TRANSCRIPTION_PROMPT
        
        logger.info(f"Начинаю транскрибацию через Gemini API модель {model_to_use}")
        
        # Инициализируем клиент
        client = genai.Client(api_key=api_key)
        
        # Загружаем аудиофайл в Gemini
        logger.info(f"Загружаю аудиофайл: {ogg_file_path}")
        uploaded_file = client.files.upload(file=ogg_file_path)
        logger.info(f"Файл загружен: {uploaded_file.display_name}")
        
        # Формируем и отправляем запрос на транскрибацию
        logger.info("Отправляю запрос на транскрибацию...")
        response = client.models.generate_content(
            model=model_to_use,
            contents=[prompt_to_use, uploaded_file]
        )
        
        # Получаем текст результата
        if hasattr(response, 'text'):
            transcription = response.text.strip()
            logger.info(f"Транскрибация завершена. Длина текста: {len(transcription)} символов")
        elif response.candidates and response.candidates[0].content.parts:
            transcription = response.candidates[0].content.parts[0].text.strip()
            logger.info(f"Транскрибация завершена (альтернативный метод). Длина текста: {len(transcription)} символов")
        else:
            logger.error("Не удалось извлечь текст транскрибации из ответа API")
            transcription = "❌ Не удалось извлечь текст транскрибации из ответа Gemini API."
        
        return transcription
        
    except Exception as e:
        logger.error(f"Ошибка транскрибации через Gemini API: {e}", exc_info=True)
        return f"❌ Ошибка транскрибации: {str(e)}"
    finally:
        # Логируем время обработки
        elapsed_time = time.time() - start_time
        try:
            duration = get_audio_duration(ogg_file_path) if os.path.exists(ogg_file_path) else 0
            proc_time_logger.info(f"Метод: Gemini API, Длительность аудио: {duration:.2f} секунд, Время обработки: {elapsed_time:.2f} секунд")
        except:
            pass

async def transcribe_with_gemini(ogg_file_path, api_key, model_version=None, prompt=None):
    """Асинхронная обертка для транскрибации"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        transcribe_with_gemini_sync,
        ogg_file_path,
        api_key,
        model_version,
        prompt
    )

async def process_voice_message(bot, message, api_key: str):
    """
    Асинхронная обработка голосового сообщения для aiogram 3.x
    """
    start_time = time.time()
    ogg_filename = None
    
    try:
        logger.info("Начинаю загрузку голосового сообщения...")
        download_start_time = time.time()
        
        # Получаем информацию о файле
        file_info = await bot.get_file(message.voice.file_id)
        
        # Скачиваем файл
        file_bytes = await bot.download_file(file_info.file_path)
        
        download_end_time = time.time()
        logger.info(f"Голосовое сообщение загружено за {download_end_time - download_start_time:.2f} секунд.")
        
        # Сохранение во временный файл
        save_start_time = time.time()
        with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as tmp_file:
            tmp_file.write(file_bytes.read() if hasattr(file_bytes, 'read') else file_bytes)
            ogg_filename = tmp_file.name
        
        save_end_time = time.time()
        logger.info(f"Аудио сохранено во временный файл {ogg_filename} за {save_end_time - save_start_time:.2f} секунд.")
        
        # Определяем длительность аудио
        duration = get_audio_duration(ogg_filename)
        logger.info(f"Длительность аудио: {duration:.2f} секунд")
        
        # Транскрибация через Gemini API
        logger.info("Используется метод транскрибации через Gemini API")
        transcribe_start_time = time.time()
        text = await transcribe_with_gemini(ogg_filename, api_key)
        transcribe_end_time = time.time()
        logger.info(f"Транскрибация завершена за {transcribe_end_time - transcribe_start_time:.2f} секунд.")
        
        return text
        
    except Exception as e:
        logger.error(f"Ошибка обработки голосового сообщения: {e}", exc_info=True)
        return f"❌ Ошибка обработки голосового сообщения: {str(e)}"
    finally:
        # Удаление временных файлов
        if ogg_filename and os.path.exists(ogg_filename):
            try:
                os.remove(ogg_filename)
                logger.info(f"Временный файл {ogg_filename} удален.")
            except Exception as e:
                logger.warning(f"Не удалось удалить временный файл {ogg_filename}: {e}")
        
        total_elapsed_time = time.time() - start_time
        proc_time_logger.info(f"Метод: process_voice_message, Общая длительность: {total_elapsed_time:.2f} секунд")

async def generate_audio_to_opus(text: str, model_version: str, api_key: str) -> tuple[bool, str]:
    """Генерация аудио в формате OPUS для Telegram"""
    try:
        logger.info(f"Генерирую аудио для текста: {text[:50]}...")
        client = genai.Client(api_key=api_key)
        
        # Правильный формат запроса для google-genai
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=model_version,
            contents=text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name='Sulafat',
                        )
                    ),
                )
            )
        )
        
        logger.info("Получен ответ от Gemini")
        
        # Проверяем наличие данных в ответе
        if not response.candidates:
            logger.error("No candidates in response")
            return (False, "No candidates in response")
        
        candidate = response.candidates[0]
        logger.info(f"Candidate: {candidate}")
        
        # Извлекаем аудио данные из ответа
        audio_data = None
        if hasattr(candidate, 'content') and candidate.content.parts:
            for part in candidate.content.parts:
                if hasattr(part, 'inline_data') and part.inline_data:
                    audio_data = part.inline_data.data
                    break
        
        if not audio_data:
            logger.error("No inline data found in response parts")
            return (False, "No inline data found in response parts")
        
        logger.info(f"Получены аудиоданные: {len(audio_data)} байт")
        
        # Создаем временный WAV файл
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_wav:
            wav_filename = tmp_wav.name
        
        # Сохраняем PCM в WAV
        with wave.open(wav_filename, 'wb') as wf:
            wf.setnchannels(1)  # моно
            wf.setsampwidth(2)  # 2 байта (16 бит)
            wf.setframerate(24000)  # частота дискретизации
            wf.writeframes(audio_data)
        
        logger.info(f"Создан WAV файл: {wav_filename} ({os.path.getsize(wav_filename)} байт)")
        
        # Конвертируем WAV в OPUS
        opus_filename = wav_filename.replace('.wav', '.opus')
        audio = AudioSegment.from_wav(wav_filename)
        
        # Оптимальные параметры для Telegram
        audio.export(
            opus_filename,
            format='opus',
            codec='libopus',
            bitrate='64k',
            parameters=["-ar", "48000", "-ac", "1"]
        )
        
        # Удаляем временный WAV файл
        os.unlink(wav_filename)
        
        logger.info(f"Создан OPUS файл: {opus_filename} ({os.path.getsize(opus_filename)} байт)")
        
        return (True, opus_filename)
        
    except Exception as e:
        logger.exception(f"Ошибка в generate_audio_to_opus: {str(e)}")
        return (False, str(e))