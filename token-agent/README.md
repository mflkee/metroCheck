# Production-ready token-agent

Робастная версия стека для передачи токена Аршина от Chrome-расширения в локальный файл.

## Задача

1. Зонов логинится в личном кабинете Аршина (`https://fgis.gost.ru`).
2. После логина JWT-токен появляется в `localStorage`/`sessionStorage` браузера.
3. Chrome-расширение автоматически находит токен и отправляет локальному агенту.
4. Агент записывает токен в JSON-файл внутри папки Synology Drive.
5. Synology Drive Client синхронизирует файл на сервер.
6. Серверный backend / metroGen забирает токен из файла.

## Что сделано для надежности

- **Агент проверяет окружение перед запуском**: папка для токена, права на запись, свободен ли порт.
- **Логирование в файл** (`token-agent.log`) и в консоль.
- **Retry при занятом порте**: если порт 8003 занят, агент делает 3 попытки.
- **Атомарная запись файла**: сначала `.tmp`, потом replace.
- **Чтение существующего токена при старте**: если файл уже есть, агент загружает его в память.
- **Расширение имеет очередь и retry**: если агент был выключен, токен отправится позже.
- **Сканирование storage**: в popup можно посмотреть, что лежит в `localStorage`.
- **Проверка синхронизации**: `check_token_sync.py` сравнивает локальный файл с серверным.

## Файлы

```
token-agent/
├── server.py              # Агент (на stdlib)
├── run.cmd                # Запуск агента на Windows
├── setup.cmd              # Проверка Python и создание .env
├── test_env.py            # Проверка окружения без запуска сервера
├── watch_token.py         # Мониторинг файла токена
├── check_token_sync.py    # Проверка синхронизации с сервером
├── serve_fake_page.py     # Сервер фейковой страницы Аршина
├── run_fake_page.cmd      # Запуск сервера фейковой страницы
├── .env                   # Настройки
├── .env.example           # Шаблон настроек
├── fake-arshin.html       # Тестовая страница (если нужно отладить без реального Аршина)
├── README.md              # Этот файл
└── chrome-extension/
    ├── manifest.json      # Расширение Chrome
    ├── background.js      # Service worker + retry
    ├── content.js         # Поиск JWT в storage
    ├── popup.html         # Popup
    ├── popup.js           # Логика popup
    └── icon.svg           # Иконка
```

## Быстрый старт

### 1. Настрой .env

Открой `token-agent\.env`:

```env
TOKEN_FILE_PATH="C:\Users\mflkee\SynologyDrive\2_Документы внутреннего происхождения\2_19 Протоколы\tokens\test\jwt-arshin-lk.json"
TOKEN_AGENT_HOST=127.0.0.1
TOKEN_AGENT_PORT=8003
TOKEN_AGENT_LOG=token-agent.log
```

Для продакшена на ПК Зонова путь будет примерно таким:
```env
TOKEN_FILE_PATH="C:\Users\Zonov\SynologyDrive\tokens\jwt-arshin-lk.json"
```

### 2. Проверь окружение

```powershell
python test_env.py
```

Должно быть `[OK] Окружение в порядке`.

### 3. Запусти агент

```powershell
run.cmd
```

Или вручную:
```powershell
python server.py
```

Если `python` не работает (Windows Store-заглушка):
```powershell
& "C:\Program Files\PostgreSQL\17\pgAdmin 4\python\python.exe" server.py
```

### 4. Установи расширение в Chrome / Яндекс

1. Открой `chrome://extensions/`.
2. Включи **Режим разработчика**.
3. Нажми **Загрузить распакованное расширение**.
4. Выбери папку `token-agent\chrome-extension`.
5. Закрепи иконку на панели.

### 5. Открой Аршин и залогинься

Перейди на `https://fgis.gost.ru/`, войди под учетной записью.

Расширение должно автоматически найти JWT в `localStorage`/`sessionStorage` и отправить агенту.

### 6. Проверь файл

```powershell
Get-Content -Path "C:\Users\mflkee\SynologyDrive\2_Документы внутреннего происхождения\2_19 Протоколы\tokens\test\jwt-arshin-lk.json" -Raw
```

Или:
```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8003/health' -Method GET
```

### 7. Проверь синхронизацию

Если известен путь к файлу на сервере (после синхронизации Synology Drive):

```powershell
python check_token_sync.py "\\server\share\tokens\jwt-arshin-lk.json"
```

## Отладка

### Агент не запускается

```powershell
python test_env.py
```

Частые причины:
- Порт 8003 занят другим процессом.
- Нет прав на запись в папку токена.
- Python не в PATH.

### Расширение не отправляет токен

1. Открой `chrome://extensions/`.
2. Найди расширение → **"Фоновая страница"** / **"service worker"**.
3. В консоли должны быть логи `[ARSHIN] ...`.
4. Если логов нет, открой DevTools на странице Аршина (F12) → Application → Local Storage.
5. Посмотри, в каком ключе лежит JWT. Для Аршина это должен быть ключ `u` в `localStorage`, внутри поля `token`. Если структура изменится, отредактируй `chrome-extension\content.js`:
   ```javascript
   const STORAGE_KEY = 'u';
   const TOKEN_FIELD = 'token';
   ```

### Агент не видит токен после перезапуска

Теперь агент при старте читает существующий `jwt-arshin-lk.json`. Если этого не происходит, проверь лог `token-agent.log`.

### Токен не синхронизируется

1. Проверь, что Synology Drive Client работает и синхронизирует папку `tokens`.
2. Убедись, что файл `jwt-arshin-lk.json` создается внутри синхронизируемой папки.
3. Запусти `watch_token.py` — он покажет, когда файл изменился.
4. После синхронизации запусти `check_token_sync.py` с путем к файлу на сервере.

## Тест без реального Аршина

Если нужно отладить расширение без входа в Аршин:

1. Запусти агент: `run.cmd`
2. Запусти сервер фейковой страницы:
   ```powershell
   run_fake_page.cmd
   ```
   Или вручную:
   ```powershell
   python serve_fake_page.py
   ```
3. Открой в браузере:
   ```
   http://127.0.0.1:8080/fake-arshin.html
   ```
   На странице создается `localStorage` с токеном так же, как на реальном Аршине.
4. Расширение должно автоматически отправить токен агенту.

## Безопасность

- Агент слушает только `127.0.0.1:8003`.
- Расширение отправляет токен только на этот локальный адрес.
- Другие устройства в сети не могут отправить токен напрямую.
- JWT хранится в файле без шифрования — это нормально, так как файл находится в синхронизируемой папке пользователя.
