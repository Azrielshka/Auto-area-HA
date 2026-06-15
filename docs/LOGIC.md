# Логика работы скриптов

Описание того, **как именно** работает импорт пространств (Areas) в Home Assistant —
от запуска до создания Area. Архитектурные решения и протокол HA см. в
[ARCHITECTURE.md](ARCHITECTURE.md); правила кода — в [RULES.md](RULES.md).

## Что делает проект

Читает список помещений из `normalized/spaces.parquet`, превращает технические
slug-имена в читаемые русские названия и создаёт по ним Areas в Home Assistant
через WebSocket API. Безопасно для повторного запуска: уже существующие Area
пропускаются (идемпотентность).

## Запуск

```bash
python AreaScript.py                 # dry-run (по умолчанию): подключается, читает, показывает дифф, НЕ пишет
python AreaScript.py --live          # реально создаёт недостающие Areas
python AreaScript.py --file <path>   # путь к parquet (default: normalized/spaces.parquet)
```

Запускать нужно из venv проекта (см. README/ARCHITECTURE). Для подключения к HA
требуется файл `.env` с `HA_BASE_URL` и `HA_TOKEN` (образец — `.env.example`).

## Сквозной поток (end-to-end)

```
AreaScript.py (entry-point)
  └─ argparse: --file, --live
  └─ runner.run(file_path, dry_run = not --live)
        └─ asyncio.run(_run_async)
              1. load_config()            config.py   → Config(base_url, token), ws_url
              2. build_area_payloads()    transform.py→ desired = [{name, aliases}, ...]   (из parquet)
              3. HAClient(...).connect()  ha_client.py→ WS + аутентификация
              4. client.list_areas()      ha_client.py→ existing (что уже есть в HA)
              5. дифф по name + create/preview                                            (цикл)
              6. сводка: создано N | пропущено M | ошибок K
```

Dry-run и live идут по **одному и тому же пути** — различие только в шаге 5
(пишем в HA или просто печатаем то, что отправили бы).

## Формат входного файла `spaces.parquet`

Лежит в `normalized/spaces.parquet`. **Одна строка = одно пространство (Area).**
В текущем примере — 12 строк × 10 колонок. Файл содержит больше данных, чем нужно
этому скрипту: реально читаются только **`room_slug`** и **`space`**, остальные
колонки относятся к отдельному проекту устройств/сущностей и здесь игнорируются
(см. «Вне рамок проекта» в ARCHITECTURE.md).

| Колонка | Тип | Исп. скриптом | Назначение | Пример |
|---|---|:---:|---|---|
| `room_slug` | str | **да** → `name` | Технический slug `<номер>_<тип>`; номер уникален, тип маппится через `TRANSLATION_DICT` | `402_kabinet_medits` |
| `space` | str | **да** → `aliases` | Короткое исходное имя; идёт одним алиасом Area (если непустое) | `402_кабинет_медиц` |
| `floor` | int | нет | Этаж (для будущей привязки к floor_registry) | `4` |
| `card_type` | str | нет | Тип карточки/помещения | `cabinet` |
| `groups` | list[str] | нет | Группы освещения помещения | `[402_0, 402_1, 402_2]` |
| `groups_count` | int | нет | Кол-во групп | `3` |
| `general_light_entity` | str | нет | Сущность «общий свет» | `light.402_..._obshchii` |
| `ms_sensors_by_group` | list | нет | Датчики по группам (может содержать `None`) | `[sensor.ms_1_20_0, ...]` |
| `ms_sensors_unique` | list | нет | Уникальные датчики помещения | `[sensor.ms_1_20_0, ...]` |
| `warnings` | list | нет | Предупреждения нормализации | `[]` |

Как используются две нужные колонки:
- **`room_slug` → имя Area.** `format_room_name` режет slug по первому `_`:
  префикс-номер сохраняется, остаток (`kabinet_medits`) переводится через
  `TRANSLATION_DICT`. Итог: `402_kabinet_medits` → `402_Кабинет медицинский`.
  Номер в префиксе делает имена уникальными и служит ключом идемпотентности.
- **`space` → алиас.** Значение колонки обрезается по пробелам и, если непустое,
  кладётся в `aliases` единственным элементом; иначе `aliases = []`.

Минимально валидной для скрипта является строка с непустым `room_slug` (формат
`<номер>_<тип>`); `space` желателен, но не обязателен. Если `<тип>` отсутствует в
`TRANSLATION_DICT` — имя всё равно собирается фоллбэком, с `WARNING` в лог.

## Модули и их роли

Чёткое разделение ответственности: один модуль — одна забота.

### `AreaScript.py` — тонкий entry-point
- Настраивает `logging` (формат `время - уровень - сообщение`, см. RULES.md).
- Разбирает аргументы `--file` и `--live`.
- Вызывает `runner.run(file_path, dry_run = not --live)`.
- Любое исключение → лог `ERROR` + выход с кодом `1`.

