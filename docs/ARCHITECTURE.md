# Архитектура MetroCheck

## Диаграмма потоков

```
                    Сервер (Docker Compose)
                    ┌──────────────────────────────────────────┐
                    │  backend_network (bridge)                │
                    │                                          │
                    │  ┌──────────┐   ┌──────────┐             │
                    │  │ postgres │◄──│  redis   │             │
                    │  │  :5434   │   │  :6382   │             │
                    │  └────┬─────┘   └──────────┘             │
                    │       │                                  │
                    │  ┌────▼──────┐    ┌──────────────┐      │
                    │  │  backend  │◄──►│     n8n      │      │
                    │  │  :8002    │    │    :5681     │      │
                    │  └────┬──────┘    └──────┬───────┘      │
                    │       │                  │               │
                    │  ┌────▼──────┐          │               │
                    │  │    awg    │◄─tinyproxy┘               │
                    │  │  (NL VPN) │   :8888                   │
                    │  └───────────┘                           │
                    └──────────────────────────────────────────┘
                              │            │
                    ┌─────────┴──┐    ┌────┴─────────┐
                    ▼            ▼    ▼               ▼
              fgis.gost.ru   openrouter.ai      Netbird peer
              (ARSHIN public)  (AI модели)       (сервер)
                                                   │
                                              Netbird mesh VPN
                                              (WireGuard P2P)
                                                   │
                                        ┌──────────┴──────────┐
                                        │  ПК Зонова (Тюмень) │
                                        │                     │
                                        │  ┌───────────────┐  │
                                        │  │ Chrome +      │  │
                                        │  │ Extension     │  │
                                        │  │ (content.js   │  │
                                        │  │  на fgis.gost)│  │
                                        │  └───────┬───────┘  │
                                        │          │ POST     │
                                        │  ┌───────▼───────┐  │
                                        │  │ token-agent   │  │
                                        │  │ :8003         │  │
                                        │  │ (FastAPI .exe)│  │
                                        │  └───────┬───────┘  │
                                        │          │          │
                                        │  Netbird peer       │
                                        └────────────────────┘
```

## Компоненты

### Серверная часть (Docker)

| Контейнер | Порт | Назначение |
|-----------|------|-----------|
| postgres | 5434 | PostgreSQL 16 |
| redis | 6382 | Redis 7 (очередь n8n) |
| backend | 8002 | FastAPI приложение |
| n8n | 5681 | n8n workflow engine |
| awg | — | AmneziaWG NL VPN + tinyproxy |

### Клиентская часть (ПК Зонова)

| Компонент | Назначение |
|-----------|-----------|
| Chrome Extension | Читает JWT из localStorage на fgis.gost.ru, шлёт на token-agent |
| token-agent | FastAPI-сервер, кеширует токен, отдаёт по запросу через Netbird |
| Netbird | P2P mesh VPN (WireGuard), соединяет ПК Зонова с сервером |

### Сеть

| Маршрут | Через что | Куда |
|---------|-----------|------|
| backend → openrouter.ai | NL VPN (awg:8888) | AI extraction |
| backend → fgis.gost.ru/public | напрямую (NO_PROXY) | Публичное API АРШИН |
| backend → token-agent (ПК Зонова) | Netbird mesh VPN | Запрос токена |
| Chrome Extension → token-agent | localhost:8003 | Отправка токена |
| n8n → backend:8000 | docker network | Все API вызовы |

## Полный цикл проверки месяца

### Шаг 1: Триггер

```
Человек → POST /webhook/run-check {year: 2025, month: 12}
  или → ScheduleTrigger (1-е число каждого месяца 09:00)
```

### Шаг 2: Получение ARSHIN токена (при необходимости)

