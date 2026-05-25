# Спецификация n8n пайплайнов (MCP + Kimi K2.6)

## Архитектура сборки

```
Kimi K2.6 (OpenRouter) — AI-агент-конструктор
    │
    ├── MCP Client ──→ n8n MCP Server (встроен в n8n v2.18.4+)
    │                      │
    │                      ├── create_workflow  — создать воркфлоу
    │                      ├── update_workflow  — обновить
    │                      ├── validate_workflow — проверить
    │                      └── execute_workflow  — прогнать тест
    │
    └── читает спецификацию → строит 5 воркфлоу
```

**Процесс сборки каждого воркфлоу:**
1. Kimi получает спецификацию (этот файл)
2. Вызывает `create_workflow` с описанием назначения
3. n8n MCP возвращает сгенерированный workflow
4. Kimi вызывает `validate_workflow` — если ошибки, чинит
5. Kimi вызывает `execute_workflow` с тестовыми данными
6. Если execution упал — читает ошибку, чинит, перезапускает
7. Готово

---

## Workflow 1: Main — Полный цикл проверки месяца

### Назначение
Запускается по Webhook от FastAPI. Скачивает данные из АРШИНа,
сканирует папку протоколов,запускает AI-экстракцию для каждого PDF,
выполняет проверки, формирует отчёт.

### Триггер
- **Webhook node** — `POST /webhook/run-check`
- **Body:** `{ "year": 2025, "month": 12 }`

### Ноды и конфигурация

**Node 1: Webhook**
- Path: `run-check`; Method: POST

**Node 2: Set** — Подготовка параметров
```
year: $json.year
month: $json.month
protocols_path: "/protocols/$json.year/$json.month"
arshin_base_url: "https://fgis.gost.ru/fundmetrology/eapi"
```

**Node 3: HTTP Request** — Проверка АРШИНа
- GET `={{ $json.arshin_base_url }}/vri?rows=1`

**Node 4: IF** — Статус 200? Нет → Error

**Node 5: HTTP Request** — Скачать список поверок
- GET `={{ $json.arshin_base_url }}/vri?rows=100&org_title=ООО "МКАИР"&year={{ $json.year }}`
- Pagination loop через Code node

**Node 6: Code** — Извлечь и нормализовать записи
```javascript
const items = $input.first().json.result?.items || [];
return items.map(item => ({
  vri_id: item.vri_id,
  mi_number: (item.mi_number || '').trim(),
  mit_number: item.mit_number,
  mit_title: item.mit_title,
  verification_date: item.verification_date,
  valid_date: item.valid_date,
  result_docnum: item.result_docnum,
  org_title: item.org_title
}));
```

**Node 7: HTTP Request** — Детали из ЛК (с Bearer token)
- POST `{{ $json.arshin_base_url }}/lk/details`
- Header: `Authorization: Bearer {{ $credentials.arshinToken.apiKey }}`
- Body: `{ "document_numbers": $json.items.map(i => i.result_docnum) }`

**Node 8: Code** — Объединить calibrations + LK data
```javascript
// join по result_docnum
const lkMap = new Map(($json.lkData || []).map(d => [d.document_number, d]));
return ($json.calibrations || []).map(cal => ({
  ...cal,
  verifier: lkMap.get(cal.result_docnum)?.verifier,
  conditions: lkMap.get(cal.result_docnum)?.conditions
}));
```

**Node 9: HTTP Request** — Сканировать папку протоколов
- POST `http://backend:8000/api/v1/protocols/scan`
- Body: `{ "year": $json.year, "month": $json.month, "path": $json.protocols_path }`

**Node 10: SplitInBatches** — Батчи по 5 протоколов
- Batch Size: 5
- Options: `{ "reset": false }`

**Node 11: Execute Workflow** — Вызвать Workflow 2 (Extract)
- Source: `Database` → искать по имени "Extract Protocol Data"
- Mode: `Each item separately`
- Input: `{ "protocol_id": $json.id, "file_path": $json.file_path, "text": $json.text }`

