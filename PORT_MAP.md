# MKAIR Infrastructure Map
## Сервер: mkair-server | Netbird: 100.89.59.195

---

## Быстрые ссылки (UI)

| Сервис | URL | Описание |
|--------|-----|----------|
| metroCheck Backend | http://100.89.59.195:8002 | API + UI очереди проверок |
| metroCheck n8n | http://100.89.59.195:5681 | n8n workflows |
| metroLog Frontend | http://100.89.59.195:5173 | UI метрологии |
| metroGen Frontend | http://100.89.59.195:5174 | UI генерации |
| Grafana | http://192.168.1.84:8090 | Мониторинг |

---

## Сеть: Netbird VPN

| Узел | Netbird IP | Роль |
|------|-----------|------|
| **mkair-server** | 100.89.59.195 | Главный сервер (Docker) |
| **mflkee-notebook** | 100.104.105.63 | Разработка metroCheck |
| **Зонов ПК** | 100.89.96.31 | Token Agent ARSHIN (порт 8003) |

---

## Проект: metroCheck (~/apps/metroCheck)

### Docker контейнеры

| Контейнер | Внутр. IP | Внутр. порт | Хост порт | Статус |
|-----------|----------|-------------|-----------|--------|
| mkair_backend | 172.19.0.4 | 8000 | **8002** | Up (healthy) |
| mkair_postgres | 172.19.0.3 | 5432 | **5434** | Up (healthy) |
| mkair_redis | 172.19.0.2 | 6379 | **6382** | Up (healthy) |
| mkair_n8n | 172.19.0.5 | 5678 | **5681** | Up |

### Сети Docker

```
metrocheck_backend_network: 172.19.0.0/16
metrocheck_mkair_network:   172.18.0.0/16
```

### Доступ

- **API**: http://100.89.59.195:8002/api/v1
- **UI очереди**: http://100.89.59.195:8002/
- **Health**: http://100.89.59.195:8002/health
- **n8n**: http://100.89.59.195:5681

### База данных (внутри сети)

```
Host: mkair_postgres:5432
User: mkair
Pass: mkair_secret
DB:   mkair
```

---

## Проект: metroLog (~/apps/metrolog)

### Docker контейнеры

| Контейнер | Внутр. IP | Внутр. порт | Хост порт | Статус |
|-----------|----------|-------------|-----------|--------|
| metrolog-backend-1 | 172.20.0.5 | 8000 | **8000** | Up |
| metrolog-backend-worker-1 | 172.20.0.4 | 8000 | - | Up |
| metrolog-postgres-1 | 172.20.0.2 | 5432 | **5432** | Up |
| metrolog-redis-1 | 172.20.0.3 | 6379 | **6379** | Up |
| metrolog-frontend-1 | 172.20.0.6 | 80 | **5173** | Up |

### Сеть Docker

```
metrolog_default: 172.20.0.0/16
```

### Доступ

- **Backend API**: http://100.89.59.195:8000
- **Frontend UI**: http://100.89.59.195:5173

---

## Проект: metroGen (~/apps/metrogen)

### Docker контейнеры

| Контейнер | Внутр. IP | Внутр. порт | Хост порт | Статус |
|-----------|----------|-------------|-----------|--------|
| metrogen-api-1 | 172.21.0.3 | 8000 | **8001** | Up (healthy) |
| metrogen-db-1 | 172.21.0.2 | 5432 | **5433** | Up (healthy) |
| metrogen-frontend-1 | 172.21.0.4 | 80 | **5174** | Up |

### Сеть Docker

```
metrogen_default: 172.21.0.0/16
```

### Доступ

- **API**: http://100.89.59.195:8001
- **Frontend UI**: http://100.89.59.195:5174

---

## Мониторинг (~/apps/monitoring)

| Контейнер | Внутр. IP | Внутр. порт | Хост порт | Статус |
|-----------|----------|-------------|-----------|--------|
| monitoring-grafana-1 | - | 3000 | **192.168.1.84:8090** | Up |
| monitoring-prometheus-1 | - | 9090 | **127.0.0.1:9091** | Up |
| monitoring-cadvisor-1 | - | 8080 | **127.0.0.1:8080** | Up |
| monitoring-alertmanager-1 | - | 9093 | **127.0.0.1:9093** | Up |
| monitoring-blackbox-exporter-1 | - | 9115 | **127.0.0.1:9115** | Up |
| monitoring-node-exporter-1 | - | 9100 | **9100** (host) | Up |

### Доступ

- **Grafana**: http://192.168.1.84:8090
- **Prometheus**: http://127.0.0.1:9091 (только локально)
- **cAdvisor**: http://127.0.0.1:8080 (только локально)

---

## Внешние узлы (Netbird)

| Узел | Netbird IP | Сервис | Порт | Описание |
|------|-----------|--------|------|----------|
| **Зонов ПК** | 100.89.96.31 | token-agent | 8003 | FastAPI, хранит ARSHIN токен |

### Проверка token-agent с сервера

```bash
curl -X POST http://100.89.96.31:8003/token/request \
  -H "X-API-Key: mkair-token-agent-key"
```

---

## Занятые порты (mkair-server)

```
# Публичные (0.0.0.0)
5432  — metroLog PostgreSQL
5433  — metroGen PostgreSQL
5434  — metroCheck PostgreSQL
6379  — metroLog Redis
6382  — metroCheck Redis
8000  — metroLog Backend
8001  — metroGen API
8002  — metroCheck Backend
5681  — metroCheck n8n
5173  — metroLog Frontend
5174  — metroGen Frontend
8090  — Grafana (192.168.1.84)

# Только localhost
8080  — cAdvisor
9091  — Prometheus
9093  — Alertmanager
9115  — Blackbox Exporter
9100  — Node Exporter
```

---

## CI/CD (GitHub Actions)

- **Trigger**: push в main или manual dispatch
- **Runner**: self-hosted на mkair-server (тег: mkair)
- **Workflow**: .github/workflows/deploy.yml
- **Команда деплоя**: `docker compose up -d --build`

### Проверить статус деплоя

```bash
ssh mflkee@100.89.59.195
cd ~/apps/metroCheck
docker compose ps
docker compose logs -f backend
```

---

## SSH Доступ

```bash
ssh mflkee@100.89.59.195
# Пароль: 7405
```

---

## Печатать и положить рядом с сервером
