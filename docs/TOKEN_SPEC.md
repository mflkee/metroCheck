# Спецификация удалённого получения токена АРШИН

## Проблема

- Токен АРШИН ЛК живёт **~1 час**
- Логин — через **Госуслуги** (ручной ввод, не автоматизируемый)
- OpenRouter может потребовать обновления токена в любое время
- ПК Зонова в **Тюмени**, сервер — в другом городе
- Токен не сохранить/передать — только live-сессия в браузере

## Схема

```
┌──────────────────────┐      Netbird VPN (mesh, P2P)       ┌──────────────────────────────┐
│  Наш сервер           │◄─────────────────────────────────►│  ПК В.М. (Нижневартовск)          │
│  (Docker, Тюмень)│   netbird.mkair.ts        :51820  │                              │
│                       │   без открытых портов              │  Chrome + Extension          │
│  FastAPI (back)       │                                    │    ↓ читает localStorage     │
│  ArshinClient         │                                    │    ↓ POST на localhost:8003   │
│                       │                                    │  token-agent:8003             │
│  При 401 от АРШИН:    │                                    │  (FastAPI, хранит токен)     │
│  POST /token/request  │── ── ── ── ── ── ── ── ── ── ──►│                              │
│                       │                                    │  ← возвращает кешированный   │
│  Ждём ответ           │◄── ── ── ── ── ── ── ── ── ── ──│    токен или {"status":"waiting"}
│  (таймаут ~24ч)       │    {"token": "eyJ..."}            │                              │
│                       │                                    │                              │
│  Кешируем на час      │                                    │  Расширение само шлёт токен  │
│  Retry при 401        │                                    │  когда Зонов залогинился     │
└──────────────────────┘                                    └──────────────────────────────┘
```

## Смена подхода: Selenium → Chrome Extension

**Было:** token-agent открывал Chrome через Selenium → Зонов логинился → JS скрапил токен.

**Стало:** Зонов один раз устанавливает расширение → сидит в его обычном Chrome фоне → при логине на fgis.gost.ru расширение само читает localStorage → шлёт на localhost:8003 → token-agent кеширует → наш сервер забирает через Netbird.

**Почему лучше:**

| Аспект | Selenium | Extension |
|--------|----------|-----------|
| Отдельное окно браузера | Да, мешает работать | **Нет**, фоновый content script |
| Зависимости на ПК Зонова | Python + Selenium + ChromeDriver | **Только Chrome** |
| Ждать 1-2 часа пока появится токен | Окно висит всё время | **Расширение висит незаметно** |
| Зонов может пользоваться браузером | Нет, Selenium занял браузер | **Да**, нормальная работа |
| Кто пишет логику скрапинга | Зонов | **Мы** (расширение наше) |
| Что нужно от Зонова | Написать код + поддерживать | **Установить расширение** (1 клик) |

## Компоненты

### 1. Chrome Extension (пишем мы)

Расширение ничего не видит, кроме `https://fgis.gost.ru/*`. Три файла:

#### manifest.json
```json
{
  "manifest_version": 3,
  "name": "ARSHIN Token Relay",
  "version": "1.0",
  "description": "Relays ARSHIN auth token to local agent",
  "permissions": [],
  "host_permissions": ["https://fgis.gost.ru/*"],
  "background": {
    "service_worker": "background.js"
  },
  "content_scripts": [{
    "matches": ["https://fgis.gost.ru/*"],
    "js": ["content.js"],
    "run_at": "document_idle"
  }]
}
```

#### content.js (запускается на каждой странице fgis.gost.ru)

Реальный ключ (подтверждено): `u` — JSON `{"orgId":"2163","token":"eyJ..."}`.

