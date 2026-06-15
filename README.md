# Auto-area-HA

Импорт пространств (**Areas**) в Home Assistant из `normalized/spaces.parquet`.
Скрипт читает список помещений, превращает технические slug-имена в читаемые
русские названия и создаёт по ним Areas через WebSocket API. Безопасен для
повторного запуска: уже существующие Area пропускаются (идемпотентность).

## Документация

| Документ | О чём |
|---|---|
| [docs/LOGIC.md](docs/LOGIC.md) | Как работают скрипты: сквозной поток, роли модулей, формат `spaces.parquet`, обработка ошибок |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Архитектурные решения, протокол Home Assistant (WS), структура проекта |
| [docs/RULES.md](docs/RULES.md) | Правила работы с кодом (секреты, dry-run, логирование, зависимости) |
| [docs/TZ.md](docs/TZ.md) | Техническое задание |
| [changelog.txt](changelog.txt) | Журнал изменений |

## Требования

- Python 3.10+
- Доступ к Home Assistant и долгоживущий токен (Long-Lived Access Token)

## Установка окружения

1. Создать и активировать виртуальное окружение:

   **Windows (PowerShell):**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   **Linux / macOS:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Установить зависимости:
   ```bash
   pip install -r requirements.txt
   ```

> Если активация в PowerShell блокируется политикой выполнения, один раз выполните:
> `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`

## Конфигурация

Секреты хранятся в `.env` (он в `.gitignore`, в репозиторий не попадает).
Скопируйте шаблон и заполните своими значениями:

```bash
# Windows: copy .env.example .env
cp .env.example .env
```

```ini
HA_BASE_URL=http://homeassistant.local:8123
HA_TOKEN=your_long_lived_access_token_here
```

Схема WebSocket выводится из `HA_BASE_URL` автоматически (`http→ws`, `https→wss`).

## Запуск

Выполнять из активированного venv в корне проекта:

```bash
python AreaScript.py                 # dry-run (по умолчанию): подключается, читает, показывает дифф, НЕ пишет
python AreaScript.py --live          # реально создаёт недостающие Areas в Home Assistant
python AreaScript.py --file <path>   # путь к parquet (default: normalized/spaces.parquet)
```

Перед боевым прогоном полезно сначала посмотреть вывод dry-run (без флага) —
он покажет ровно те команды, что ушли бы в Home Assistant. Повторный `--live`
безопасен: существующие Areas пропускаются (`SKIP`), создаётся только недостающее.

Подробнее о логике и формате данных — в [docs/LOGIC.md](docs/LOGIC.md).
