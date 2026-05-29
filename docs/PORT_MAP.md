# MKAIR Server — Port Mapping & Infrastructure

## Server: mkair-server (100.89.59.195)

## Docker Services

| Service | Container | Internal Port | External Port | URL | Description |
|---------|-----------|--------------|---------------|-----|-------------|
| **Frontend (nginx)** | metroCheck_frontend | 80 | 8080 | http://100.89.59.195:8080 | Web UI мониторинга |
| **Backend API** | metroCheck_backend | 8000 | 8002 | http://100.89.59.195:8002 | FastAPI + API endpoints |
| **PostgreSQL** | metroCheck_postgres | 5432 | 5434 | localhost only | База данных |
| **Redis** | metroCheck_redis | 6379 | 6382 | localhost only | Очередь и кэш |
| **n8n** | metroCheck_n8n | 5678 | 5681 | http://100.89.59.195:5681 | Воркфлоу автоматизации |

## API Endpoints (Backend :8002)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/health` | GET | Health check |
| `/api/v1/arshin/status` | GET | ARSHIN API status |
| `/api/v1/arshin/token-status` | GET | Token status |
| `/api/v1/arshin/scheduler/status` | GET | Scheduler status |
| `/api/v1/arshin/scheduler/mode` | POST | Set scheduler mode (manual/auto) |
| `/api/v1/arshin/scheduler/settings` | POST | Configure scheduler settings |
| `/api/v1/arshin/run-check` | POST | Manual check trigger |
| `/api/v1/arshin/refresh-token` | POST | Request new token |
| `/api/v1/arshin/task/{id}` | GET | Task status |
| `/api/v1/jobs/queue` | GET | Job queue status |
| `/api/v1/checks/results/{id}` | GET | Check results |

## Synology Drive Sync

| Local Path | Sync Direction | Remote | Description |
|------------|---------------|--------|-------------|
| `/home/mflkee/SynologyDrive/` | ↔ | NAS | Протоколы (2022-2026) |
| `/home/mflkee/SynologyDrive/tokens/` | ↔ | NAS | Токены АРШИН |

## Token Flow

```
ПК Зонова (Нижневартовск)
  ├─ Chrome Extension → fgis.gost.ru
  ├─ Token Agent → C:/Users/Зонов/SynologyDrive/tokens/arshin-token.json
  └─ Synology Drive Client → NAS

NAS (Synology)
  └─ Облачное хранилище

mkair-server (Тюмень)
  ├─ Synology Drive Client → /home/mflkee/SynologyDrive/tokens/
  ├─ Docker Volume Mount → /shared/tokens/
  └─ Backend читает → arshin-token.json
```

## Scheduler Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `mode` | `manual` | Режим: manual или auto |
| `auto_day` | 1 | День месяца для авто-проверки |
| `auto_time` | 09:00 | Время авто-проверки (HH:MM) |
| `month_offset` | -1 | Смещение месяца (-12 до 0) |

## Firewall

| Port | Service | Access |
|------|---------|--------|
| 8080 | Frontend | LAN + VPN |
| 8002 | Backend API | LAN + VPN |
| 5681 | n8n | LAN + VPN |
| 5434 | PostgreSQL | localhost only |
| 6382 | Redis | localhost only |

## Deployment

```bash
cd ~/apps/metroCheck
git pull origin main
docker compose up -d --build
docker compose exec backend alembic upgrade head
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Token not found | Check SynologyDrive sync status |
| Scheduler not running | Check mode: `GET /api/v1/arshin/scheduler/status` |
| Database errors | Run migrations: `alembic upgrade head` |
| Backend unhealthy | Check logs: `docker logs metroCheck_backend` |
