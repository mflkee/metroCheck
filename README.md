# metroCheck — Система контроля протоколов МКАИР

Автоматизированная система проверки протоколов поверки ООО «МКАИР» с интеграцией в АРШИН (ФГИС «Росаккредитация»).

## Возможности

- **Автоматическая проверка протоколов** — загрузка и валидация протоколов поверки из АРШИН
- **Проверка серийных номеров** — нечеткий поиск и валидация серийных номеров оборудования
- **Асинхронная обработка** — очередь задач с отслеживанием прогресса
- **Мониторинг в реальном времени** — веб-интерфейс со статусом системы, прогресс-барами и журналом ошибок
- **Удаленное получение токена** — Chrome-расширение + token-agent на ПК оператора для автоматической передачи токена АРШИН
- **Email-отчеты** — HTML-отчеты после завершения проверок
- **Интеграция с n8n** — воркфлоу для автоматизации бизнес-процессов

## Архитектура

```
metroCheck-server (Тюмень)                    ПК оператора (Нижневартовск)
├─ Docker Compose                        ├─ Chrome + Расширение
│  ├─ PostgreSQL 16                      ├─ token-agent :8003
│  ├─ Redis 7                                (FastAPI, хранит токен)
│  ├─ Backend (FastAPI)                  
│  │  ├─ Job Queue Service               
│  │  ├─ Health Monitor                  
│  │  ├─ ArshinClient                    
│  │  └─ Email Service                   
│  └─ Monitoring UI (/)                  
│                                         
Synology Drive       ◄──────────────────────►
```

## Структура репозитория

```
metroCheck/
├── backend/                 # FastAPI приложение
│   ├── app/
│   │   ├── api/v1/routes/   # API endpoints
│   │   ├── services/        # Бизнес-логика (JobQueue, HealthMonitor, Email)
│   │   ├── integrations/    # Внешние интеграции (ARSHIN, OpenRouter)
│   │   ├── static/          # Веб-интерфейс мониторинга
│   │   └── models/          # SQLAlchemy модели
│   ├── tests/               # Тесты
│   ├── alembic/             # Миграции БД
│   └── Dockerfile
├── chrome-extension/        # Расширение Chrome для захвата токена АРШИН
│   ├── manifest.json
│   ├── content.js
│   └── background.js
├── token-agent/             # Агент на ПК оператора (FastAPI)
│   ├── main.py
│   ├── requirements.txt
│   └── token-agent.service  # systemd unit
├── docs/                    # Документация и спецификации
│   ├── ARCHITECTURE.md
│   ├── TOKEN_SPEC.md
│   ├── Спецификация_приложения.md
│   ├── Этапы_проектирования.md
│   └── ...
├── data/                    # Данные и документы
├── protocols/               # PDF протоколов (в .gitignore)
├── docker-compose.yml       # Основная оркестрация
└── README.md
```

## Быстрый старт

### Требования

- Docker + Docker Compose
- Netbird VPN (для связи с ПК оператора)
- Python 3.11+ (для локальной разработки)

### Запуск

```bash
# 1. Клонировать репозиторий
git clone <repo-url>
cd metroCheck

# 2. Создать .env файл
cp .env.example .env
# Отредактировать переменные окружения

# 3. Запустить
docker-compose up -d

# 4. Применить миграции
cd backend
alembic upgrade head
```

### Доступ к сервисам

| Сервис | URL | Описание |
|--------|-----|----------|
| Backend API | http://localhost:8002 | FastAPI + документация Swagger |
| Monitoring UI | http://localhost:8002/ | Дашборд мониторинга |
| n8n | http://localhost:5681 | Воркфлоу автоматизации |
| PostgreSQL | localhost:5434 | База данных |
| Redis | localhost:6382 | Кеш и очередь |

## Компоненты системы

### Backend

- **Job Queue** — асинхронная очередь задач с приоритетом (авто/ручной), прогресс-бар для каждого устройства
- **Health Monitor** — проверка доступности ARSHIN API, token-agent, OpenRouter, n8n
- **ArshinClient** — интеграция с АРШИН через OpenRouter для обхода ограничений
- **Email Service** — HTML email-отчеты после проверок

### Token Relay

Токен АРШИН живет ~1 час и требует ручного логина через Госуслуги. Для автоматизации:

1. **Chrome Extension** — перехватывает токен из localStorage при логине на fgis.gost.ru
2. **token-agent** — получает токен от расширения и отдает серверу через Netbird VPN
3. **ArshinClient** — запрашивает токен у агента при необходимости

### Job Queue

- Только одна проверка одновременно
- Ручные задачи имеют приоритет над автоматическими
- Автоматическая проверка 1-го числа каждого месяца в 09:00
- Ожидание токена в процессе проверки (не прерывает задачу)

## Разработка

### Стек технологий

- **Backend**: FastAPI, SQLAlchemy (async), Alembic, Pydantic
- **Queue**: Redis + asyncio
- **Frontend**: Vanilla JS (мониторинг UI)
- **Chrome Extension**: Manifest V3
- **Token Agent**: FastAPI + uvicorn
- **Infra**: Docker Compose, Netbird VPN

### Тестирование

```bash
cd backend
pytest
```

## Документация

Подробная документация в папке `docs/`:

- `ARCHITECTURE.md` — Архитектура системы
- `TOKEN_SPEC.md` — Спецификация получения токена АРШИН
- `Спецификация_приложения.md` — Требования к приложению
- `Этапы_проектирования.md` — Этапы разработки

## Лицензия

Внутренний проект ООО «МКАИР». Все права защищены.
