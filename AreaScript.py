"""Entry-point: импорт пространств (Areas) в Home Assistant из parquet.

Dry-run по умолчанию (read-only: подключается к HA, читает существующие Areas
и показывает дифф, но ничего не пишет). Реальное создание — флагом --live.
Вся логика в пакете areacreator.
"""
import logging
import argparse

from areacreator.runner import run

# Структурированное логирование согласно RULES.md (вместо print()).
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)


def main() -> None:
    parser = argparse.ArgumentParser(description="HA Area Creator")
    parser.add_argument(
        "--file", type=str, default="normalized/spaces.parquet",
        help="Путь к файлу parquet",
    )
    parser.add_argument(
        "--live", action="store_true",
        help="Снять dry-run и реально создавать Areas в Home Assistant",
    )
    args = parser.parse_args()

    try:
        run(file_path=args.file, dry_run=not args.live)
    except Exception as e:
        logging.error(f"Критическая ошибка: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
