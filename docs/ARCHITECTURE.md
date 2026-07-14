# Архитектура MetroCheck

## Диаграмма потоков

```
                    Сервер (Docker Compose)
                    ┌──────────────────────────────────────────────┐
                    │  backend_network (bridge)                    │
                    │                                              │
                    │  ┌──────────┐      ┌──────────┐              │
                    │  │ postgres │◄────►│  redis   │              │
                    │  │ :5434/5  │      │ :6382/3  │              │
                    │  └────┬─────┘      └──────────┘              │
                    │       │                                      │
                    │  ┌────▼─────────────────────────┐            │
                    │  │         backend               │            │
                    │  │  FastAPI :8002/9002            │            │
                    │  │                                │            │
                    │  │  ┌───────────────────────┐    │            │
                    │  │  │ JobQueueService        │    │            │
                    │  │  │ 8-phase pipeline:      │    │            │
                    │  │  │ public_api → scan →    │    │            │
                    │  │  │ OCR → extract →        │    │            │
                    │  │  │ partial_check →        │    │            │
                    │  │  │ wait_token → lk_api →  │    │            │
                    │  │  │ full_check → report    │    │            │
                    │  │  └───────────────────────┘    │            │
                    │  │                                │            │
                    │  │  ┌───────────────────────┐    │            │
                    │  │  │ ArshinService          │    │            │
                    │  │  │ ├─ public API (no auth)│    │            │
                    │  │  │ └─ LK API (Bearer)    │    │            │
                    │  │  └───────────────────────┘    │            │
                    │  │                                │            │
                    │  │  ┌───────────────────────┐    │            │
                    │  │  │ ProtocolScanner        │    │            │
                    │  │  │ ├─ рекурсивный поиск   │    │            │
                    │  │  │ └─ Tesseract OCR       │    │            │
                    │  │  └───────────────────────┘    │            │
                    │  │                                │            │
                    │  │  ┌───────────────────────┐    │            │
                    │  │  │ ExtractionService      │    │            │
│  │  │ ├─ regex (primary)     │    │            │
│  │  │ └─ OpenRouter (fallback, │   │            │
│  │  │    все поля при None)   │   │            │
                    │  │  └───────────────────────┘    │            │
                    │  └───────────┬───────────────────┘            │
                    │              │                                │
                    │  ┌───────────▼────────────┐                   │
                    │  │    frontend (nginx)     │                   │
                    │  │    :8081/9081           │                   │
                    │  └────────────────────────┘                   │
                    └──────────────────────────────────────────────┘
                              │
              ┌───────────────┼──────────────────────┐
              ▼               ▼                      ▼
    fgis.gost.ru      openrouter.ai            Synology NAS
    (АРШИН API)        (AI модели)               (протоколы + токены)
                                                     │
                                            Synology Drive Client
                                                     │
                                              Сервер (mount):
                                        /home/mflkee/SynologyDrive/
                                        ├── 2025/{месяц}/         ← протоколы
                                        └── tokens/jwt-arshin-lk.json ← токен
```

## Компоненты

### Серверная часть (Docker)

| Контейнер | Порт (prod/stg) | Назначение |
|-----------|-----------------|------------|
| postgres | 5434 / 5435 | PostgreSQL 16 |
| redis | 6382 / 6383 | Redis 7 (очередь + кэш) |
| backend | 8002 / 9002 | FastAPI приложение |
| frontend | 8081 / 9081 | nginx статика |

### Сеть

| Маршрут | Через что | Куда |
|---------|-----------|------|
| backend → fgis.gost.ru (public) | HTTPS напрямую | Публичное API АРШИН |
| backend → fgis.gost.ru (LK) | HTTPS + Bearer token | ЛК АРШИН |
| backend → openrouter.ai | HTTPS напрямую | AI extraction |
| Synology Drive (сервер) ↔ NAS | Synology собств. протокол | Синхронизация файлов |
| сервер ↔ ПК Зонова | Netbird mesh VPN (WireGuard P2P) | Токен АРШИН |

### Клиентская часть (ПК Зонова)

| Компонент | Назначение |
|-----------|-----------|
| Chrome Extension | Читает JWT из localStorage на fgis.gost.ru, пишет в Synology Drive |
| Synology Drive Client | Синхронизирует токены + протоколы с NAS |
| Netbird peer | P2P mesh VPN (WireGuard) для связи с сервером |

## 8-фазный пайплайн

