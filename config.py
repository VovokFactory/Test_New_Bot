# config.py 
import os
from configparser import ConfigParser
import logging # Импортируем logging для сообщений

# Настройки очереди обработки голоса
# Количество воркеров для параллельной обработки голосовых сообщений
# Рекомендуется устанавливать значение от 1 до количества ядер CPU
VOICE_WORKERS_COUNT = 2 # По умолчанию 2 воркера

# Настройки контекста
MAX_HISTORY = 100                   # Максимальная глубина контекста
CONTEXT_TIMEOUT = 12000              # Время хранения контекста (сек)

# Начальные размеры контекста
DEFAULT_MAX_HISTORY   = 100          # сообщений
DEFAULT_CONTEXT_TTL   = 12000        # секунд


# config.py

LOG_TO_CONSOLE = False  # Включи True, если хочешь лог в консоль

# Настройки для транскрибации через Gemini
TRANSCRIPTION_MODEL = 'gemini-2.5-flash-lite' # Или любая другая подходящая модель
TRANSCRIPTION_PROMPT = 'Транскрибируй речь, выдай текст без дополнительных слов'

# Настройки ролей
ROLE_CONFIG_FILE = 'person.set'
ROLES_BASE_DIR = 'person' # Изменено с 'roles' на 'person'

# Создаем отдельный логгер для config, чтобы видеть его сообщения
logger_config = logging.getLogger('config') 
# Убедимся, что он пишет в тот же файл
if not logger_config.handlers:
    logger_config.addHandler(logging.FileHandler("bot_debug.log", encoding='utf-8'))
    logger_config.setLevel(logging.DEBUG) # Повышаем уровень для отладки


def find_file_case_insensitive(directory, filename):
    """
    Ищет файл в директории без учета регистра.
    
    Args:
        directory (str): Путь к директории.
        filename (str): Имя файла для поиска.
        
    Returns:
        str or None: Путь к найденному файлу или None, если не найден.
    """
    if not os.path.exists(directory):
        return None
        
    try:
        # Получаем список файлов в директории
        files = os.listdir(directory)
        filename_lower = filename.lower()
        
        # Ищем файл, имя которого совпадает без учета регистра
        for f in files:
            if f.lower() == filename_lower:
                return os.path.join(directory, f)
    except Exception as e:
        logger_config.warning(f"Ошибка при поиске файла в директории {directory}: {e}")
    
    return None