```
Если токен протух:
  n8n → GET /api/v1/arshin/token-status → {"status": "expired"}
  n8n → POST /api/v1/arshin/refresh-token → 202 { "task_id": "abc" }
  n8n → Loop: GET /api/v1/checks/task/abc
         ↓ пока status = "waiting_token"
         ↓ Зонов заходит в ЛК → расширение ловит токен → token-agent кеширует
         ↓ status = "completed"
```

**Как токен попадает на сервер:**
1. Зонов открывает `fgis.gost.ru/fundmetrology/cm/lk` в Chrome
2. Логинится через Госуслуги — SPA получает JWT и сохраняет в localStorage
3. Content script расширения каждые 3 секунды проверяет localStorage по списку ключей
4. При обнаружении значения, начинающегося с `eyJ...`, отправляет в background service worker
5. Service worker делает `POST http://127.0.0.1:8003/token/callback` с токеном
6. token-agent кеширует токен в памяти на 1 час
7. Наш сервер через Netbird вызывает `POST http://100.x.x.x:8003/token/request`
8. Если ответ `{"status": "waiting"}` — сервер спит 30 секунд и повторяет
9. Получив токен — кеширует на 1 час, ретраит отложенные запросы к LK

### Шаг 3: Сбор данных из АРШИН

```
n8n → POST backend:8000/api/v1/arshin/fetch-calibrations {year: 2025, month: 12}

ArshinService.fetch_and_save_calibrations(2025, 12):
  GET https://fgis.gost.ru/fundmetrology/eapi/vri
    ?org_title=ООО "МКАИР"
    &verification_date_start=2025-12-01
    &verification_date_end=2025-12-31
    &rows=100
    ↑ напрямую (NO_PROXY), токен не нужен

  Сохраняет каждую запись в таблицу calibrations
```

### Шаг 4: LK детали (требуют токен)

```
n8n → POST backend:8000/api/v1/arshin/fetch-lk-async {year: 2025, month: 12}
       → 202 { "task_id": "abc" }

Backend в фоне:
  1. Проверяет bearer_token
  2. Если нет → status = "waiting_token", polling token-agent
  3. После получения → качает LK детали для всех калибровок
  4. status = "completed"

n8n → Loop: GET /api/v1/arshin/task/abc → { "status": "completed", "result": {...} }
```

### Шаг 5: Сканирование протоколов

Протоколы хранятся на **Synology Drive** (ПК Зонова):
```
Метрологическая лаборатория\2_Документы внутреннего происхождения\2_19 Протоколы\2025\12\
```

На сервер папка монтируется через **Synology Drive Client** (Linux):
```
/opt/synology-drive/Протоколы/2025/12/   →  смонтировано в /protocols/
```

```
n8n → POST backend:8000/api/v1/protocols/scan {year: 2025, month: 12, path: "/protocols/"}
  Читает папку /protocols/2025.12/, регистрирует PDF
```

### Шаг 6: AI extraction

```
Для каждого PDF (по батчам):
  n8n → POST backend:8000/api/v1/ai/extract { text, model, fallback_models }
  FastAPI AI-proxy: fallback chain через NL VPN
  1. deepseek/deepseek-v4-flash:free (3/3 success, $0)
  2. inclusionai/ring-2.6-1t:free
  3. openai/gpt-oss-120b:free
  4. google/gemma-4-31b-it:free
  5. qwen/qwen3-next-80b-a3b-instruct:free
  6. openai/gpt-4o-mini (платная, ~$0.00028/PDF)
```

### Шаг 7: Проверки (не требуют токена)

```
n8n → POST backend:8000/api/v1/checks/run_async {year: 2025, month: 12}
       → 202 { "task_id": "abc" }

CheckService.run_checks:
  1. Completeness check — все ли калибровки имеют протокол
  2. Protocol found check — все ли протоколы имеют калибровку
  3. Data match check — verifier, date, temperature (±2°C), pressure (±3 kPa)

n8n → Loop: GET /api/v1/checks/task/abc → { "status": "completed", "result": {...} }
```