```javascript
const KNOWN_TOKEN = 'u';  // localStorage['u'] = {"orgId":"2163","token":"eyJ..."}

function checkForToken() {
  for (const store of [localStorage, sessionStorage]) {
    try {
      const raw = store.getItem(KNOWN_TOKEN);
      if (!raw) continue;
      let parsed;
      try { parsed = JSON.parse(raw); } catch (_) { continue; }
      if (parsed && parsed.token && parsed.token.startsWith('eyJ')) {
        chrome.runtime.sendMessage({
          type: 'token_found',
          token: parsed.token,
          key: KNOWN_TOKEN,
          source: store === localStorage ? 'localStorage' : 'sessionStorage',
        });
        return true;
      }
    } catch (_) {}
  }
  return false;
}

checkForToken();
setInterval(checkForToken, 3000);
```

#### background.js (сервис-воркер, шлёт на token-agent)

```javascript
const AGENT_URL = 'http://127.0.0.1:8003';
let knownTokens = new Set();

chrome.runtime.onMessage.addListener((msg, sender) => {
  if (msg.type === 'token_found' && !knownTokens.has(msg.token)) {
    knownTokens.add(msg.token);
    console.log('[ARSHIN] Token found:', msg.key, '(' + msg.source + ')');
    fetch(`${AGENT_URL}/token/callback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: msg.token, key: msg.key, source: msg.source })
    }).catch(() => { /* agent offline — попробует в следующий раз */ });
  }
  if (msg.type === 'storage_dump') {
    console.log('[ARSHIN] Storage dump:', msg.dump);
    fetch(`${AGENT_URL}/token/discover`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(msg.dump)
    }).catch(() => {});
  }
});
```

### 2. token-agent (на ПК Зонова, пишем мы)

Маленький FastAPI-сервер, единственная зависимость — `uvicorn[standard]`.

```
token-agent/
├── main.py
└── requirements.txt  # fastapi, uvicorn[standard]
```

#### main.py

```python
"""token-agent: получает токен от Chrome Extension, отдаёт нашему серверу."""
import time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="ARSHIN Token Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Хранилище токена
_token_store: dict = {"token": None, "updated_at": 0}

class TokenCallback(BaseModel):
    token: str
    key: str | None = None
    source: str | None = None

class TokenResponse(BaseModel):
    token: str | None = None
    status: str = "ok"
    expires_in: int = 0

@app.post("/token/callback")
async def receive_token(data: TokenCallback):
    """Вызывается расширением Chrome при обнаружении токена."""
    _token_store["token"] = data.token
    _token_store["updated_at"] = int(time.time())
    print(f"[token-agent] Received token ({data.key}/{data.source}) — {data.token[:20]}...")
    return {"status": "ok"}

@app.post("/token/request")
async def request_token():
    """Вызывается нашим сервером через Netbird."""
    token = _token_store.get("token")
    if not token:
        return {"status": "waiting", "token": None}
    age = int(time.time()) - _token_store.get("updated_at", 0)
    expires_in = max(0, 3600 - age)
    if expires_in <= 0:
        return {"status": "waiting", "token": None}
    return {"status": "ok", "token": token, "expires_in": expires_in}

@app.post("/token/discover")
async def discover_storage(data: dict):
    """Режим discovery: расширение шлёт все ключи localStorage для анализа."""
    print("[token-agent] Discovery dump received:")
    for store_name, keys in data.items():
        print(f"  {store_name}:")
        for k, v in keys.items():
            print(f"    {k} = {v}")
    return {"status": "ok"}

@app.get("/health")
async def health():
    return {"status": "ok"}
```
Запуск: `uvicorn main:host --host 0.0.0.0 --port 8003`

Опционально: токен можно записывать в файл, задав переменную окружения `TOKEN_AGENT_FILE`:

```bash
# Windows (cmd)
set TOKEN_AGENT_FILE=C:\Users\Zonov\token.txt
uvicorn main:host --host 0.0.0.0 --port 8003

