# MetroCheck — Port Mapping & Infrastructure

## Сервер: mkair-server (100.89.59.195)
Пароль: `<PASSWORD>`, пользователь: `mflkee`, VPN: Netbird

## Docker Services — Production

| Service | Container Name | Internal Port | External Port | Description |
|---------|---------------|--------------|---------------|-------------|
| Backend | `metroCheck_backend` | 8000 | **8002** | FastAPI |
| Frontend | `metroCheck_frontend` | 80 | **8081** | React (Vite) + nginx |
| PostgreSQL | `metroCheck_postgres` | 5432 | **5434** | Database (db: `mkair`) |
| Redis | `metroCheck_redis` | 6379 | **6382** | Cache & queue |

## Docker Services — Staging

| Service | Container Name | Internal Port | External Port | Description |
|---------|---------------|--------------|---------------|-------------|
| Backend | `metroCheck_backend_stg` | 8000 | **9002** | FastAPI |
| Frontend | `metroCheck_frontend_stg` | 80 | **9081** | React (Vite) + nginx |
| PostgreSQL | `metroCheck_postgres_stg` | 5432 | **5435** | Database (db: `mkair_stg`) |
| Redis | `metroCheck_redis_stg` | 6379 | **6383** | Cache & queue |

## API Endpoints (Backend)

Все эндпоинты требуют заголовок `x-api-key`.

### Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Основной healthcheck |
| GET | `/health/live` | Liveness probe |

### ARSHIN (`/api/v1/arshin/`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/status` | Статус API АРШИН |
| GET | `/token-status` | Статус токена ЛК |
| POST | `/refresh-token` | Запросить новый токен (async) |
| GET | `/task/{id}` | Статус асинхронной задачи |
| POST | `/fetch-calibrations` | Загрузить калибровки (sync) |
| POST | `/fetch-lk-details` | LK детали (sync) |
| POST | `/fetch-lk-data2` | LK data2 (sync) |
| POST | `/fetch-lk-async` | LK детали (async) |
| POST | `/fetch-data2-async` | LK data2 (async) |
| GET | `/scheduler/status` | Статус scheduler |
| POST | `/scheduler/mode` | Режим manual/auto |
| POST | `/scheduler/settings` | Настройки scheduler |
| GET | `/scheduler/emails` | Список email для отчётов |
| POST | `/scheduler/emails` | Добавить email |
| DELETE | `/scheduler/emails/{id}` | Удалить email |

### Jobs (`/api/v1/jobs/`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/enqueue` | Создать ручную задачу |
| POST | `/enqueue-auto` | Создать авто-задачу |
| GET | `/status` | Список задач |
| GET | `/{id}` | Детали задачи |
| POST | `/{id}/pause` | Пауза |
| POST | `/{id}/resume` | Возобновить |
| POST | `/{id}/cancel` | Отмена |
| DELETE | `/{id}` | Удалить |
| POST | `/{id}/generate-report` | Сгенерировать отчёт |
| GET | `/{id}/download-report` | Скачать отчёт |

### Checks (`/api/v1/checks/`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/run` | Запустить проверку (sync) |
| POST | `/run_async` | Запустить проверку (async) |
| GET | `/task/{id}` | Статус задачи |
| GET | `/results/{id}` | Результаты |

## Synology Drive Sync

| Local Path | Remote | Description |
|------------|--------|-------------|
| `/home/mflkee/SynologyDrive/2025/` | NAS | Протоколы по месяцам |
| `/home/mflkee/SynologyDrive/tokens/` | NAS | Токены АРШИН |
| `/home/mflkee/SynologyDrive/2022/` | NAS | Архив |
| `/home/mflkee/SynologyDrive/2023/` | NAS | Архив |
| `/home/mflkee/SynologyDrive/2024/` | NAS | Архив |

**Mount в контейнере:**
- `/home/mflkee/SynologyDrive/2025/` → `/protocols/` (ro)
- `/home/mflkee/SynologyDrive/tokens/` → `/shared/tokens/`

## Monitoring (отдельный Docker Compose в ~/apps/monitoring/)

| Service | Port | URL |
|---------|------|-----|
| Grafana | 3000 → 8090 | http://192.168.1.84:8090 |
| Prometheus | 9090 → 9091 | http://127.0.0.1:9091 |
| cAdvisor | 8080 | http://127.0.0.1:8080 |
| Node Exporter | 9100 | — |
| Alertmanager | 9093 | — |
| Blackbox | 9115 | — |

## Scheduler Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `mode` | `manual` | Режим: manual / auto |
| `auto_day` | 1 | День месяца для авто-запуска |
| `auto_time` | 09:00 | Время авто-запуска |
| `month_offset` | -1 | Смещение месяца (-12..0) |

## Firewall

| Port | Service | Access |
|------|---------|--------|
| 8002 | Backend (prod) | LAN + VPN |
| 8081 | Frontend (prod) | LAN + VPN |
| 9002 | Backend (staging) | LAN + VPN |
| 9081 | Frontend (staging) | LAN + VPN |
| 5434 | PostgreSQL (prod) | localhost only |
| 5435 | PostgreSQL (staging) | localhost only |
| 6382 | Redis (prod) | localhost only |
| 6383 | Redis (staging) | localhost only |
| 8090 | Grafana | LAN + VPN |

## Quick Deploy

### Staging (авто)
```bash
git push origin main
# → GitHub Actions само задеплоит
```

### Staging (ручное пересоздание)
```bash
sshpass -p "$SSH_PASSWORD" ssh mflkee@mkair-server 'cd ~/apps/metroCheck && docker compose -f docker-compose.staging.yml down && docker compose -f docker-compose.staging.yml up -d --build && docker compose -f docker-compose.staging.yml run --no-deps --rm backend alembic upgrade head'
```

### Production
```bash
# GitHub UI → Actions → Promote to Production → type "deploy"
# Или:
git checkout -b release/v1.x.x && git push origin release/v1.x.x
```