### `areacreator/config.py` — конфигурация и секреты
- `load_config()` грузит `.env` через `python-dotenv`, читает `HA_BASE_URL` и
  `HA_TOKEN` из окружения. Если чего-то нет — `RuntimeError` с понятным текстом
  (скрипт останавливается до подключения).
- `Config.ws_url` выводит адрес WebSocket из `base_url`:
  `http://host:8123` → `ws://host:8123/api/websocket` (и `https` → `wss`).
- Токен берётся только из `.env` (он в `.gitignore`), в код и логи не попадает.

### `areacreator/transform.py` — доменная логика имён (parquet → payload)
Сетью и Home Assistant не занимается, только данные.
- `build_area_payloads(file_path)` читает parquet (`pandas`) и для каждой строки
  собирает `{"name": ..., "aliases": [...]}`:
  - `name` ← `format_room_name(room_slug)`;
  - `aliases` ← одно значение из колонки `space` (если оно непустое), иначе `[]`.
  - Если файла нет — `FileNotFoundError`.
- `format_room_name(slug)` превращает `402_kabinet_medits` → `402_Кабинет медицинский`:
  - режет slug по **первому** `_` на префикс-номер и остаток;
  - остаток ищется в `TRANSLATION_DICT` (транслит → русское название);
  - если остатка нет в словаре — фоллбэк `rest.replace("_", " ").capitalize()` и
    **`WARNING`** (сигнал «добавь запись в словарь»);
  - префикс-номер сохраняется → имена остаются уникальными.
- `build_create_command(payload)` — собирает полную WS-команду
  `config/area_registry/create` (используется и для отправки, и для предпросмотра
  в dry-run, чтобы видеть ровно то, что ушло бы в HA).

`TRANSLATION_DICT` — единственное место, которое нужно расширять при появлении
новых типов помещений.

### `areacreator/ha_client.py` — транспорт WebSocket
Только транспорт: подключение, аутентификация, вызовы `area_registry`. Доменной
логики (имена, дифф) здесь нет. Используется как async context manager
(`async with HAClient(...)`), который сам открывает и закрывает соединение.
- `connect()` — открывает WS (с таймаутом), ждёт `auth_required`, шлёт `auth` с
  токеном, ожидает `auth_ok` (иначе `HAAuthError`).
- `list_areas()` — `config/area_registry/list` → список существующих Areas.
- `create_area(name, aliases)` — `config/area_registry/create`, возвращает сырой
  ответ HA (с ключом `success`).
- `_command()` — присваивает запросу растущий `id` и читает сообщения, пока не
  придёт `result` именно с этим `id` (события и чужие ответы игнорируются).
- Все операции чтения/подключения защищены таймаутом (по умолчанию 10 с).

### `areacreator/runner.py` — оркестрация
Связывает всё вместе (`_run_async`):
1. `load_config()` → `build_area_payloads()` (желаемое состояние).
2. В рамках `async with HAClient(...)`: `list_areas()` → множество `existing_names`.
3. По каждому желаемому Area:
   - **`name in existing_names`** → `SKIP` (`INFO: уже существует`), счётчик `skipped`;
   - иначе при **dry-run** → лог `[DRY RUN] WOULD CREATE` + JSON команды;
   - иначе (**live**) → `create_area(...)`; `success` → `CREATED`, иначе `ERROR` и
     счётчик `errors` (цикл при этом не прерывается).
4. Итоговая строка: `создано/к созданию N | пропущено M | ошибок K`.

`run()` — синхронная обёртка (`asyncio.run`) для вызова из entry-point.

## Идемпотентность

Ключ сравнения — **`name`** (он уникален за счёт номера-префикса). Если Area с
таким именем уже есть в HA — она пропускается. Поэтому скрипт можно запускать
сколько угодно раз: повторный прогон создаёт только недостающее и безопасен после
частичного сбоя. Расхождение алиасов сознательно игнорируется (ручные правки в HA
не затираем) — см. бэклог в ARCHITECTURE.md.

## Dry-run и безопасность

- Dry-run — **режим по умолчанию** и полностью read-only: подключается, читает
  существующие Areas, показывает дифф, но ничего не пишет. Запись включается
  только явным флагом `--live`.
- Перед боевым прогоном полезно сначала посмотреть dry-run-вывод.

## Обработка ошибок

| Ситуация | Поведение |
|---|---|
| Нет `HA_BASE_URL` / `HA_TOKEN` | `RuntimeError` → `ERROR`, стоп до подключения |
| `auth_invalid` / отказ соединения / таймаут | `HAAuthError`/таймаут → `ERROR`, стоп |
| Нет parquet-файла | `FileNotFoundError` → `ERROR`, стоп |
| slug отсутствует в словаре | `WARNING` + фоллбэк-имя, работа продолжается |
| `create_area` вернул `success: false` | `ERROR`, учитывается в сводке, цикл продолжается |

Логирование — через модуль `logging` (а не `print`): `INFO` для успеха, `WARNING`
для подозрительных данных, `ERROR` для сбоев.
