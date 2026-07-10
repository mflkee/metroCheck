Продолжи работу над проектом win_test — тестирование token-agent для Windows.

Контекст:
- В папке win_test находится production-ready стек: Python-агент, Chrome-расширение, тестовая страница Аршина, скрипты проверки.
- Задача: Зонов логинится в Аршин (https://fgis.gost.ru), JWT попадает в localStorage, расширение отправляет его агенту на http://127.0.0.1:8003, агент записывает токен в JSON-файл в Synology-папку.
- Серверная часть уже протестирована и работает: POST /token/callback пишет файл в C:\Users\mflkee\SynologyDrive\2_Документы внутреннего происхождения\2_19 Протоколы\tokens\test\arshin-token.json.
- Зомби-процесс на порту 8003 был убит пользователем. Порт свободен.
- Команда python в системе не работает (Windows Store-заглушка), используется Python из pgAdmin или нужно установить Python с python.org.

Что нужно сделать:
1. Проверить, что агент запускается через run.cmd.
2. Проверить установку расширения в Chrome/Yandex.
3. Провести тест с реальным входом в Аршин (или с fake-arshin.html на http://127.0.0.1:8080).
4. Убедиться, что файл arshin-token.json появляется в Synology-папке.
5. Если расширение не находит токен — открыть DevTools на fgis.gost.ru, посмотреть ключ localStorage и добавить его в chrome-extension/content.js в TOKEN_KEYS.
6. Подготовить win_test для добавления в GitHub как отдельная папка.

Важные файлы:
- win_test/server.py — агент
- win_test/chrome-extension/ — расширение
- win_test/run.cmd — запуск агента
- win_test/test_env.py — проверка окружения
- win_test/README.md — полная инструкция
- win_test/LLM_CONTEXT.md — детальный контекст

Инструкции по запуску:
1. run.cmd (или python server.py)
2. chrome://extensions/ → режим разработчика → загрузить win_test/chrome-extension
3. http://127.0.0.1:8080/fake-arshin.html (если нужен тест без Аршина)
4. Проверить файл arshin-token.json и лог token-agent.log

Будь внимателен к:
- Правам на запись в Synology-папку.
- Занятости порта 8003.
- Правильному ключу в localStorage на fgis.gost.ru.
- CORS и host_permissions в manifest.json расширения.

Ответь на русском языке. Действуй последовательно, проверяй каждый шаг и сообщай результаты.
