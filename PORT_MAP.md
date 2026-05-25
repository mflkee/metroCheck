# Port Map — проекты MKAIR

## Локальные проекты (`~/projects/`)

| Проект | Сервис | Внутр. порт | Хост порт | Статус |
|--------|--------|-------------|-----------|--------|
| **metroLog** | PostgreSQL | 5432 | 5432 | ✅ |
| | Redis | 6379 | 6379 | ✅ |
| | Backend (FastAPI) | 8000 | 8000 | ✅ |
| | Backend Worker | — | — | ✅ |
| | Frontend | 80 | 5173 | ❌ выключен |
| **metroSearch** | App | 8000 | 8000 | ❌ выключен |
| **metroGen** | PostgreSQL | 5432 | 5433 | ✅ |
| | API (FastAPI) | 8000 | 8001 | ✅ |
| | Frontend | 80 | 5174 | ✅ |
| **metroGet** | — | — | — | только .env, без Docker |
| **n8n_test** | n8n | 5678 | — | без публичного порта |
| | AWG | 5678 | 5678 | ✅ |
| **ap-visualizer** | App | 80 | 8080 | ✅ |
| **docker-app-1** | App | 8000 | 8081 | ✅ |
| **metroCheck** | PostgreSQL | 5432 | **5434** | ✅ |
| | Redis | 6379 | **6382** | ✅ |
| | Backend (FastAPI) | 8000 | **8002** | ✅ |
| | n8n | 5678 | **5681** | ✅ |

## Сервер mkair-server (Tailscale: 100.80.114.18)

Проекты лежат в `~/apps/`, не в `~/projects/`. SSH доступен (пароль: 7405).

| Проект | Сервис | Внутр. порт | Хост порт | Статус |
|--------|--------|-------------|-----------|--------|
| **metroLog** | PostgreSQL | 5432 | 5432 | Up 2 weeks |
| | Redis | 6379 | 6379 | Up 2 weeks |
| | Backend | 8000 | 8000 | Up 2 days |
| | Worker | — | — | Up 2 days |
| | Frontend | 80 | 5173 | Up 10 days |
| **metroGen** | PostgreSQL | 5432 | 5433 | Up 4 weeks (healthy) |
| | API | 8000 | 8001 | Up 4 weeks (healthy) |
| | Frontend | 80 | 5174 | Up 4 weeks |
| **monitoring** | Grafana | 3000 | 192.168.1.84:8090 | Up 4 weeks |
| | Prometheus | 9090 | 127.0.0.1:9091 | Up 4 weeks |
| | Alertmanager | 9093 | 127.0.0.1:9093 | Up 4 weeks |
| | Blackbox Exporter | 9115 | 127.0.0.1:9115 | Up 4 weeks |
| | cAdvisor | 8080 | 127.0.0.1:8080 | Up 4 weeks (healthy) |
| | Node Exporter | 9100 | — | Up 4 weeks |
| **metroSearch** | — | — | — | ❌ Не запущен |

## Почему такие порты для metroCheck

| Сервис | Старый порт | Новый порт | Конфликтовал с |
|--------|------------|------------|----------------|
| PostgreSQL | 5433 | **5434** | metroGen (5433) и локально, и на сервере |
| Backend | 8000 | **8002** | metroLog (8000) и локально, и на сервере |
| Redis | 6381 | **6382** | metroLog-devbox-redis (6380) — смещение для запаса |
| n8n | 5679 | **5681** | n8n_test-AWG (5678) |

## Занятые порты (локально, все проекты)

```
5432  — metroLog PostgreSQL
5433  — metroGen PostgreSQL
5434  — metroCheck PostgreSQL  ←
5678  — n8n_test AWG
5681  — metroCheck n8n         ←
6379  — metroLog Redis
6380  — metroLog devbox Redis
6382  — metroCheck Redis       ←
8000  — metroLog Backend
8001  — metroGen API
8002  — metroCheck Backend     ←
8080  — ap-visualizer
8081  — docker-app-1
5173  — metroLog Frontend
5174  — metroGen Frontend
```

## Занятые порты (сервер mkair-server, 100.80.114.18)

```
5432  — metroLog PostgreSQL
5433  — metroGen PostgreSQL
6379  — metroLog Redis
8000  — metroLog Backend
8001  — metroGen API
5173  — metroLog Frontend
5174  — metroGen Frontend
3000  — Grafana (192.168.1.84:8090)
8080  — cAdvisor (127.0.0.1)
9091  — Prometheus (127.0.0.1)
9093  — Alertmanager (127.0.0.1)
9115  — Blackbox Exporter (127.0.0.1)
9100  — Node Exporter
```

## Tailscale сеть

Все сервисы доступны через Tailscale (100.x.x.x). Для доступа с других устройств использовать:

```
http://100.104.105.63:8002  — metroCheck Backend (локально)
http://100.104.105.63:5681  — metroCheck n8n (локально)
http://100.80.114.18:8000   — metroLog Backend (сервер)
http://100.80.114.18:8001   — metroGen API (сервер)
```

## SSH доступ

| Сервер | IP | Пользователь | Пароль |
|--------|----|-------------|--------|
| mkair-server | 100.80.114.18 | mflkee | 7405 |
