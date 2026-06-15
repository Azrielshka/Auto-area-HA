# Архитектура: этапы 1–2 (живая отправка + идемпотентность)

## Решения
- **Где запускается:** внешний скрипт с рабочей машины, подключается к Home Assistant по **WebSocket API**. Не внутри HA (тяжёлые зависимости `pandas`/`pyarrow` остаются вне HA; создание Area — WS-команда, а не сервис, поэтому запуск «внутри» не даёт выгоды).
- **Dry-run:** read-only. Подключается и читает существующие Areas (`config/area_registry/list`), показывает дифф (что создалось бы / что уже есть), но **ничего не пишет**. Остаётся режимом по умолчанию.
- **Идемпотентность:** ключ сравнения — `name` (уникален за счёт номера-префикса). Если имя уже есть — SKIP.
- **Расхождение алиасов:** если имя совпало, но алиасы отличаются — просто SKIP (ручные правки в HA не затираем).

## Структура модулей
```
Auto-area-HA/
├── areacreator/
│   ├── __init__.py
│   ├── config.py        # HA_BASE_URL + HA_TOKEN из .env (python-dotenv); вывод ws/wss из схемы URL
│   ├── transform.py     # parquet -> [{name, aliases}]  (текущая логика format_room_name + словарь)
│   ├── ha_client.py     # async WS-клиент: connect, auth, list_areas, create_area
│   └── runner.py        # оркестрация: transform -> connect -> list -> diff -> (create|preview) -> сводка
├── AreaScript.py        # тонкий entry-point: argparse -> runner
└── normalized/...
```

## Зависимости (добавить в requirements.txt)
- `websockets` — асинхронный WS-клиент (упомянут в RULES.md)
- `python-dotenv` — загрузка `.env`

## Протокол Home Assistant (WS)
```
1. connect ws(s)://<host>/api/websocket
2. server -> {"type": "auth_required"}
3. client -> {"type": "auth", "access_token": "<LLAT>"}
4. server -> {"type": "auth_ok"} | {"type": "auth_invalid"}  # invalid -> стоп с ERROR
5. client -> {"id": N, "type": "config/area_registry/list"}
6. server -> {"id": N, "type": "result", "success": true, "result": [ {area_id, name, aliases, ...}, ... ]}
7. client -> {"id": M, "type": "config/area_registry/create", "name": ..., "aliases": [...]}
8. server -> {"id": M, "type": "result", "success": true|false, "result": {...} | "error": {...}}
```
- `id` — монотонно растущий счётчик, ответы сопоставляются по `id`.
- Схема: `http -> ws`, `https -> wss` (выводим из `HA_BASE_URL`).

## Поток выполнения (runner)
```
1. config: загрузить HA_BASE_URL, HA_TOKEN (ошибка, если нет -> ERROR, стоп)
2. transform: parquet -> desired = [{name, aliases}, ...]
3. connect + auth (auth_invalid -> ERROR, стоп)
4. existing = list_areas(); existing_names = { a.name for a in existing }
5. для каждого desired:
     name in existing_names ?
        да  -> SKIP (INFO: "уже существует")
        нет -> dry-run ? log "WOULD CREATE" + payload
                       : create_area(payload); log результат (success/error)
6. сводка: создано N | пропущено M | ошибок K
```
Dry-run и live идут по одному пути; различие только в шаге 5 (write). Идемпотентность делает повторный запуск после частичного сбоя безопасным.

## CLI
```
python AreaScript.py                 # dry-run (по умолчанию): connect + list + дифф, без записи
python AreaScript.py --live          # реально создаёт недостающие Areas
python AreaScript.py --file <path>   # путь к parquet (default: normalized/spaces.parquet)
```

## Обработка ошибок
- Нет конфигурации / токена -> ERROR, стоп до подключения.
- `auth_invalid` / отказ соединения / таймаут -> ERROR, стоп.
- Ошибка создания конкретного Area (`success: false`) -> ERROR, продолжаем, учитываем в сводке.
- Таймаут на ожидание ответа по `id`.

## Безопасность (по RULES.md)
- `HA_TOKEN` только в `.env` (в `.gitignore`); в коде/логах не печатаем.
- В лог — base_url и факт успеха/ошибки, без токена.

## Вне рамок этих этапов (бэклог)
- Этажи (`floor`) -> `config/floor_registry/*` и привязка Areas.
- Обновление существующих Areas (alias drift) — сознательно отложено.

## Вне рамок проекта совсем
- Устройства/сущности (`device_rows.parquet`) — обрабатываются в отдельном проекте, здесь не трогаем.
```
