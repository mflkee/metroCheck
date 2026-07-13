# Token Agent для Windows

Локальный агент на Python, который принимает JWT-токен из Chrome-расширения и записывает его в файл внутри папки Synology Drive.

## Содержимое `token-agent/`

```
token-agent/
├── server.py              # Агент (HTTP-сервер на stdlib)
├── run.cmd                # Запуск агента
├── setup.cmd              # Проверка Python и создание .env
├── test_env.py            # Проверка окружения без запуска сервера
├── watch_token.py         # Мониторинг файла токена
├── check_token_sync.py    # Проверка синхронизации с сервером
├── serve_fake_page.py     # Фейковая страница Аршина для тестов
├── run_fake_page.cmd      # Запуск фейковой страницы
├── fake-arshin.html       # HTML-страница для тестирования
├── .env.example           # Шаблон настроек
├── .env                   # Локальные настройки (не в git)
├── README.md              # Подробная инструкция
└── chrome-extension/      # Расширение Chrome
    ├── manifest.json
    ├── background.js
    ├── content.js
    ├── popup.html
    ├── popup.js
    └── icon.svg
```

## Установка для ПК Зонова (5 минут)

### Шаг 1: Установить Python

Скачать с https://python.org/downloads/ и установить.

Убедиться, что Python в PATH:
```cmd
python --version
```

### Шаг 2: Распаковать/скопировать папку `token-agent`

Скопировать папку `token-agent` из репозитория на ПК Зонова, например:
```
C:\Users\Zonov\token-agent\
```

### Шаг 3: Создать .env

Запустить `setup.cmd` — он создаст `.env` из `.env.example`.

Или создать `.env` вручную:
```env
TOKEN_FILE_PATH="C:/Users/Zonov/SynologyDrive/tokens/arshin-token.json"
TOKEN_AGENT_HOST=127.0.0.1
TOKEN_AGENT_PORT=8003
TOKEN_AGENT_LOG=token-agent.log
```

### Шаг 4: Проверить окружение

```cmd
python test_env.py
```

Должно быть `[OK] Окружение в порядке`.

### Шаг 5: Установить расширение Chrome

1. Открыть `chrome://extensions/`.
2. Включить **Режим разработчика**.
3. Нажать **Загрузить распакованное расширение**.
4. Выбрать папку `token-agent\chrome-extension`.

### Шаг 6: Запустить агент

```cmd
run.cmd
```

Или вручную:
```cmd
python server.py
```

## Как это работает

```
Chrome Extension (fgis.gost.ru)
    ↓ (POST localhost:8003/token/callback)
token-agent (server.py)
    ↓ (пишет JSON)
C:/Users/Zonov/SynologyDrive/tokens/arshin-token.json
    ↓ (Synology Drive sync)
NAS (Synology)
    ↓ (Synology Drive sync)
/home/mflkee/SynologyDrive/tokens/arshin-token.json (mkair-server)
    ↓ (читает)
metroCheck backend (Docker)
    ↓ (проверяет протоколы)
ARSHIN API
```

## Структура файла токена

```json
{
  "token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "updated_at": 1748423456,
  "expires_in": 3600,
  "source": "chrome-extension"
}
```

## Важно

- После прочтения backend **переименовывает** файл в `arshin-token.json.used`.
- Это предотвращает повторное использование старого токена.
- Зонову нужно только **запустить агент** и **логиниться в АРШИН**.

## Тестирование без реального Аршина

1. Запустить агент: `run.cmd`
2. Запустить фейковую страницу: `run_fake_page.cmd`
3. Открыть `http://127.0.0.1:8080/fake-arshin.html`
4. Расширение должно автоматически отправить токен агенту.

Проверить токен:
```cmd
curl http://127.0.0.1:8003/token
```
