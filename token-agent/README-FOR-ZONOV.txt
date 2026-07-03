ARSHIN Token Agent - Установка для Зонова
=========================================

БЫСТРЫЙ СТАРТ
-------------
1. Распакуй папку token-agent-windows куда удобно, например:
   C:\Tools\token-agent-windows\

2. Внутри должно быть:
   token-agent-windows\
   ├── python.exe              <-- portable Python
   ├── run.cmd                 <-- запуск агента
   ├── setup.cmd               <-- первая настройка (pip)
   ├── add-autostart.cmd       <-- добавить в автозагрузку
   └── token-agent\
       ├── main.py             <-- сам агент
       ├── .env                <-- настройки пути к токену
       └── token-agent.log     <-- логи

3. Открой файл token-agent\.env и укажи РЕАЛЬНЫЙ путь к Synology Drive.

   Замени строку:
      TOKEN_FILE_PATH=REPLACE_WITH_YOUR_SYNOLOGY_DRIVE_PATH/tokens/arshin-token.json

   На свой путь, например:
      TOKEN_FILE_PATH=C:/Users/Zonov/SynologyDrive/tokens/arshin-token.json

   Как узнать путь:
   - Открой проводник Windows
   - Перейди в папку SynologyDrive
   - Нажми на адресную строку сверху и скопируй путь
   - Вставь его в .env вместо REPLACE_WITH_YOUR_SYNOLOGY_DRIVE_PATH
   - Оставь в конце /tokens/arshin-token.json

   Можно использовать прямые слэши C:/Users/... или обратные C:\Users\...
   Главное - чтобы папка tokens синхронизировалась с сервером.
4. Запусти setup.cmd один раз (создаст pip и пропишет python*.pth).

5. Запусти run.cmd двойным кликом.
   Окно не закрывай - агент должен работать.

6. (Опционально) Запусти add-autostart.cmd, чтобы агент стартовал при включении Windows.


КАК ПРОВЕРИТЬ ЧТО РАБОТАЕТ
--------------------------
Открой браузер и перейди:
   http://127.0.0.1:8003/health

Должно вернуть JSON примерно такой:
   {
     "status": "ok",
     "has_token": false,
     "token_file": "C:/Users/Zonov/SynologyDrive/tokens/arshin-token.json",
     "token_file_exists": false
   }

После входа в личный кабинет ФГИС "Аршин" файл должен появиться в папке SynologyDrive\tokens\.


АВТОЗАГРУЗКА И SYNOLOGY DRIVE
------------------------------
Агент умеет ждать, пока папка Synology Drive появится.
Если при старте Windows папки ещё нет, агент будет писать в лог:
   "Waiting for token directory... (1/60)"

Максимальное время ожидания: 60 секунд.
Если за 60 секунд папка не появилась - агент попытается создать её сам.


РЕШЕНИЕ ПРОБЛЕМ
----------------
Q: run.cmd пишет "python.exe not found"
A: Рядом с run.cmd должен лежать python.exe из portable Python. Если его нет -
   скачай embedded Python 3.11 с python.org и положи файлы рядом с run.cmd.

Q: "Could not create directory" при запуске
A: Путь в .env неверный или Synology Drive ещё не синхронизировал папку.
   Проверь путь в token-agent\.env.

Q: Токен не приходит на сервер
A: 1) Проверь, что файл arshin-token.json появляется в SynologyDrive\tokens\
   2) Проверь лог token-agent\token-agent.log
   3) Проверь, что расширение Chrome включено и работает на fgis.gost.ru

Q: Окно агента закрывается сразу
A: Запусти run.cmd через cmd.exe вручную, чтобы увидеть ошибку.
   Или открой token-agent\token-agent.log.

Q: Как поменять порт?
A: В token-agent\.env измени TOKEN_AGENT_PORT=8003 на другой.
   Не забудь поменять порт и в расширении Chrome (background.js).


ЛОГИРОВАНИЕ
-----------
Все действия пишутся одновременно:
- в консоль (чёрное окно)
- в файл token-agent\token-agent.log

При каждом запуске предыдущий лог сохраняется как token-agent.log.prev.


ФАЙЛЫ И ИХ НАЗНАЧЕНИЕ
---------------------
run.cmd              - запуск агента (двойной клик)
setup.cmd            - первая настройка portable Python
add-autostart.cmd    - добавить run.cmd в автозагрузку Windows
token-agent\.env     - настройки пути к файлу токена
token-agent\main.py  - исходный код агента