```
Пользователь → POST /api/v1/jobs/enqueue {year, month}
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                   JobQueueService._execute_job()                 │
│                                                                  │
│  Phase 1: public_api                                             │
│    ArshinService.fetch_and_save_calibrations(year, month)        │
│    → GET fgis.gost.ru/eapi/vri?org_title=МКАИР&date=...         │
│    → сохраняет в calibrations                                    │
│    progress: ~5% → 20%                                           │
│                                                                  │
│  Phase 2: protocol_scan                                          │
│    ProtocolScanner.scan(year, month)                             │
│    → рекурсивный поиск PDF по /protocols/{year}.{month}/         │
│    → SHA256, регистрация в protocol_files                        │
│    progress: ~20% → 30%                                          │
│                                                                  │
│  Phase 3: protocol_ocr                                           │
│    ProtocolScanner.extract_text(proto.id)                        │
│    → Tesseract OCR (rus) с таймаутом 30 сек                     │
│    → raw_text → protocol_files                                   │
│    progress: ~30% → 50%                                          │
│                                                                  │
│  Phase 4: data_extract                                           │
│    ProtocolExtractionService.extract(text, filename, path)       │
│    → regex (primary) + OpenRouter (fallback для любых полей)    │
│    → AI_FALLBACK лог: file, поля, snippet текста для ручного    │
│      добавления паттернов                                        │
│    → поля: device_name, type, serial, verifier, method, range... │
│    → сохраняет в protocol_data                                    │
│    progress: ~50% → 65%                                          │
│                                                                  │
│  Phase 5: partial_check                                          │
│    CheckService.run_checks(year, month)                          │
│    → сверка serial_number с calibrations                         │
│    → проверка полноты, соответствия                               │
│    progress: ~65% → 80%                                          │
│                                                                  │
│  Phase 6: wait_token  ← если токен протух                        │
│    → мониторинг /shared/tokens/jwt-arshin-lk.json                 │
│    → ждём, пока Зонов обновит токен через Synology Drive         │
│    progress: 80% (фикс)                                          │
│                                                                  │
│  Phase 7: lk_api ← только с токеном                              │
│    ArshinService.fetch_lk_details(), fetch_data2()               │
│    → обогащение calibrations данными из ЛК                       │
│    progress: ~80% → 90%                                          │
│                                                                  │
│  Phase 8: full_check + report                                    │
│    CheckService.full_check()                                     │
│    ReportService.generate_report()                               │
│    EmailService.send()                                           │
│    progress: ~90% → 100%                                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## API endpoints

### Управление задачами (`/api/v1/jobs/`)

| Метод | Endpoint | Тело | Описание |
|-------|----------|------|----------|
| POST | `/enqueue` | `{year, month}` | Создать ручную задачу |
| POST | `/enqueue-auto` | `{year, month}` | Создать авто-задачу |
| GET | `/status` | — | Список всех задач |
| GET | `/{id}` | — | Детали задачи |
| POST | `/{id}/pause` | — | Пауза |
| POST | `/{id}/resume` | — | Возобновить |
| POST | `/{id}/cancel` | — | Отмена |
| DELETE | `/{id}` | — | Удалить |
| POST | `/{id}/generate-report` | — | Сгенерировать отчёт |
| GET | `/{id}/download-report` | — | Скачать отчёт |

### АРШИН (`/api/v1/arshin/`)

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/status` | Статус API АРШИН |
| GET | `/token-status` | Статус токена ЛК |
| POST | `/refresh-token` | Запросить новый токен |
| GET | `/task/{id}` | Статус асинхронной задачи |
| POST | `/fetch-lk-async` | LK детали (async) |
| POST | `/fetch-data2-async` | LK data2 (async) |
| POST | `/fetch-calibrations` | Калибровки (синхр.) |
| POST | `/fetch-lk-details` | LK детали (синхр.) |
| POST | `/fetch-lk-data2` | LK data2 (синхр.) |
| GET | `/scheduler/status` | Статус scheduler |
| POST | `/scheduler/mode` | Режим manual/auto |
| POST | `/scheduler/settings` | Настройки scheduler |

## Структура репозитория

```
metroCheck/
├── backend/
│   ├── app/
│   │   ├── api/v1/routes/       # FastAPI endpoints
│   │   ├── services/            # Бизнес-логика
│   │   ├── models/              # SQLAlchemy модели
│   │   ├── repositories/        # DB слой
│   │   ├── integrations/        # Внешние API
│   │   └── core/                # config, database, dependencies
│   ├── scripts/                 # Утилиты (run_extraction_test.py)
│   ├── Dockerfile
│   └── pyproject.toml
├── chrome-extension/            # Расширение для Chrome (Зонов)
│   ├── manifest.json
│   ├── content.js
│   └── background.js
├── docs/                        # Документация
├── docker-compose.yml           # Production стек
├── docker-compose.staging.yml   # Staging стек
├── nginx.conf                   # nginx конфиг
└── .github/workflows/           # CI/CD
    ├── staging.yml              # Авто-деплой staging
    ├── deploy.yml               # Production deploy
    └── promote.yml              # Promote staging→production
```

## Хранение протоколов (Synology Drive)

```
ПК Зонова (Windows)
  └── Synology Drive Client
       └── Метрологическая лаборатория/2_Документы внутреннего происхождения/
           2_19 Протоколы/{year}/{month}/
           └── (PDF + вложенные папки)

NAS (Synology)
  └── зеркало с ПК Зонова

Сервер (Linux)
  └── Synology Drive Client
       └── /home/mflkee/SynologyDrive/2025/{month}/
            └── смонтировано в контейнер как /protocols/2025.{month}/
```

## CI/CD

### Staging (GitHub Actions)
- `git push origin main` → auto-deploy на `:9002/:9081/:5435/:6383`
- `docker compose -f docker-compose.staging.yml down && up -d --build`
- `alembic upgrade head`
- Healthcheck через `/health`

### Production
- **Promote:** GitHub UI → Actions workflow → type "deploy"
- **Release:** `git push origin release/*` → `deploy.yml`
- Требуется reviewer (`mflkee`), 5 min wait timer

## Токен АРШИН ЛК

```
Chrome Extension (content.js)
  → читает localStorage на fgis.gost.ru
  → находит JWT (начинается с eyJ...)
  → background.js → пишет в SynologyDrive/tokens/jwt-arshin-lk.json

Synology Drive (Windows → NAS → Linux)
  → синхронизация файла на сервер

Сервер
  /home/mflkee/SynologyDrive/tokens/jwt-arshin-lk.json
  → монтируется в контейнер как /shared/tokens/jwt-arshin-lk.json
  → Backend читает, парсит, кеширует
  → Использует для LK запросов
  → Архивация использованных токенов в .used файлы
```
