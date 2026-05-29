# Token Agent для Windows (Embedded Python)

## Архив: `token-agent-windows-embedded.zip` (13 MB)

## Содержимое
- `python.exe` - Embedded Python 3.11 (не требует установки)
- `token-agent/main.py` - агент для приема токена от Chrome Extension
- `token-agent/run.bat` - запуск агента
- `token-agent/.env` - настройки пути к файлу
- `setup.bat` - установка зависимостей (один раз)

## Установка для Зонова (5 минут)

### Шаг 1: Распаковать
```
token-agent-windows-embedded.zip → C:/token-agent/
```

### Шаг 2: Настроить путь
```
1. Открыть: token-agent/.env
2. Прописать путь к Synology Drive:
   TOKEN_FILE_PATH=C:/Users/Зонов/SynologyDrive/tokens/arshin-token.json
```

### Шаг 3: Установить зависимости (один раз)
```cmd
cd C:/token-agent
setup.bat
```

### Шаг 4: Запустить
```cmd
cd C:/token-agent/token-agent
run.bat
```

## Как это работает

```
Chrome Extension (fgis.gost.ru)
    ↓ (POST localhost:8003/token/callback)
token-agent.exe
    ↓ (пишет JSON)
C:/Users/Зонов/SynologyDrive/tokens/arshin-token.json
    ↓ (Synology Drive sync)
NAS (Synology)
    ↓ (Synology Drive sync)
/home/mflkee/SynologyDrive/tokens/arshin-token.json (mkair-server)
    ↓ (читает)
metroCheck backend (Docker)
    ↓ (проверяет протоколы)
ARSHIN API
```

## Преимущества
- ✅ Не нужен Python на Windows (встроен)
- ✅ Не нужен Netbird/VPN
- ✅ Не нужно открывать порты
- ✅ Synology Drive уже настроен
- ✅ Токен живет ~1 час, потом Зонов просто перелогинивается

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
- После прочтения backend **переименовывает** файл в `arshin-token.json.used`
- Это предотвращает повторное использование старого токена
- Зонову нужно только **запустить агент** и **логиниться в АРШИН**