# Linux
TOKEN_AGENT_FILE=/home/zonov/token.txt uvicorn main:host --host 0.0.0.0 --port 8003
```

### Варианты использования в скриптах Зонова

#### Вариант А — через HTTP (token-agent запущен)

token-agent работает как сервер, скрипт дёргает `GET /token/request`:

```powershell
# PowerShell
$r = Invoke-RestMethod http://localhost:8003/token/request
if ($r.status -eq "ok") {
    Write-Output $r.token
    # используй в своих скриптах...
}
```

```bash
# bash / WSL
curl -s http://localhost:8003/token/request | jq -r '.token'
```

```python
# Python
import httpx
r = httpx.get("http://localhost:8003/token/request")
data = r.json()
if data["status"] == "ok":
    token = data["token"]
```

Плюсы: всегда свежий токен, валидация срока, не нужно думать о файлах.
Минусы: token-agent должен быть запущен.

#### Вариант Б — через файл (token-agent пишет token.txt)

token-agent запущен с `TOKEN_AGENT_FILE=token.txt`. При каждом получении токена от расширения — обновляет файл.

```json
// token.txt
{"token": "eyJ...", "updated_at": 1747512345, "expires_in": 3600}
```

Скрипт читает файл:

```powershell
# PowerShell
$data = Get-Content token.txt | ConvertFrom-Json
$age = [int](Get-Date -UFormat %s) - $data.updated_at
if ($age -lt $data.expires_in) {
    Write-Output $data.token
} else {
    Write-Output "Token expired, log in to ARSHIN"
}
```

```bash
# bash
token=$(cat token.txt | jq -r '.token')
```

Плюсы: можно читать из любого окружения, не обязательно HTTP.
Минусы: нужно следить за сроком действия самому, файл может быть пуст если токена нет.

#### Вариант В — комбинированный

```powershell
# PowerShell — сначала HTTP, если сервер не отвечает — читаем файл
try {
    $r = Invoke-RestMethod http://localhost:8003/token/request -TimeoutSec 2
    $token = $r.token
} catch {
    $data = Get-Content token.txt | ConvertFrom-Json
    $token = $data.token
}
```

### 3. Netbird VPN (без изменений)

Как и раньше — mesh VPN между сервером и ПК Зонова.

После соединения наш сервер видит Зонова по IP `100.x.x.x:8003`.

### 4. Модификация ArshinClient (наш сервер)

```python
class ArshinClient:
    def __init__(self):
        self._cache: dict = {}

    async def _request_new_token(self) -> str:
        """Спросить токен у token-agent через Netbird."""
        async with httpx.AsyncClient(timeout=86400) as client:
            while True:
                r = await client.post(
                    f"http://{ZONOV_IP}:8003/token/request",
                    headers={"X-API-Key": TOKEN_AGENT_KEY},
                )
                data = r.json()
                if data.get("status") == "waiting":
                    await asyncio.sleep(30)  # polling раз в 30 сек
                    continue
                return data["token"]
```

## Как это работает: полный цикл

1. **Один раз:** Зонов устанавливает расширение (загружает unpacked из папки)
2. **Один раз:** Мы запускаем discovery — Зонов логинится в АРШИН, расширение шлёт dump localStorage → мы смотрим, какой ключ содержит токен → фиксим TOKEN_KEYS в content.js (если нужно)
3. **Каждый день:** Зонов просто работает за компьютером. Заходит на fgis.gost.ru, логинится через Госуслуги — расширение само читает токен, шлёт на localhost:8003
4. **Когда нужно нашему серверу:** запрашивает /token/request → token-agent отдаёт кешированный токен

## Что нужно от Зонова

### Этап 0. Discovery без расширения (один раз, 2 минуты)

**Подтверждено:** токен лежит в `localStorage['u']` = `{"orgId":"2163","token":"eyJ..."}`.

Ключ `u` содержит JSON-объект, внутри поле `token` с JWT. Расширение парсит JSON и извлекает токен.

Не нужно никаких дополнительных действий — ключ уже зафиксирован в `content.js`.

### Этап 1. Установка Netbird + token-agent (один раз, 10 минут)

1. Установить Netbird: `curl -sSL https://netbird.io/install.sh | sh`, потом `netbird login`
2. Скачать token-agent (`.exe` для Windows или папку для Linux)
3. Запустить token-agent (на Windows — просто открыть .exe, в трее появится иконка)

