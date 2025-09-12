# make_tree.py
import os
from pathlib import Path

def generate_tree(root_dir: str, ignore_patterns: list[str], prefix: str = "", is_last: bool = True) -> str:
    """
    Рекурсивно генерирует текстовое представление дерева файлов и папок.

    Args:
        root_dir (str): Путь к корневой директории.
        ignore_patterns (list[str]): Список паттернов для игнорирования.
        prefix (str): Префикс для текущего уровня (для отступов).
        is_last (bool): Является ли текущий элемент последним в списке родителя.

    Returns:
        str: Строка, представляющая дерево.
    """
    tree_str = ""
    try:
        # Получаем список элементов в директории
        entries = list(os.scandir(root_dir))
        # Сортируем: сначала директории, потом файлы, по имени
        entries.sort(key=lambda e: (not e.is_dir(), e.name.lower()))
    except PermissionError:
        # Если нет прав доступа, просто возвращаем пустую строку или сообщение
        return f"{prefix}{'└── ' if is_last else '├── '} [Нет доступа]\n"

    # Фильтруем элементы
    filtered_entries = []
    for entry in entries:
        # Проверяем, соответствует ли элемент или его путь какому-либо паттерну игнорирования
        relative_path = os.path.relpath(entry.path, start=os.path.dirname(root_dir)) # Путь относительно родителя root_dir
        normalized_path = relative_path.replace(os.sep, '/') # Нормализуем для сравнения
        
        # Проверяем, начинается ли путь с игнорируемой папки или содержит её
        should_ignore = any(pattern in normalized_path for pattern in ignore_patterns)
        
        if not should_ignore:
            filtered_entries.append(entry)

    # Обрабатываем отфильтрованные элементы
    for i, entry in enumerate(filtered_entries):
        is_last_entry = (i == len(filtered_entries) - 1)
        
        # Определяем соединитель
        connector = "└── " if is_last_entry else "├── "
        
        # Добавляем текущий элемент к дереву
        tree_str += f"{prefix}{connector}{entry.name}\n"
        
        # Если это директория, рекурсивно добавляем её содержимое
        if entry.is_dir(follow_symlinks=False):
            # Определяем префикс для потомков
            extension = "    " if is_last_entry else "│   "
            tree_str += generate_tree(entry.path, ignore_patterns, prefix + extension, is_last_entry)
            
    return tree_str

def main():
    """Главная функция скрипта."""
    # --- Настройки ---
    project_root = "."  # Текущая директория
    output_file = "Prog_Tree.txt"
    
    # Паттерны для игнорирования (можно легко расширить)
    ignore_list = [
        "__pycache__",
        "venv",
        ".git",
        ".vscode",
        ".idea",
        "node_modules",
        ".pytest_cache__",
        ".mypy_cache__",
        ".eggs",
        ".tox",
        ".nox",
        "build",
        "dist",
        ".egg-info",
        ".coverage",
        ".DS_Store",
        "Thumbs.db",
        "Prog_Tree.txt" # Игнорируем сам файл вывода, если он уже существует
        # Добавьте сюда свои паттерны
    ]
    
    print(f"Генерация структуры проекта из '{os.path.abspath(project_root)}'...")
    
    # Генерируем дерево
    tree_output = f"{os.path.basename(os.path.abspath(project_root))}/\n"
    tree_output += generate_tree(project_root, ignore_list)
    
    # Записываем в файл
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(tree_output)
        print(f"Структура проекта успешно записана в '{output_file}'.")
    except IOError as e:
        print(f"Ошибка при записи в файл '{output_file}': {e}")
        return

    # Выводим в консоль (опционально)
    print("\nСгенерированная структура:")
    print(tree_output)

if __name__ == "__main__":
    main()