**Node 12: HTTP Request** — Сохранить извлечённые данные
- POST `http://backend:8000/api/v1/protocols/data`
- Body: как пришло от Workflow 2

**Loop:** Node 10-12 для всех батчей

**Node 13: HTTP Request** — Запустить проверки
- POST `http://backend:8000/api/v1/checks/run`
- Body: `{ "year": $json.year, "month": $json.month }`

**Node 14: Wait + Poll** — Ждать 5s, GET статус, повтор до "completed"

**Node 15: HTTP Request** — Получить результаты
- GET `http://backend:8000/api/v1/checks/results/{{ $json.run_id }}`

**Node 16: HTTP Request** — Сформировать Excel отчёт
- POST `http://backend:8000/api/v1/reports/generate/{{ $json.run_id }}`

**Node 17: Email** — Отправить уведомление
- Credential: SMTP
- Subject: `Проверка протоколов {{ $json.month }}/{{ $json.year }} — {{ summary.status }}`

### Credentials
| Имя | Тип | Назначение |
|-----|-----|-----------|
| `Arshin Public` | None | Публичный API АРШИН |
| `Arshin Token` | Header Auth (Bearer) | ЛК АРШИН |
| `FastAPI Backend` | Header Auth (API Key) | Backend |
| `SMTP` | Email (SMTP) | Уведомления |

### Sticky Note
```
Workflow 1: Main — Полный цикл проверки месяца
1. Получает year + month из Webhook
2. Проверяет АРШИН, скачивает поверки МКАИР
3. Получает детали из ЛК (требуется Bearer token)
4. Сканирует папку протоколов через FastAPI
5. Разбивает на батчи по 5, вызывает Extract для каждого
6. Сохраняет результаты, запускает проверки
7. Ждёт завершения, формирует отчёт, отправляет email

Credentials: Arshin Token (Bearer), FastAPI Backend (API Key), SMTP
```

---

## Workflow 2: Extract — AI extraction (gpt-oss-20b + fallback для сложных)

### Назначение
Sub-workflow. Получает текст PDF, пробует `gpt-oss-20b:free` (бесплатно). Если результат содержит ошибки — пробует `gpt-4o-mini` (платно, $0.15/1M). Возвращает JSON.

### Триггер
- **Execute Workflow Trigger** (из Workflow 1)

### Вход
```json
{ "protocol_id": "uuid", "file_path": "/path/to.pdf", "text": "..." }
```

### Ноды

**Node 1: Set** — Базовый промпт
```json
{
  "system_prompt": "Ты — помощник метрологической лаборатории. Извлеки структурированные данные из протокола поверки СИ в формате JSON.\nПоля: protocol_number, device_name, device_type, serial_number, mit_number, manufacture_year, owner, verification_date (ГГГГ-ММ-ДД), verifier, temperature (число), humidity (число), pressure (число), pressure_units (кПа/мм рт.ст.), result (годен/не годен), verification_method.\nЕсли поле не определено — null. Только JSON, без пояснений.",
  "protocol_text": "{{ $json.text }}"
}
```

