# AGENTS.md — MetroCheck LLM Development Guide

## 1. Project Identity

| Field | Value |
|-------|-------|
| **What** | Automated verification protocol checker for `OOO "MKAIR"` |
| **Stack** | FastAPI + SQLAlchemy async + PostgreSQL 16 + Redis 7 + nginx |
| **Server** | `mkair-server-tmn` — Netbird VPN `100.89.18.223`, public `80.91.19.151` (password: `<PASSWORD>`) |
| **User** | `mflkee` on server, `Zonov` on PC in Tyumen (token provider) |
| **Monitor** | Grafana `192.168.1.84:8090`, Prometheus `127.0.0.1:9091` |

**Sibling repos (same infra):**
- [mflkee/metroLog](https://github.com/mflkee/metroLog) — equipment accounting system
- [mflkee/metroGen](https://github.com/mflkee/metroGen) — protocol generation service

---

## 2. Key Reference Files

| File | What it contains |
|------|------------------|
| `docs/ARCHITECTURE.md` | Full architecture diagram, component map, data flows |
| `docs/TOKEN_SPEC.md` | Chrome Extension + Synology Drive token sync |
| `docs/Спецификация_приложения.md` | Application requirements specification |
| `docs/Этапы_проектирования.md` | Design stages |
| `docs/PORT_MAP.md` | Port mapping, staging/production, token paths |
| `docker-compose.yml` | Production stack (ports 8xxx/5xxx) |
| `docker-compose.staging.yml` | Staging stack (ports 9xxx) |
| `.github/workflows/staging.yml` | Auto-deploy to staging on push to `main` |
| `.github/workflows/promote.yml` | Manual promote staging→production via GitHub UI |
| `.github/workflows/deploy.yml` | Deploy production on push to `release/*` |

**On server:** `~/apps/CICD.md` — full CI/CD documentation with rollback procedures.

---

## 3. Architecture (8-Phase Pipeline)

```
public_api → protocol_scan → protocol_ocr → data_extract →
partial_check → wait_token → lk_api → full_check → report
```

Phases 1-5: **no token needed** (public API + local files + AI)
Phase 6: **wait for ARSHIN LK token** (Synology Drive sync)
Phases 7-8: **token required** (LK details, full verification)

---

## 4. Server Access

```bash
# Connect
sshpass -p "$SSH_PASSWORD" ssh mflkee@mkair-server-tmn -o StrictHostKeyChecking=no

# Docker status (all containers)
sshpass -p "$SSH_PASSWORD" ssh mflkee@mkair-server-tmn -o StrictHostKeyChecking=no 'docker ps'

# Service logs
sshpass -p "$SSH_PASSWORD" ssh mflkee@mkair-server-tmn -o StrictHostKeyChecking=no 'docker logs metroCheck_backend --tail 50'
```

---

## 5. CI/CD — Two Circuits

### Circuit A: Staging (auto-deploy)
- **Ports:** Backend `:9002`, Frontend `:9081`, DB `:5436`, Redis `:6383`
- **Env file:** `.env.staging` (must contain `OPENROUTER_API_KEY`, `FASTAPI_API_KEY`)
- **Trigger:** `git push origin main` → GitHub Actions → `staging.yml`
- **DB:** `mkair_stg` (separate from production)
- **Purpose:** test changes before production

### Circuit B: Production (manual promote or release branch)
- **Ports:** Backend `:8002`, Frontend `:8081`, DB `:5434`, Redis `:6382`
- **Promote:** GitHub UI → Actions → "Promote to Production" → type `deploy` → wait 5 min
- **Release:** `git push origin release/*` → `deploy.yml`
- **DB:** `mkair` (production data)

### GitHub Environments
| Environment | Required Reviewers | Wait Timer | Branches |
|-------------|-------------------|------------|----------|
| `staging` | — | — | `main` |
| `production` | `mflkee` | 5 min | `main`, `release/*` |

---

## 6. LLM Development Workflow

### Starting a new task — MANDATORY protocol:

#### Step 1: Understand → Plan → Propose

When you receive a task (feature, fix, refactor, debug, chore):

1. **Analyze the request**
2. **Determine the type of work:**
   - `feature/*` — new functionality
   - `fix/*` — bug fix
   - `refactor/*` — code improvement without behavior change
   - `debug/*` — investigation, logging, diagnosis
   - `chore/*` — CI/CD, configs, dependencies, docs
3. **Create a plan** with:
   - Branch name (e.g., `feature/new-dashboard`)
   - Estimated stages in order
   - What touches staging vs production
   - Any manual steps required (GitHub UI, server, etc.)
4. **Present the plan** to the user and ask for approval

#### Step 2: Execute (after user approval)

1. **Create branch** (`git checkout -b feature/xxx`)
2. **Implement** changes
3. **Commit and push** to `main` (staging auto-deploys)
4. **Verify staging** health
5. **Report completion** and next steps (promote to production if needed)

---

## 7. Common Operations (Minimal Commands)

### Deploy to staging (after push to main)
```bash
# I do this automatically. Just say "push metroCheck to staging"
cd ~/projects/metroCheck && git add . && git commit -m "..." && git push origin main
```

### Staging UI access
- **URL:** `http://192.168.1.128:9081` (local network) or via Netbird `http://100.89.18.223:9081`
- **API key:** `CHANGE_ME_API_KEY` (hardcoded in frontend, must match `FASTAPI_API_KEY` in `.env.staging`)
- **Note:** Public IP `80.91.19.151:9081` is not accessible because the server is behind NAT. Use local/Netbird IP or set up an NPM proxy host.

### Check staging health
```bash
sshpass -p "$SSH_PASSWORD" ssh mflkee@mkair-server-tmn 'curl -s http://localhost:9002/health'
sshpass -p "$SSH_PASSWORD" ssh mflkee@mkair-server-tmn 'curl -s http://localhost:9081/'
```

### Restart staging backend
```bash
sshpass -p "$SSH_PASSWORD" ssh mflkee@mkair-server-tmn 'cd ~/apps/metroCheck && docker compose -p metrocheck-stg -f docker-compose.staging.yml --env-file .env.staging up -d --build'
```

### Check job queue (is a check running?)
```bash
sshpass -p "$SSH_PASSWORD" ssh mflkee@mkair-server-tmn 'curl http://localhost:9002/api/v1/jobs/queue'
```

### Check token status
```bash
sshpass -p "$SSH_PASSWORD" ssh mflkee@mkair-server-tmn 'curl http://localhost:9002/api/v1/arshin/token-status'
```

### View backend logs
```bash
sshpass -p "$SSH_PASSWORD" ssh mflkee@mkair-server-tmn 'docker logs metroCheck_backend_stg --tail 30'
```

### View AI fallback logs (to find regex patterns to add)
```bash
sshpass -p "$SSH_PASSWORD" ssh mflkee@mkair-server-tmn 'docker logs metroCheck_backend_stg --tail 500 2>&1 | grep AI_FALLBACK'
```

### Promote to production
```bash
# Requires GitHub UI — I can guide you through it
# GitHub → Actions → "Promote to Production" → Run workflow → type "deploy"
```

---

## 8. Token Sync (Synology Drive)

Token file path (server): `/home/mflkee/SynologyDrive/tokens/jwt-arshin-lk.json`
Inside container: `/shared/tokens/jwt-arshin-lk.json`

**Flow:** Zonov logs into `fgis.gost.ru` → Chrome Extension captures JWT → writes to local Synology Drive folder → syncs to NAS → syncs to server → backend reads file.

**Important:** After fixing the read-only volume bug (`:ro` removed), the backend now archives used tokens to `.used` files.

---

## 9. Git Rules

- **Never push directly to `release/*`** without explicit instructions
- **Staging branch:** `main` (auto-deploys)
- **Production:** via GitHub Actions promote or `release/*` push
- **Commit format:** `type: description` (e.g., `fix: resolve token polling loop`, `feat: add measurement range extraction`)
- **Always ask before push** if unsure of the target

---

## 10. Quick Reference — Ports & Services

| Service | Production Port | Staging Port |
|---------|----------------|--------------|
| Backend | `:8002` | `:9002` |
| Frontend | `:8081` | `:9081` |
| PostgreSQL | `:5434` | `:5435` |
| Redis | `:6382` | `:6383` |
| Prometheus | `:9091` | — |
| Grafana | `192.168.1.84:8090` | — |
| Netbird (server) | `100.89.59.195` | — |

**Monitoring stack** (`~/apps/monitoring/`): separate Docker Compose — Prometheus, Grafana, cAdvisor, Node Exporter, Alertmanager, Blackbox.