### Шаг 8: Отчёт

```
n8n → POST backend:8000/api/v1/reports/generate/{run_id}
  Формирует Excel (.xlsx), отправляет на почту
```

## API endpoints (async queue)

| Метод | Endpoint | Тело | Ответ | Описание |
|-------|----------|------|-------|----------|
| POST | /api/v1/checks/run_async | `{year, month}` | `202 {task_id}` | Асинхронный запуск проверок |
| GET | /api/v1/checks/task/{id} | — | `{status, progress, result?}` | Статус задачи (polling) |
| GET | /api/v1/checks/token-status | — | `{status, expires_in}` | Жив ли ARSHIN токен |
| POST | /api/v1/arshin/refresh-token | — | `202 {task_id}` | Запросить новый токен у Зонова |
| POST | /api/v1/arshin/fetch-lk-async | `{year, month}` | `202 {task_id}` | LK детали с ожиданием токена |
| POST | /api/v1/arshin/fetch-data2-async | `{year, month}` | `202 {task_id}` | LK data2 с ожиданием токена |

## Структура репозитория

```
metroCheck/
├── chrome-extension/                # расширение Chrome (устанавливает Зонов)
│   ├── manifest.json
│   ├── content.js
│   └── background.js
├── token-agent/                     # программа для ПК Зонова
│   ├── main.py
│   ├── requirements.txt
│   ├── token-agent.service          # systemd (Linux)
│   └── build_exe.bat                # сборка .exe (Windows)
├── backend/                         # FastAPI сервер
│   ├── app/
│   │   ├── api/v1/routes/
│   │   │   ├── ai.py                # AI-proxy (fallback chain)
│   │   │   ├── arshin.py            # ARSHIN + token endpoints
│   │   │   ├── checks.py            # async queue + checks
│   │   │   ├── protocols.py
│   │   │   ├── reports.py
│   │   │   └── health.py
│   │   ├── integrations/
│   │   │   └── arshin_client.py     # ARSHIN API + token polling
│   │   ├── services/
│   │   │   ├── check_service.py
│   │   │   ├── arshin_service.py
│   │   │   ├── task_manager.py      # async queue (in-memory)
│   │   │   └── protocol_scanner.py
│   │   ├── models/                  # SQLAlchemy модели
│   │   └── repositories/           # DB репозитории
│   └── tests/
│       └── test_check_service.py    # 18 тестов
├── n8n/
│   ├── workflows/*.json             # 5 workflow
│   └── awg-config/                  # NL VPN конфиг
├── docker-compose.yml
├── ARCHITECTURE.md
└── TOKEN_SPEC.md
```

## Protocol storage (Synology Drive)

```
Synology Drive (Windows, ПК Зонова)
  ↓ синхронизация через Synology Drive Client
Synology NAS (центральное хранилище)
  ↓ монтирование на сервере через Synology Drive Client (Linux)
/opt/synology-drive/Протоколы/2025/12/  (на сервере)
  ↓ монтировано в Docker контейнер backend
/protocols/2025/12/  (внутри контейнера)
```

**Путь на Synology Drive (Windows):**
```
Метрологическая лаборатория\2_Документы внутреннего происхождения\2_19 Протоколы\{year}\{month}\
```

Внутри могут быть подпапки — сканер рекурсивно ищет PDF.

## Fallback chain AI моделей

- **Selenium отменён** — Chrome Extension вместо него (не мешает работе)
- **NL VPN** для OpenRouter (AWG, userspace), ARSHIN напрямую через NO_PROXY
- **Бесплатные AI модели** — deepseek-v4-flash:free обрабатывает 3/3 PDF, $0
- **async queue** — все долгие операции через task_id + polling (n8n не зависает)
- **Netbird** — P2P mesh VPN без открытых портов для связи с ПК Зонова
- **token-agent** — скомпилирован в .exe для Windows (Python не нужен)