**Node 2: HTTP Request** — NN1: google/gemma-4-31b-it:free (через FastAPI AI-proxy)
```json
{
  "method": "POST",
  "url": "http://fastapi:8000/api/v1/ai/extract",
  "headers": {
    "Content-Type": "application/json",
    "X-API-Key": "{{ $credentials.fastApiBackend.apiKey }}"
  },
  "body": {
    "model": "google/gemma-4-31b-it:free",
    "fallback_models": [
      "qwen/qwen3-next-80b-a3b-instruct:free",
      "openai/gpt-oss-120b:free",
      "openai/gpt-4o-mini"
    ],
    "system_prompt": "{{ $json.system_prompt }}",
    "text": "{{ $json.protocol_text }}",
    "max_tokens": 1000,
    "temperature": 0.1
  }
}
```
**ВАЖНО:** n8n НЕ ходит напрямую в OpenRouter (https://openrouter.ai), т.к. n8n работает внутри AWG VPN (сеть МКАИР). Все AI-запросы идут через FastAPI AI-proxy по внутренней docker-сети. FastAPI сам управляет fallback-цепочкой NN1→NN2→NN3→NN4.

**Node 3: Code (JS)** — Валидация + определение сложного случая
```javascript
const r = $input.first().json;
let data;
try { data = JSON.parse(r.choices?.[0]?.message?.content || '{}'); } catch { data = null; }

let score = 0;
const req = ['protocol_number','serial_number','device_name','verification_date','verifier','temperature','humidity','pressure'];
for (const f of req) { if (data?.[f]) score += 1; }
if (data?.temperature < -50 || data?.temperature > 60) score -= 2;
if (data?.humidity < 0 || data?.humidity > 100) score -= 2;

const confidence = Math.max(0, score / req.length);
const has_errors = confidence < 0.3 || data === null || score < 0;
const missing_critical = req.filter(f => !data?.[f]);

return [{
  protocol_id: $json.protocol_id,
  confidence: confidence,
  missing: missing_critical,
  data: data,
  raw_response: r,
  model_used: 'gpt-oss-20b',
  is_hard_case: has_errors,
  cost: 0
}];
```

**Node 4: IF** — Сложный случай?
- Condition: `$json.is_hard_case === true`
- True → Node 5 (GPT-4o mini correction)
- False → Node 7 (Return Success)

### Сложные случаи (триггерят GPT-4o mini)

| Условие | Тип сбоя | Пример |
|---------|---------|--------|
| `data === null` | Технический | JSON не распарсился |
| `confidence < 0.3` | Технический | Менее 3 полей из 8 |
| `score < 0` | Логический | t°C < -50 или > 60 |
| `missing_critical.length > 5` | Технический | Большинство полей пусты |

**Node 5: Set** — Промпт для GPT-4o mini с контекстом ошибки
```json
{
  "system_prompt": "Ты — помощник метрологической лаборатории. Предыдущая модель не справилась:\nconfidence={{ $json.confidence }}, пропущены поля: {{ $json.missing }}.\n\nИзвлеки данные заново. Ошибки предыдущей попытки:\n{{ JSON.stringify($json.data) }}\n\nВерни ТОЛЬКО JSON с теми же полями.",
  "protocol_text": "{{ $json.protocol_text }}",
  "model": "openai/gpt-4o-mini"
}
```

**Node 6: HTTP Request** — GPT-4o mini correction pass
- URL: `http://fastapi:8000/api/v1/ai/extract`
- body.model: `"openai/gpt-4o-mini"`
- body.temperature: 0.05

**Node 6b: Code (JS)** — Валидация GPT-4o mini
```javascript
const r = $input.first().json;
let data;
try { data = JSON.parse(r.choices?.[0]?.message?.content || '{}'); } catch { data = null; }

let score = 0;
const req = ['protocol_number','serial_number','device_name','verification_date','verifier','temperature','humidity','pressure'];
for (const f of req) { if (data?.[f]) score += 1; }
if (data?.temperature < -50 || data?.temperature > 60) score -= 2;
if (data?.humidity < 0 || data?.humidity > 100) score -= 2;

const confidence = Math.max(0, score / req.length);

return [{
  protocol_id: $json.protocol_id,
  confidence: confidence,
  missing: req.filter(f => !data?.[f]),
  data: data,
  model_used: 'gpt-4o-mini',
  cost: r.usage ? r.usage.prompt_tokens * 1.5e-7 + r.usage.completion_tokens * 6e-7 : 0,
  status: confidence >= 0.3 && score >= 0 ? 'success' : 'manual_review'
}];
```

**Node 7: Set** — Финальный результат
```json
{
  "protocol_id": $json.protocol_id,
  "data": $json.data,
  "model_used": $json.model_used,
  "confidence": $json.confidence,
  "cost": $json.cost,
  "status": "{{ $json.status || 'success' }}"
}
```

**Node 8: Return** — Вернуть результат в Workflow 1

### Sticky Note
```
Workflow 2: Extract — AI extraction

Основная модель: google/gemma-4-31b-it:free (бесплатно через OpenRouter)
Fallback NN2:   qwen/qwen3-next-80b-a3b-instruct:free ($0)
Fallback NN3:   openai/gpt-oss-120b:free ($0)
Аварийная NN4:  openai/gpt-4o-mini ($0.15/1M input) — только если все бесплатные не справились

FastAPI AI-proxy управляет fallback-цепочкой автоматически.
n8n получает только финальный результат.

Сложный случай = confidence < 0.3 || t°C аномальная || JSON не распарсен
Если все модели не справились → status: manual_review

Поля: protocol_number, serial_number, device_name, verification_date,
verifier, temperature, humidity, pressure, mit_number, owner, result
```

---

## Workflow 3: Scheduled — Ежемесячная проверка по расписанию

### Назначение
Запускается автоматически 1-го числа каждого месяца. Вычисляет предыдущий месяц и вызывает Workflow 1.

### Триггер
- **Schedule Trigger** — Cron: `0 9 1 * *`

### Ноды

**Node 1: Schedule Trigger**
- Cron Expression: `0 9 1 * *`

**Node 2: Code (JS)** — Вычислить предыдущий месяц
```javascript
const now = new Date();
const prev = new Date(now.getFullYear(), now.getMonth() - 1, 1);
return [{ year: prev.getFullYear(), month: prev.getMonth() + 1 }];
```

**Node 3: Execute Workflow** — Workflow 1 (Main)
- Source: `Database` → "Main"
- Mode: `Once`
- Input: `{ "year": $json.year, "month": $json.month }`

**Node 4: Email** — Уведомление о завершении
- Subject: `Автоматическая проверка за {{ $json.month }}/{{ $json.year }} завершена`

### Sticky Note
```
Workflow 3: Scheduled — Ежемесячная проверка
- Cron: 1-е число каждого месяца в 09:00
- Проверяет предыдущий месяц
- Вызывает Workflow 1 (Main)
- Отправляет email-уведомление
```

---

## Workflow 4: Error Recovery — Повторная обработка ошибок

### Назначение
Обрабатывает протоколы, где все 3 модели не справились. Использует сразу NN3 (GPT-4o mini) с расширенным контекстом ошибки.

### Триггер
- **Webhook** — `POST /webhook/retry-protocol`

### Ноды

**Node 1: Webhook** — POST `/webhook/retry-protocol`
- Body: `{ "protocol_id": "uuid", "text": "...", "previous_attempts": [...] }`

**Node 2: Set** — Промпт с контекстом ошибок
```
system_prompt: "Ты — эксперт метролог. Предыдущие 3 модели не смогли корректно извлечь данные из протокола. Вот их ошибки: (список). Проанализируй текст заново. Особое внимание: заводской номер (ищи после 'зав.№','серийный','serial','S/N'), дата поверки, ФИО поверителя, условия поверки."
protocol_text: $json.text
```

**Node 3: HTTP Request** — NN3: GPT-4o mini (единственная попытка, через FastAPI AI-proxy)
- URL: `http://fastapi:8000/api/v1/ai/extract`
- body.model: `"openai/gpt-4o-mini"`
- body.temperature: 0.05 (максимальная детерминированность)
- body.max_tokens: 1500

**Node 4: Code (JS)** — Валидация

**Node 5: IF** — Успех? → Return success, иначе → `manual_review`

**Node 6: HTTP Request** — Обновить статус в БД
- POST `http://backend:8000/api/v1/protocols/{{ $json.protocol_id }}/status`

### Sticky Note
```
Workflow 4: Error Recovery
- Вызывается вручную или автоматически для протоколов со status=manual_review
- Использует GPT-4o mini (единственный проход, без fallback)
- При повторной ошибке → окончательно manual_review
- Если gpt-oss-20b был недоступен (rate limit) — пробуем GPT-4o mini
```

---

## Workflow 5: Arshin Monitor — Мониторинг АРШИНа

### Назначение
Проверяет доступность АРШИНа каждые 15 минут. При недоступности — уведомление.

### Триггер
- **Schedule Trigger** — `*/15 * * * *`

### Ноды

**Node 1: Schedule Trigger** — `*/15 * * * *`

**Node 2: HTTP Request** — GET `https://fgis.gost.ru/fundmetrology/eapi/vri?rows=1`

**Node 3: IF** — StatusCode != 200 → Node 4, иначе → Stop

**Node 4: Email** — Тема: `⚠️ АРШИН НЕДОСТУПЕН | {{ $now.toISO() }}`

### Sticky Note
```
Workflow 5: Arshin Monitor
- Cron: каждые 15 минут
- Проверяет GET /eapi/vri
- При недоступности → email админу
```

---

## Глобальные credentials (создать в n8n)

| Имя | Тип | Поле | Назначение |
|-----|-----|------|-----------|
| `fastApiBackend` | Header Auth | Name: `X-API-Key`, Value: `{{ FASTAPI_API_KEY }}` | Все вызовы к FastAPI (и data, и AI-proxy) |
| `arshinToken` | Header Auth | Name: `Authorization`, Value: `Bearer {{ ARSHIN_BEARER_TOKEN }}` | ЛК АРШИН (через FastAPI) |
| `smtp` | Email (SMTP) | Host/Port/User/Pass | Уведомления |

**Внимание:** OpenRouter credential в n8n НЕ НУЖЕН. Все AI-запросы идут через FastAPI AI-proxy (`POST /api/v1/ai/extract`). OpenRouter API key хранится только в FastAPI.

## Параметры окружения

### n8n (контейнер с AWG VPN)
```
N8N_MCP_SERVER_ENABLED=true
N8N_MCP_SERVER_API_KEY=...
FASTAPI_URL=http://fastapi:8000
FASTAPI_API_KEY=mkair-secret-key
ARSHIN_BEARER_TOKEN=eyJ2ZXIi...
SMTP_HOST=smtp.mkair.ru
SMTP_USER=notify@mkair.ru
SMTP_PASS=...
```

### FastAPI (контейнер без VPN, внешний интернет)
```
OPENROUTER_API_KEY=sk-or-v1-...
ARSHIN_BEARER_TOKEN=eyJ2ZXIi...
DATABASE_URL=postgresql://user:pass@postgres:5432/mkair
FASTAPI_API_KEY=mkair-secret-key
```

## AWG VPN конфиг для n8n

```
# /etc/awg/mkair.conf — AmneziaWireGuard конфиг
[Interface]
PrivateKey = ...
Address = 10.0.0.2/24
DNS = 10.0.0.1

[Peer]
PublicKey = ...
AllowedIPs = 10.0.0.0/24, 192.168.1.0/24  # только сеть МКАИР, НЕ весь трафик
Endpoint = vpn.mkair.ru:51820
PersistentKeepalive = 25
```

**Критично:** `AllowedIPs` должен содержать только подсети МКАИР (SMB, будущая БД), НЕ `0.0.0.0/0`. Иначе n8n потеряет доступ к FastAPI через docker bridge.

---

## Порядок сборки для Kimi (MCP команды)

```
1. create_workflow "Workflow 5: Arshin Monitor"
   → validate → execute с тестом

2. create_workflow "Workflow 4: Error Recovery"  
   → validate → execute
```
3. create_workflow "Workflow 2: Extract Protocol Data"
   → validate → execute с тестовым PDF
   → проверить fallback цепочку NN1→NN2→NN3→NN4
```
4. create_workflow "Workflow 3: Scheduled Monthly Check"
   → validate → execute с тестом

5. create_workflow "Workflow 1: Main Full Check"
   → validate → execute с тестовым месяцем
   → проверить полный цикл
```