### Этап 2. Установка расширения (один раз, 2 минуты)

1. `chrome://extensions` → Режим разработчика → Загрузить распакованное → выбрать папку с расширением
2. Открыть `https://fgis.gost.ru/fundmetrology/cm/lk` — если уже залогинен, токен уедет сразу

### Этап 3. Ежедневная работа (ноль действий)

Расширение висит в фоне. Зонов пользуется Chrome как обычно. Когда нужно — логинится в АРШИН, токен автоматически уезжает к нам.

## Ответы на вопросы

### «Расширение будет работать, если надо ждать 1-2 часа?»

**Да.** Content script запускается при каждом заходе на fgis.gost.ru. Если расширение стоит и пользователь когда-либо зайдёт на этот сайт — токен будет пойман. Можно ждать хоть сутки — расширение ничем не мешает, не потребляет ресурсы (только setInterval раз в 3 секунды, пока открыта вкладка fgis.gost.ru).

После 5 минут бездействия service worker может заснуть — но content script в вкладке остаётся активным. Как только находит токен, будит service worker через `chrome.runtime.sendMessage`, и тот отправляет на token-agent.

### «Можно будет пользоваться браузером или это второе окно?»

**Можно пользоваться нормально.** Расширение не занимает браузер, не открывает свои окна, не перехватывает клики. Единственное — content.js выполняется в контексте fgis.gost.ru, но он только читает localStorage и ничего не меняет на странице.

### «Что попросить у Зонова для discovery?»

Конкретная инструкция для Зонова (можно просто скопировать в Telegram):

> 1. Скачай папку с расширением: [ссылкой на архив]
> 2. Распакуй, открой `chrome://extensions`, включи «Режим разработчика», нажми «Загрузить распакованное», выбери папку
> 3. Открой `https://fgis.gost.ru/fundmetrology/cm/lk`
> 4. Залогинься через Госуслуги
> 5. После логина открой `chrome://extensions` → «ARSHIN Token Relay» → «Service Worker» → там будет консоль с логами
> 6. Сделай скриншот и скинь мне

## Как узнать ключ без Зонова

Если Зонов не может/не хочет возиться с discovery — есть **универсальный подход**:

content.js будет проверять **все ключи localStorage** на предмет того, что значение начинается с `eyJ` (начало JWT). Большинство SPA хранят JWT в localStorage под одним из стандартных ключей. Если значение не `eyJ`, но всё равно токен — можно проверить по длине (>200 символов, похоже на base64url).

Плюс можно через `chrome.webRequest` API ловить HTTP-заголовок `Authorization` на запросах к `fgis.gost.ru/fundmetrology/cm/lk/api/...` — это 100% точный способ, не требующий знания ключа.

План Б описан в разделе «Резервные методы».

## Резервные методы (если localStorage пуст)

### Метод А: Intercept заголовков (webRequest)

```javascript
// background.js — ловим Authorization header в запросах к API
chrome.webRequest.onBeforeSendHeaders.addListener(
  (details) => {
    const auth = details.requestHeaders?.find(h => h.name === 'Authorization');
    if (auth?.value?.startsWith('Bearer eyJ')) {
      const token = auth.value.replace('Bearer ', '');
      fetchAgent(token);
    }
  },
  { urls: ['https://fgis.gost.ru/fundmetrology/cm/lk/api/*'] },
  ['requestHeaders']
);
```

### Метод Б: Script injection в контекст страницы

Если токен хранится в JS-переменной (Vuex/Redux), а не в localStorage:

