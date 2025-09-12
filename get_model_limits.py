# get_model_limits.py
import logging
import os
from google import genai
from google.genai import types

from dotenv import load_dotenv


# Загружаем ключ из .env
load_dotenv(override=True)
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if not GOOGLE_API_KEY:
    raise ValueError("Не найден GOOGLE_API_KEY в .env")

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    """Основная функция для получения и записи лимитов моделей."""
    output_file = "model_limits.txt"
    
    try:
        logger.info("Создание клиента genai...")
        client = genai.Client()
        
        logger.info("Получение списка моделей...")
        models_list = client.models.list()
        
        logger.info(f"Открытие файла '{output_file}' для записи...")
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("# Список моделей и их максимальная длина входного контекста\n")
            f.write("# Формат: model_id - input_token_limit\n")
            f.write("----------------------------------------\n")
            
            model_count = 0
            for model in models_list:
                model_count += 1
                try:
                    model_name = getattr(model, 'name', 'N/A')
                    # Извлекаем короткое имя (после последнего '/')
                    model_id = model_name.split('/')[-1] if '/' in model_name else model_name
                    input_limit = getattr(model, 'input_token_limit', 'N/A')
                    
                    line = f"{model_id} - {input_limit}\n"
                    f.write(line)
                    logger.info(f"Записано: {model_id} - {input_limit}")
                    
                except Exception as e:
                    error_line = f"Ошибка обработки модели #{model_count}: {e}\n"
                    f.write(error_line)
                    logger.error(error_line.strip())
            
            f.write("----------------------------------------\n")
            f.write(f"Всего обработано моделей: {model_count}\n")
        
        logger.info(f"Информация о лимитах успешно записана в '{output_file}'")
        
    except Exception as e:
        logger.error(f"Критическая ошибка при выполнении скрипта: {e}", exc_info=True)
        print(f"Ошибка: {e}")

if __name__ == "__main__":
    main()