"""Оркестрация: transform -> connect -> list -> дифф -> (create|preview) -> сводка."""
import json
import logging
import asyncio

from .config import load_config
from .ha_client import HAClient
from .transform import build_area_payloads, build_create_command


async def _run_async(file_path: str, dry_run: bool) -> None:
    config = load_config()
    desired = build_area_payloads(file_path)

    async with HAClient(config.ws_url, config.token) as client:
        existing = await client.list_areas()
        existing_names = {a.get("name") for a in existing}
        logging.info(f"В Home Assistant уже есть пространств: {len(existing_names)}")

        to_create = skipped = errors = 0

        for area in desired:
            name = area["name"]

            # Идемпотентность: ключ сравнения — name (уникален за счёт номера).
            if name in existing_names:
                logging.info(f"SKIP: '{name}' уже существует.")
                skipped += 1
                continue

            if dry_run:
                cmd = build_create_command(area)
                logging.info(
                    f"[DRY RUN] WOULD CREATE:\n"
                    f"{json.dumps(cmd, ensure_ascii=False, indent=2)}"
                )
                to_create += 1
            else:
                resp = await client.create_area(name, area["aliases"])
                if resp.get("success"):
                    logging.info(f"CREATED: '{name}'")
                    to_create += 1
                else:
                    logging.error(f"Ошибка создания '{name}': {resp.get('error')}")
                    errors += 1

        verb = "к созданию" if dry_run else "создано"
        logging.info(f"Итог: {verb} {to_create} | пропущено {skipped} | ошибок {errors}")


def run(file_path: str, dry_run: bool) -> None:
    """Синхронная точка входа для запуска асинхронного сценария."""
    asyncio.run(_run_async(file_path, dry_run))