```javascript
// content.js — внедряем скрипт в page context
const script = document.createElement('script');
script.textContent = `
  setInterval(() => {
    const token = window.__INITIAL_STATE__?.token
                  || window.__ARSHIN_TOKEN__
                  || document.cookie.match(/token=([^;]+)/)?.[1];
    if (token && token.startsWith('eyJ')) {
      window.postMessage({ type: 'ARSHIN_TOKEN', token }, '*');
    }
  }, 3000);
`;
document.documentElement.appendChild(script);

window.addEventListener('message', (e) => {
  if (e.data?.type === 'ARSHIN_TOKEN') {
    chrome.runtime.sendMessage({ type: 'token_found', token: e.data.token });
  }
});
```

## Windows сборка token-agent

Для пользователей Windows (у Зонова скорее всего Windows) Python ставить не нужно.

### Сборка .exe

Используем PyInstaller через Docker:

```bash
# Установка образа
docker pull cdrx/pyinstaller-windows:latest

# Сборка
docker run -v /home/mflkee/projects/metroCheck/token-agent:/src \
  cdrx/pyinstaller-windows \
  "pip install -r requirements.txt && pyinstaller --onefile --name token-agent main.py"
```

После сборки:
- `token-agent/dist/token-agent.exe` — единственный файл, ~15 MB
- Зонов просто запускает его (можно добавить в автозагрузку)
- Открывается консольное окно с логами
- Для работы в фоне — создать ярлык в `shell:startup`

### Альтернатива: NSSM (установка как служба Windows)

```
nssm install ARSHIN-Token-Agent "C:\path\to\token-agent.exe"
nssm start ARSHIN-Token-Agent
```

## Структура файлов в репозитории

```
metroCheck/
├── chrome-extension/                # расширение Chrome (устанавливает Зонов)
│   ├── manifest.json
│   ├── content.js
│   └── background.js
├── token-agent/                     # программа для ПК Зонова
│   ├── main.py                      # FastAPI сервер
│   ├── requirements.txt
│   ├── token-agent.service          # systemd (Linux)
│   └── build_exe.bat                # скрипт сборки .exe
├── backend/
│   ├── app/
│   │   ├── api/v1/routes/
│   │   │   ├── arshin.py            # + token-status, refresh-token, fetch-lk-async
│   │   │   ├── checks.py            # + run_async, task/{id}, token-status
│   │   │   └── ...
│   │   ├── integrations/
│   │   │   └── arshin_client.py     # _request_new_token() с polling + кеш
│   │   └── services/
│   │       └── task_manager.py      # async queue для background задач
│   └── tests/
│       └── test_check_service.py    # 18 тестов
├── docker-compose.yml
├── ARCHITECTURE.md
└── TOKEN_SPEC.md
```

## Безопасность

- **Расширение НЕ имеет прав на другие сайты** — `host_permissions: ["https://fgis.gost.ru/*"]`
- **Токен НЕ уходит в интернет** — только на localhost:8003
- **token-agent НЕ открыт наружу** — слушает только localhost (или Netbird IP)
- **Ключи от Зонова не нужны** — логин через Госуслуги как обычно
- **Netbird mesh VPN** — P2P шифрованный канал без открытых портов

## Альтернативы (не подошли)

| Вариант | Почему нет |
|---------|-----------|
| SSH + скрипт на ПК Зонова | Полный доступ к машине, security risk |
| Telegram bot | Токен — секрет, нельзя через мессенджер |
| Selenium + ChromeDriver | Занимает браузер, нужен Python |
| Selenium в headless-режиме | Нельзя залогиниться через Госуслуги (СМС-код) |
| ПК Зонова как сервер без VPN | Нет публичного IP (офисный NAT) |

## Ограничения

- Токен живёт ~1 час → нужно обновлять при каждой серии LK-запросов
- Зонов должен быть онлайн (включён ПК, работает token-agent)
- Ручной ввод Госуслуг не ускорить — только ждать
- Если Зонов не заходит на fgis.gost.ru — токена нет
- Netbird Free: до 3 peers, до 100 MB/мес (для текста — хватит на годы)
