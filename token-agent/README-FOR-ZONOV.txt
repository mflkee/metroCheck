Агент токена ARSHIN — инструкция для Зонова
============================================

ЧТО ДЕЛАЕТ
-----------
Эта программа принимает токен от расширения Chrome на сайте fgis.gost.ru
и записывает его в файл arshin-token.json. Этот файл должен лежать в папке,
которую синхронизирует Synology Drive Client. После этого сервер сам заберёт
токен из файла.

ФАЙЛЫ
-----
token-agent-windows\
├── python.exe              <-- портативный Python
├── run.cmd                 <-- запуск агента
├── setup.cmd               <-- настройка pip (один раз)
├── add-autostart.cmd       <-- добавить в автозагрузку
└── token-agent\
    ├── main.py             <-- программа агента
    ├── .env                <-- настройки пути к файлу токена
    └── token-agent.log     <-- логи работы

БЫСТРЫЙ СТАРТ
-------------
1. Распакуй папку token-agent-windows в удобное место, например:
   C:\Tools\token-agent-windows\

2. Открой файл token-agent\.env обычным Блокнотом.

3. Замени строку:
      TOKEN_FILE_PATH=REPLACE_WITH_YOUR_SYNOLOGY_DRIVE_PATH/tokens/arshin-token.json

   на реальный путь к своей папке Synology Drive, например:
      TOKEN_FILE_PATH=C:/Users/Zonov/SynologyDrive/tokens/arshin-token.json

   Как узнать путь:
   - Открой Проводник Windows
   - Перейди в папку SynologyDrive
   - Нажми на адресную строку сверху и скопируй путь
   - Вставь его в .env вместо REPLACE_WITH_YOUR_SYNOLOGY_DRIVE_PATH
   - Оставь в конце /tokens/arshin-token.json

   Можно использовать / или \ — оба варианта работают.

4. Запусти setup.cmd один раз (двойным кликом).

5. Запусти run.cmd двойным кликом.
   Окно не закрывай — агент должен работать постоянно.

6. (Опционально) Запусти add-autostart.cmd, чтобы агент стартовал
   автоматически при включении компьютера.

КАК ПРОВЕРИТЬ
--------------
Открой браузер и перейди по адресу:
   http://127.0.0.1:8003/health

Должен появиться примерно такой текст:
   {
     "status": "ok",
     "has_token": false,
     "token_file": "C:/Users/Zonov/SynologyDrive/tokens/arshin-token.json",
     "token_file_exists": false
   }

После входа в личный кабинет ФГИС "Аршин" файл arshin-token.json должен
появиться в папке tokens.

ЕСЛИ НЕ РАБОТАЕТ
----------------
1. run.cmd пишет "python.exe not found"
   Рядом с run.cmd должен лежать python.exe. Если его нет — скачай
   портативный Python 3.11 и положи файлы рядом с run.cmd.

2. "Не удалось создать папку для токена"
   Путь в .env неверный. Проверь, что папка SynologyDrive существует
   и в ней есть папка tokens.

3. Окно сразу закрывается
   Запусти run.cmd через cmd.exe, чтобы увидеть ошибку.
   Или открой файл token-agent\token-agent.log.

4. Токен не приходит на сервер
   - Проверь, что файл arshin-token.json появился в SynologyDrive\tokens
   - Проверь лог token-agent\token-agent.log
   - Проверь, что расширение Chrome включено

ЛОГИ
----
Все действия пишутся в:
- консоль (чёрное окно)
- файл token-agent\token-agent.log

При каждом запуске старый лог сохраняется как token-agent.log.prev.

НАСТРОЙКА ПОРТА
---------------
Если нужно сменить порт, измени в .env:
   TOKEN_AGENT_PORT=8003

Не забудь поменять порт и в расширении Chrome (файл background.js).
