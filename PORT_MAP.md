# MKAIR Server — mkair-server (Netbird: 100.89.59.195)

## Быстрые ссылки

| Сервис | URL |
|--------|-----|
| metroCheck | http://100.89.59.195:8002 |
| metroLog | http://100.89.59.195:5173 |
| metroGen | http://100.89.59.195:5174 |
| Grafana | http://192.168.1.84:8090 |
| n8n | http://100.89.59.195:5681 |

---

## Сеть

| Узел | Netbird IP | Порт | Описание |
|------|-----------|------|----------|
| mkair-server | 100.89.59.195 | — | Главный сервер |
| Token Agent | 100.89.96.31 | 8003 | ARSHIN токен (ПК Зонова) |

---

## Docker контейнеры

### metroCheck (~/apps/metroCheck)

| Контейнер | Внутр. IP | Внутр. порт | Хост порт |
|-----------|----------|-------------|-----------|
| metroCheck_backend | 172.19.0.4 | 8000 | **8002** |
| metroCheck_postgres | 172.19.0.3 | 5432 | **5434** |
| metroCheck_redis | 172.19.0.2 | 6379 | **6382** |
| metroCheck_n8n | 172.19.0.5 | 5678 | **5681** |

### metroLog (~/apps/metrolog)

| Контейнер | Внутр. IP | Внутр. порт | Хост порт |
|-----------|----------|-------------|-----------|
| metroLog_backend | 172.20.0.5 | 8000 | **8000** |
| metroLog_worker | 172.20.0.4 | — | — |
| metroLog_postgres | 172.20.0.2 | 5432 | **5432** |
| metroLog_redis | 172.20.0.3 | 6379 | **6379** |
| metroLog_frontend | 172.20.0.6 | 80 | **5173** |

### metroGen (~/apps/metrogen)

| Контейнер | Внутр. IP | Внутр. порт | Хост порт |
|-----------|----------|-------------|-----------|
| metroGen_api | 172.21.0.3 | 8000 | **8001** |
| metroGen_db | 172.21.0.2 | 5432 | **5433** |
| metroGen_frontend | 172.21.0.4 | 80 | **5174** |

### metroMonitoring (~/apps/monitoring)

| Контейнер | Внутр. порт | Хост порт | Доступ |
|-----------|-------------|-----------|--------|
| metroMonitoring_grafana | 3000 | **8090** (192.168.1.84) | Публичный |
| metroMonitoring_prometheus | 9090 | **127.0.0.1:9091** | Только localhost |
| metroMonitoring_cadvisor | 8080 | **127.0.0.1:8080** | Только localhost |
| metroMonitoring_alertmanager | 9093 | **127.0.0.1:9093** | Только localhost |
| metroMonitoring_blackbox | 9115 | **127.0.0.1:9115** | Только localhost |
| metroMonitoring_node | 9100 | **9100** | Host network |

---

## Порты (mkair-server)

```
8000  — metroLog
8001  — metroGen
8002  — metroCheck
5432  — metroLog PostgreSQL
5433  — metroGen PostgreSQL
5434  — metroCheck PostgreSQL
6379  — metroLog Redis
6382  — metroCheck Redis
5681  — metroCheck n8n
5173  — metroLog Frontend
5174  — metroGen Frontend
8090  — Grafana (192.168.1.84)
9091  — Prometheus (localhost)
9093  — Alertmanager (localhost)
8080  — cAdvisor (localhost)
9115  — Blackbox (localhost)
9100  — Node Exporter
```

---

## Управление

```bash
# SSH
ssh mflkee@100.89.59.195
# Пароль: 7405

# Docker (автозагрузка включена)
ssh mflkee@100.89.59.195 "docker compose ps"

# Проверить статус
ssh mflkee@100.89.59.195 "docker compose ps"
```

---

## CI/CD

GitHub Actions → self-hosted runner (mkair) → `docker compose up -d --build`

## Печатать и положить рядом с сервером
