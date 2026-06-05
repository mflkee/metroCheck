# Спецификация получения токена АРШИН ЛК

## Проблема

- Токен АРШИН ЛК живёт **~1 час**
- Логин — через **Госуслуги** (ручной ввод, не автоматизируемый)
- Зонов в Тюмени, сервер в другом городе
- Токен живёт только в browser session (localStorage SPA)

## Решение: Chrome Extension + Synology Drive

```
                    ПК Зонова (Тюмень)
┌─────────────────────────────────────────────────────────────────┐
│  Chrome                                                         │
│  ├── fgis.gost.ru/fundmetrology/cm/lk                           │
│  │   → SPA хранит JWT в localStorage                            │
│  │                                                              │
│  └── Chrome Extension                                           │
│      ├── content.js                                             │
│      │   → читает localStorage по списку ключей каждые 3 сек    │
│      │   → находит значение, начинающееся с eyJ...              │
│      │   → отправляет в background.js                           │
│      ├── background.js                                          │
│      │   → получает токен от content.js                         │
│      │   → пишет в файл:                                        │
│      │     SynologyDrive/tokens/arshin-token.json               │
│      └── manifest.json                                          │
│                                                                  │
│  Synology Drive Client (Windows)                                │
│  └── синхронизирует SynologyDrive/tokens/ → NAS                 │
└─────────────────────────────────────────────────────────────────┘
                            │
                    Synology NAS
                   (облачное хранилище)
                            │
┌─────────────────────────────────────────────────────────────────┐
│  Сервер (mkair-server, Linux)                                   │
│                                                                  │
│  Synology Drive Client (Linux)                                  │
│  └── /home/mflkee/SynologyDrive/tokens/arshin-token.json        │
│                                                                  │
│  Docker: смонтировано в контейнер backend                       │
│  └── /shared/tokens/arshin-token.json                           │
│                                                                  │
│  Backend (FastAPI):                                             │
│  1. Читает файл при старте и каждые N секунд                    │
│  2. Парсит JSON, извлекает Bearer token                         │
│  3. Кеширует в памяти на 1 час                                  │
│  4. При 401 от АРШИН — инвалидирует кеш                         │
│  5. Использованные токены архивирует в .used                    │
└─────────────────────────────────────────────────────────────────┘
```

## Формат файла токена

```json
{
  "token": "eyJhbGciOiJSUzI1NiIsImtpZCI6...",
  "captured_at": "2026-06-05T10:30:00+05:00",
  "source": "chrome_extension",
  "expires_in": 3600
}
```

## Жизненный цикл в пайплайне

```
JobQueueService._execute_job()
  │
  ├── Фазы 1-5 (public_api → partial_check)
  │   → не требуют токена, выполняются всегда
  │
  ├── Фаза 6: wait_token
  │   → проверяет /shared/tokens/arshin-token.json
  │   → если токена нет или истёк:
  │     ├── статус job = "waiting_for_token"
  │     ├── polling файла каждые 30 сек
  │     └── ждём, пока Зонов не обновит токен
  │
  └── Фазы 7-8 (lk_api → full_check)
      → токен есть, выполняются
      → если 401 во время выполнения → возврат в фазу 6
```

## Компоненты Chrome Extension

### content.js
- Внедряется на страницу `fgis.gost.ru/fundmetrology/cm/*`
- Каждые 3 секунды проверяет `localStorage` по ключам:
  - `access_token`
  - `id_token`
  - `token`
  - Любое значение, начинающееся с `eyJ`
- При обнаружении нового токена отправляет сообщение в `background.js`

### background.js
- Service Worker (persistent)
- Получает токен от content.js
- Сохраняет в файл `arshin-token.json` в папке Synology Drive
- Логирует время захвата

## Важные моменты

- **Synology Drive должен быть запущен** на ПК Зонова до входа в ЛК
- После обновления токена синхронизация занимает **до 30 секунд**
- Backend архивирует старые токены (переименовывает в `.used.YYYYMMDD_HHMMSS`)
- Токен не передаётся по сети — только через Synology Drive
- Для ручного обновления: Зонов открывает ЛК АРШИН, логинится, расширение само ловит токен
