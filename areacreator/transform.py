"""Преобразование данных из parquet в полезную нагрузку для создания Areas.

Здесь живёт вся доменная логика именования (транслит -> кириллица).
Сетью и Home Assistant модуль не занимается.
"""
import os
import logging

import pandas as pd

# Словарь для перевода транслита в читаемые русские названия.
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
    "obshchii": "Общий",
}


def format_room_name(slug: str) -> str:
    """402_kabinet_medits -> 402_Кабинет медицинский."""
    parts = slug.split("_", 1)

    if len(parts) == 2:
        prefix, rest = parts
        if rest in TRANSLATION_DICT:
            ru_name = TRANSLATION_DICT[rest]
        else:
            ru_name = rest.replace("_", " ").capitalize()
            logging.warning(
                f"Тип помещения '{rest}' (slug '{slug}') не найден в TRANSLATION_DICT — "
                f"использован фоллбэк '{ru_name}'. Добавьте запись в словарь."
            )
        return f"{prefix}_{ru_name}"

    logging.warning(f"Slug '{slug}' без префикса '_' — использована фоллбэк-капитализация.")
    return slug.capitalize()


def build_area_payloads(file_path: str) -> list[dict]:
    """Читает parquet и возвращает список {'name', 'aliases'} для каждого пространства."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Файл {file_path} не найден.")

    df = pd.read_parquet(file_path)
    logging.info(f"Успешно прочитан файл {file_path}. Найдено пространств: {len(df)}")

    payloads: list[dict] = []
    for _, row in df.iterrows():
        room_slug = row.get("room_slug", "")
        space = row.get("space", "")

        name = format_room_name(room_slug)

        aliases: list[str] = []
        if pd.notna(space):
            alias = str(space).strip()
            if alias:
                aliases = [alias]

        payloads.append({"name": name, "aliases": aliases})

    return payloads


def build_create_command(payload: dict) -> dict:
    """Полная WS-команда создания Area (для отправки и для предпросмотра в dry-run)."""
    return {
        "type": "config/area_registry/create",
        "name": payload["name"],
        "aliases": payload["aliases"],
    }