def load_role_settings():
    """
    Загружает настройки роли из файла person.set.
    """
    logger_config.debug("Начало загрузки настроек роли...")
    role_settings = {
        'name': None,
        'instructions': None,
        'knowledge_base': None
    }
    
    logger_config.debug(f"Проверяем наличие файла настроек: {os.path.abspath(ROLE_CONFIG_FILE)}")
    if not os.path.exists(ROLE_CONFIG_FILE):
        logger_config.info(f"Файл настроек роли {ROLE_CONFIG_FILE} не найден. Используется стандартный режим.")
        return role_settings

    try:
        with open(ROLE_CONFIG_FILE, 'r', encoding='utf-8') as f:
            logger_config.debug(f"Файл {ROLE_CONFIG_FILE} открыт для чтения.")
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                logger_config.debug(f"Читаю строку {line_num}: '{line}'")
                # Пропускаем пустые строки и комментарии
                if not line or line.startswith('#'):
                    continue
                
                # Ищем строку вида ROLE = ...
                if line.startswith('ROLE'):
                    try:
                        # Разделяем по '=' и берем правую часть
                        _, raw_role_value = line.split('=', 1)
                        raw_role = raw_role_value.strip()
                        logger_config.info(f"Найдена роль в конфиге: '{raw_role}'")
                        
                        # Проверяем, задана ли роль и не является ли она "нулевой"
                        if raw_role and raw_role.lower() not in ('null', 'none', '0', ''):
                            
                            # Формируем путь к папке роли
                            role_dir = os.path.join(ROLES_BASE_DIR, raw_role)
                            logger_config.debug(f"Путь к папке роли: {os.path.abspath(role_dir)}")
                            logger_config.debug(f"Папка роли существует: {os.path.exists(role_dir)}")
                            
                            # --- ОСНОВНОЕ ПРАВИЛО ---
                            # Роль запускается ТОЛЬКО если существует Instructions.txt (в любом регистре)
                            instructions_path = find_file_case_insensitive(role_dir, 'Instructions.txt')
                            logger_config.debug(f"Путь к Instructions.txt (поиск без учета регистра): {instructions_path}")
                            if instructions_path:
                                role_settings['name'] = raw_role
                                logger_config.info(f"Найден файл инструкций '{os.path.basename(instructions_path)}' для роли '{raw_role}'. Активируем роль.")
                                
                                # Загружаем Instructions.txt
                                try:
                                    with open(instructions_path, 'r', encoding='utf-8') as inst_f:
                                        instructions_content = inst_f.read().strip()
                                        if instructions_content:
                                            role_settings['instructions'] = instructions_content
                                            logger_config.info(f"Инструкции для роли '{raw_role}' загружены. Длина: {len(instructions_content)} символов.")
                                        else:
                                            logger_config.warning(f"Файл инструкций {instructions_path} пуст.")
                                except Exception as e:
                                    logger_config.error(f"Ошибка чтения файла инструкций {instructions_path}: {e}")
                                
                                # Загружаем knowledge_base.txt (опционально, с поиском без учета регистра)
                                kb_path = find_file_case_insensitive(role_dir, 'knowledge_base.txt')
                                logger_config.debug(f"Путь к knowledge_base.txt (поиск без учета регистра): {kb_path}")
                                if kb_path:
                                    try:
                                        with open(kb_path, 'r', encoding='utf-8') as kb_f:
                                            kb_content = kb_f.read().strip()
                                            if kb_content:
                                                role_settings['knowledge_base'] = kb_content
                                                logger_config.info(f"База знаний '{os.path.basename(kb_path)}' для роли '{raw_role}' загружена. Длина: {len(kb_content)} символов.")
                                            else:
                                                 logger_config.info(f"Файл базы знаний {kb_path} пуст.")
                                    except Exception as e:
                                        logger_config.warning(f"Ошибка чтения файла базы знаний {kb_path}: {e}. Продолжаем без базы знаний.")
                                else:
                                     logger_config.info(f"Файл базы знаний 'knowledge_base.txt' не найден в {role_dir}. Продолжаем без базы знаний.")
                                    
                            else:
                                # Instructions.txt НЕ найден (ни в каком регистре)
                                logger_config.warning(
                                    f"Для роли '{raw_role}' не найден файл инструкций 'Instructions.txt' (в любом регистре) в папке {os.path.abspath(role_dir)}. "
                                    f"Роль НЕ будет активирована. Используется стандартный режим."
                                )
                        else:
                            logger_config.info("Роль не задана или установлена в 'null'. Используется стандартный режим.")
                        # После обработки ROLE=... выходим из цикла
                        break 
                    except ValueError as ve:
                        # Если split не смог разделить строку на 2 части
                        logger_config.warning(f"Некорректный формат строки {line_num} в файле {ROLE_CONFIG_FILE}: {line}. Ошибка: {ve}")
                        continue # Пропускаем эту строку и идем дальше
            
            logger_config.info("Файл person.set успешно прочитан (или обработан с предупреждениями).")
            
    except Exception as e:
        logger_config.error(f"Ошибка при чтении файла {ROLE_CONFIG_FILE}: {e}. Используется стандартный режим.", exc_info=True)
        
    logger_config.debug(f"Итоговые настройки роли: name={role_settings['name']}, instructions={'YES' if role_settings['instructions'] else 'NO'}, knowledge_base={'YES' if role_settings['knowledge_base'] else 'NO'}")
    return role_settings

# Загружаем настройки роли при импорте config.py
CURRENT_ROLE_SETTINGS = load_role_settings()
