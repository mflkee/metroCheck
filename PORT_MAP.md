# Port Map — проекты MKAIR

## Сеть: Netbird VPN (mesh)

| Узел | Netbird IP | Роль |
|------|-----------|------|
| mkair-server | 100.89.59.195 | Сервер (metroLog, metroGen, metroCheck, monitoring) |
| mflkee (локально) | 100.104.105.63 | Разработка metroCheck |
| Зонов (Нижневартовск) | 100.89.96.31 | Token Agent (порт 8003) |

---

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

---

## Сервер mkair-server (Netbird: 100.89.59.195)

Проекты лежат в `~/apps/`. Деплой через GitHub Actions self-hosted runner.

| Проект | Сервис | Внутр. порт | Хост порт | Статус |
|--------|--------|-------------|-----------|--------|
| **metroLog** | PostgreSQL | 5432 | 5432 | Up |
| | Redis | 6379 | 6379 | Up |
| | Backend | 8000 | 8000 | Up |
| | Worker | — | — | Up |
| | Frontend | 80 | 5173 | Up |
| **metroGen** | PostgreSQL | 5432 | 5433 | Up |
| | API | 8000 | 8001 | Up |
| | Frontend | 80 | 5174 | Up |
| **metroCheck** | PostgreSQL | 5432 | **5434** | Up |
| | Redis | 6379 | **6382** | Up |
| | Backend | 8000 | **8002** | Up |
| | n8n | 5678 | **5681** | Up |
| **monitoring** | Grafana | 3000 | 192.168.1.84:8090 | Up |
| | Prometheus | 9090 | 127.0.0.1:9091 | Up |
| | Alertmanager | 9093 | 127.0.0.1:9093 | Up |
| | Blackbox Exporter | 9115 | 127.0.0.1:9115 | Up |
| | cAdvisor | 8080 | 127.0.0.1:8080 | Up |
| | Node Exporter | 9100 | — | Up |
| **metroSearch** | — | — | — | ❌ Не запущен |

---

## Внешние узлы (Netbird)

| Узел | IP | Сервис | Порт | Описание |
|------|-----|--------|------|----------|
| **Зонов ПК** | 100.89.96.31 | token-agent | 8003 | FastAPI сервер, хранит ARSHIN токен |

Token Agent доступен с mkair-server:
```bash
curl -X POST http://100.89.96.31:8003/token/request \
  -H "X-API-Key: mkair-token-agent-key"
```

---

## Почему такие порты для metroCheck

| Сервис | Старый порт | Новый порт | Конфликтовал с |
|--------|------------|------------|----------------|
| PostgreSQL | 5433 | **5434** | metroGen (5433) и локально, и на сервере |
| Backend | 8000 | **8002** | metroLog (8000) и локально, и на сервере |
| Redis | 6381 | **6382** | metroLog-devbox-redis (6380) — смещение для запаса |
| n8n | 5679 | **5681** | n8n_test-AWG (5678) |

---

## Занятые порты (локально)

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

---

## Занятые порты (сервер mkair-server)

```
5432  — metroLog PostgreSQL
5433  — metroGen PostgreSQL
5434  — metroCheck PostgreSQL  ←
6379  — metroLog Redis
6382  — metroCheck Redis       ←
8000  — metroLog Backend
8001  — metroGen API
8002  — metroCheck Backend     ←
5681  — metroCheck n8n         ←
5173  — metroLog Frontend
5174  — metroGen Frontend
3000  — Grafana (192.168.1.84:8090)
8080  — cAdvisor (127.0.0.1)
9091  — Prometheus (127.0.0.1)
9093  — Alertmanager (127.0.0.1)
9115  — Blackbox Exporter (127.0.0.1)
9100  — Node Exporter
```

---

## Доступ через Netbird

```
http://100.89.59.195:8000   — metroLog Backend (сервер)
http://100.89.59.195:8001   — metroGen API (сервер)
http://100.89.59.195:8002   — metroCheck Backend (сервер)  ←
http://100.89.59.195:5681   — metroCheck n8n (сервер)      ←
http://100.89.96.31:8003    — Token Agent (Зонов)           ←
```

---

## SSH доступ

| Сервер | IP (Netbird) | Пользователь | Пароль |
|--------|-------------|-------------|--------|
| mkair-server | 100.89.59.195 | mflkee | <PASSWORD> |

---

## CI/CD (GitHub Actions)

Файл: `.github/workflows/deploy.yml`

- **Trigger**: push в `main` или ручной запуск
- **Runner**: self-hosted на mkair-server (тег `mkair`)
- **Шаги**: clone → pull → `docker compose up -d --build` → health check

Запуск деплоя:
```bash
git push origin main
```

Или вручную: GitHub → Actions → "Deploy metroCheck" → Run workflow

---

## Firewall (mkair-server)

Для доступа token-agent с сервера на Зонова нужно разрешить порт 8003:

```powershell
# На ПК Зонова (Windows, Admin PowerShell):
New-NetFirewallRule -DisplayName "Allow Netbird ARSHIN Agent" `
  -Direction Inbound -Protocol TCP -LocalPort 8003 `
  -Action Allow -RemoteAddress 100.64.0.0/10
```
