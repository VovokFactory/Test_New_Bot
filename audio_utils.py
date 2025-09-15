# audio_utils.py
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

logger = logging.getLogger('audio_utils')
logger.setLevel(logging.INFO)
if not logger.handlers:
    console_handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

proc_time_logger = logging.getLogger('processing_time')
proc_time_logger.setLevel(logging.INFO)
if not proc_time_logger.handlers:
    proc_time_handler = logging.FileHandler("processing_time.log", encoding="utf-8")
    proc_time_formatter = logging.Formatter('%(asctime)s - %(message)s')
    proc_time_handler.setFormatter(proc_time_formatter)
    proc_time_logger.addHandler(proc_time_handler)
    proc_time_logger.propagate = False

def get_audio_duration(ogg_file_path: str) -> float:
    try:
        audio = AudioSegment.from_ogg(ogg_file_path)
        return len(audio) / 1000.0
    except Exception as e:
        logger.error(f"Ошибка определения длительности: {e}")
        return 0.0

def transcribe_with_gemini_sync(ogg_file_path: str, api_key: str, model_version=None, prompt=None) -> str:
    start_time = time.time()
    try:
        model_to_use = model_version if model_version else TRANSCRIPTION_MODEL
        prompt_to_use = prompt if prompt else TRANSCRIPTION_PROMPT
        logger.info(f"Начинаю транскрибацию через Gemini API модель {model_to_use}")

        client = genai.Client(api_key=api_key)

        logger.info(f"Загружаю аудиофайл: {ogg_file_path}")
        uploaded_file = client.files.upload(file=ogg_file_path)
        logger.info(f"Файл загружен: {getattr(uploaded_file, 'display_name', None)}")

        logger.info("Отправляю запрос на транскрибацию...")
        response = client.models.generate_content(
            model=model_to_use,
            contents=[prompt_to_use, uploaded_file]
        )

        if hasattr(response, 'text') and response.text:
            transcription = response.text.strip()
            logger.info(f"Транскрибация завершена. Длина текста: {len(transcription)} символов")
        elif response.candidates and response.candidates.content.parts:
            transcription = response.candidates.content.parts.text.strip()
            logger.info(f"Транскрибация завершена (альтернативный метод). Длина текста: {len(transcription)} символов")
        else:
            logger.error("Не удалось извлечь текст транскрибации из ответа API")
            transcription = "❌ Не удалось извлечь текст транскрибации из ответа Gemini API."

        return transcription

    except Exception as e:
        logger.error(f"Ошибка транскрибации через Gemini API: {e}", exc_info=True)
        return f"❌ Ошибка транскрибации: {e}"
    finally:
        elapsed_time = time.time() - start_time
        try:
            duration = get_audio_duration(ogg_file_path) if os.path.exists(ogg_file_path) else 0
            proc_time_logger.info(f"Метод: Gemini API, Длительность аудио: {duration:.2f} секунд, Время обработки: {elapsed_time:.2f} секунд")
        except Exception:
            pass

async def transcribe_with_gemini(ogg_file_path: str, api_key: str, model_version=None, prompt=None) -> str:
    return await asyncio.to_thread(transcribe_with_gemini_sync, ogg_file_path, api_key, model_version, prompt)

async def process_voice_message(bot, message, api_key: str) -> str:
    start_time = time.time()
    ogg_filename = None
    try:
        file_info = await bot.get_file(message.voice.file_id)
        file_bytes = await bot.download_file(file_info.file_path)
        with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as tmp_file:
            tmp_file.write(file_bytes.read() if hasattr(file_bytes, 'read') else file_bytes)
            ogg_filename = tmp_file.name

        duration = get_audio_duration(ogg_filename)
        logger.info(f"Длительность: {duration:.2f}s")

        text = await transcribe_with_gemini(ogg_filename, api_key)
        return text
    except Exception as e:
        logger.error(f"Ошибка обработки голосового сообщения: {e}", exc_info=True)
        return f"❌ Ошибка: {e}"
    finally:
        if ogg_filename and os.path.exists(ogg_filename):
            try:
                os.remove(ogg_filename)
                logger.info(f"Удалён временный файл {ogg_filename}")
            except Exception as e:
                logger.warning(f"Не удалось удалить {ogg_filename}: {e}")
        proc_time_logger.info(f"Полное время обработки: {time.time() - start_time:.2f}s")

async def generate_audio_to_opus(text: str, model_version: str, api_key: str) -> tuple[bool, str]:
    """
    Генерация аудио (OPUS) через Gemini:
      - формируем запрос CONTENT/Part по спецификации (AUDIO-модальность + SpeechConfig/VoiceConfig);
      - вытаскиваем аудиобайт из parts.inline_data.data в ответе;
      - сохраняем PCM->WAV->OPUS (libopus), совместимый с Telegram. 
    """
    try:
        logger.info(f"Generating audio for text: {text[:50]}...")
        client = genai.Client(api_key=api_key)

        # Формируем корректный CONTENT (а не просто строку), чтобы гарантированно получить аудиочасти
        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=text)]
            )
        ]

        config = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name='Sulafat')
                )
            ),
        )

        # Вызываем синхронный SDK в пуле потоков (не блокируем event loop)
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=model_version,
            contents=contents,
            config=config
        )

        # По спецификации TTS аудио приходит в parts.inline_data.data (PCM 24kHz, 16-bit) [docs]
        # Ищем байты во всех кандидатах/частях
        audio_bytes = None
        if getattr(response, "candidates", None):
            for cand in response.candidates:
                if cand and cand.content and cand.content.parts:
                    for part in cand.content.parts:
                        if getattr(part, "inline_data", None) and getattr(part.inline_data, "data", None):
                            audio_bytes = part.inline_data.data
                            break
                if audio_bytes:
                    break

        if not audio_bytes:
            logger.error("No inline data found in response parts")
            return (False, "No inline data found in response parts")

        # Сохраняем PCM -> WAV
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_wav:
            wav_filename = tmp_wav.name

        with wave.open(wav_filename, 'wb') as wf:
            wf.setnchannels(1)        # mono
            wf.setsampwidth(2)        # 16-bit (2 bytes)
            wf.setframerate(24000)    # 24kHz
            wf.writeframes(audio_bytes)

        # Конвертация в OPUS для Telegram
        opus_filename = wav_filename.replace('.wav', '.opus')
        AudioSegment.from_wav(wav_filename).export(
            opus_filename,
            format='opus',
            codec='libopus',
            bitrate='64k',
            parameters=["-ar", "48000", "-ac", "1"]
        )

        # Чистим WAV
        try:
            os.unlink(wav_filename)
        except Exception:
            pass

        logger.info(f"Создан OPUS файл: {opus_filename} ({os.path.getsize(opus_filename)} байт)")
        return (True, opus_filename)

    except Exception as e:
        logger.exception(f"Error in generate_audio_to_opus: {str(e)}")
        return (False, str(e))
