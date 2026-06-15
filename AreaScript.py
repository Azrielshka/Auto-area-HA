import pandas as pd
import logging
import json
import argparse
import os

# Настройка структурированного логирования согласно RULES.md
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)

# Словарь для перевода транслита в красивые русские названия.
# Ключ - часть slug после номера, Значение - желаемое имя в HA.
TRANSLATION_DICT = {
    "kabinet_medits": "Кабинет медицинский",
    "lestnitsa": "Лестница",
    "koridor": "Коридор",
    "lekts": "Лекционная",
    "lekts_kabin": "Лекционный кабинет",
    "lekts_kabinet": "Лекционный кабинет",
    "lekts_kabinet_med": "Лекционный кабинет (мед.)",
    "s_u_zhenskii": "Санузел женский",
    "s_u_muzhskoi": "Санузел мужской",
    "obshchii": "Общий"
}

def format_room_name(slug: str) -> str:
    """
    Преобразует room_slug (например, 402_kabinet_medits) 
    в читаемое имя (например, 402_Кабинет медицинский).
    """
    # Разбиваем строку по первому символу подчеркивания
    parts = slug.split('_', 1)
    
    if len(parts) == 2:
        prefix, rest = parts
        # Ищем перевод в словаре. Если нет - WARNING + фоллбэк (капитализация транслита)
        if rest in TRANSLATION_DICT:
            ru_name = TRANSLATION_DICT[rest]
        else:
            ru_name = rest.replace('_', ' ').capitalize()
            logging.warning(
                f"Тип помещения '{rest}' (slug '{slug}') не найден в TRANSLATION_DICT — "
                f"использован фоллбэк '{ru_name}'. Добавьте запись в словарь для корректного имени."
            )
        return f"{prefix}_{ru_name}"

    # Если подчеркиваний нет, просто капитализируем
    logging.warning(f"Slug '{slug}' без префикса '_' — использована фоллбэк-капитализация.")
    return slug.capitalize()

def main(file_path: str, dry_run: bool):
    if not os.path.exists(file_path):
        logging.error(f"Файл {file_path} не найден.")
        return

    try:
        # Шаг 2: Чтение данных (Python)
        df = pd.read_parquet(file_path)
        logging.info(f"Успешно прочитан файл {file_path}. Найдено пространств: {len(df)}")
    except Exception as e:
        logging.error(f"Ошибка при чтении Parquet файла: {e}")
        return

    # Проходим по каждой строке сформированного датафрейма
    for index, row in df.iterrows():
        room_slug = row.get('room_slug', '')
        space = row.get('space', '')

        # Формируем красивое имя
        pretty_name = format_room_name(room_slug)
        
        # Подготавливаем алиасы (если space не пустой)
        # Убираем лишние пробелы и символы, если нужно, но пока берем как есть
        aliases = [space.strip()] if pd.notna(space) and space.strip() else []

        # Формируем итоговый JSON-запрос для Home Assistant
        payload = {
            "type": "config/area_registry/create",
            "name": pretty_name,
            "aliases": aliases
        }

        # Режим "Холостого прогона" (Dry Run)
        if dry_run:
            logging.info(
                f"[DRY RUN] Исходный slug: '{room_slug}' -> Сформирован JSON:\n"
                f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
            )
        else:
            # Реальная отправка через WebSocket API — задача следующего этапа (бэклог).
            logging.error(
                "Режим --live ещё не реализован: отправка в Home Assistant отложена в бэклог. "
                "Запустите без --live для dry-run."
            )
            return

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="HA Area Creator")
    parser.add_argument('--file', type=str, default='normalized/spaces.parquet', help='Путь к файлу parquet')
    # Dry-run — безопасный режим по умолчанию (только вывод JSON, без отправки в HA).
    # Реальная отправка включается явным флагом --live (будет реализована на следующем этапе).
    parser.add_argument('--live', action='store_true', help='Снять dry-run и реально отправлять запросы в Home Assistant')

    args = parser.parse_args()

    main(file_path=args.file, dry_run=not args.live)