"""Агент токена ARSHIN для Windows.

Принимает JWT-токен от расширения Chrome и записывает его в JSON-файл
в папке, синхронизируемой Synology Drive Client.

Настройка:
    token-agent/.env    -> TOKEN_FILE_PATH, HOST, PORT
    Переменная среды    -> TOKEN_FILE_PATH

Логирование:
    token-agent/token-agent.log
    Вывод в консоль

Без внешних зависимостей: используется только стандартная библиотека Python.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Пути
# ---------------------------------------------------------------------------
AGENT_DIR = Path(__file__).resolve().parent
LOG_FILE = Path(os.environ.get("TOKEN_AGENT_LOG", AGENT_DIR / "token-agent.log"))
ENV_FILE = AGENT_DIR / ".env"

# ---------------------------------------------------------------------------
# Загрузка .env из папки агента (не из текущей директории)
# ---------------------------------------------------------------------------
if ENV_FILE.exists():
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key not in os.environ:
            os.environ[key] = value

# ---------------------------------------------------------------------------
# Логирование: консоль + файл
# ---------------------------------------------------------------------------
logger = logging.getLogger("token-agent")
logger.setLevel(logging.DEBUG)

if LOG_FILE.exists():
    try:
        backup = LOG_FILE.with_suffix(".log.prev")
        backup.write_text(LOG_FILE.read_text(encoding="utf-8"), encoding="utf-8")
    except Exception:
        pass

formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

file_handler = logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# ---------------------------------------------------------------------------
# Настройки
# ---------------------------------------------------------------------------
TOKEN_FILE_PATH = Path(
    os.environ.get(
        "TOKEN_FILE_PATH",
        r"C:\Users\Zonov\SynologyDrive\tokens\arshin-token.json",
    )
)
HOST = os.environ.get("TOKEN_AGENT_HOST", "127.0.0.1")
PORT = int(os.environ.get("TOKEN_AGENT_PORT", "8003"))
TOKEN_TTL = int(os.environ.get("TOKEN_TTL", "3600"))

_state: dict[str, Any] = {"token": None, "updated_at": 0}


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------
def log_startup_info() -> None:
    """Вывести диагностическую информацию при старте."""
    logger.info("=" * 50)
    logger.info("Запуск агента токена ARSHIN")
    logger.info("=" * 50)
    logger.info("Python: %s", sys.executable)
    logger.info("Версия Python: %s", sys.version.replace("\n", " "))
    logger.info("Папка агента: %s", AGENT_DIR)
    logger.info("Текущая папка: %s", Path.cwd())
    logger.info("Файл настроек: %s", ENV_FILE)
    logger.info("Файл настроек существует: %s", ENV_FILE.exists())
    logger.info("TOKEN_FILE_PATH: %s", TOKEN_FILE_PATH)
    logger.info("TOKEN_FILE_PATH (абсолютный): %s", TOKEN_FILE_PATH.resolve())
    logger.info("Папка для токена существует: %s", TOKEN_FILE_PATH.parent.exists())
    logger.info("Адрес прослушивания: %s:%s", HOST, PORT)


def jwt_expires_in(raw_token: str, default: int = TOKEN_TTL) -> int:
    """Расшифровать JWT и получить время до истечения."""
    try:
        parts = raw_token.split(".")
        if len(parts) < 2:
            return default
        payload = parts[1]
        payload = payload.replace("-", "+").replace("_", "/")
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += "=" * padding
        decoded = json.loads(base64.b64decode(payload, validate=True))
        exp = decoded.get("exp")
        if exp is None:
            return default
        remaining = int(exp - time.time())
        return max(remaining, 0)
    except Exception as exc:
        logger.warning("Не удалось расшифровать срок действия JWT: %s", exc)
        return default


def ensure_token_directory() -> bool:
    """Создать папку для токена, если её нет."""
    directory = TOKEN_FILE_PATH.parent
    if directory.exists():
        return True
    try:
        directory.mkdir(parents=True, exist_ok=True)
        logger.info("Создана папка для токена: %s", directory)
        return True
    except Exception as exc:
        logger.error("Не удалось создать папку для токена: %s", exc)
        logger.error(traceback.format_exc())
        return False


def write_token_file(token: str) -> bool:
    """Записать токен в JSON-файл. Возвращает True при успехе."""
    if not ensure_token_directory():
        return False
    try:
        data = {
            "token": token,
            "updated_at": int(time.time()),
            "expires_in": jwt_expires_in(token),
            "source": "chrome-extension",
        }
        tmp_path = TOKEN_FILE_PATH.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(TOKEN_FILE_PATH)
        _state["token"] = token
        _state["updated_at"] = data["updated_at"]
        logger.info("Токен записан: %s", TOKEN_FILE_PATH)
        logger.info("Размер файла: %s байт", TOKEN_FILE_PATH.stat().st_size)
        logger.info("Токен истекает через: %ss", data["expires_in"])
        return True
    except Exception as exc:
        logger.error("Не удалось записать файл токена: %s", exc)
        logger.error(traceback.format_exc())
        return False


# ---------------------------------------------------------------------------
# HTTP-обработчик
# ---------------------------------------------------------------------------
class TokenHandler(BaseHTTPRequestHandler):
    def _cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, Authorization, X-API-Key",
        )

    def _json(self, payload: dict, code: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(code)
        self._cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        logger.info("GET %s от %s", self.path, self.client_address)
        if self.path == "/health":
            self._json({
                "status": "ok",
                "has_token": _state["token"] is not None,
                "token_file": str(TOKEN_FILE_PATH),
                "token_file_exists": TOKEN_FILE_PATH.exists(),
                "token_updated_at": _state["updated_at"],
            })
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        logger.info("POST %s от %s", self.path, self.client_address)
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length)

        try:
            body = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            logger.error("Некорректное JSON-тело: %s", exc)
            self._json({"error": "invalid json"}, 400)
            return

        if self.path == "/token/callback":
            token = body.get("token", "")
            key = body.get("key", "?")
            source = body.get("source", "?")
            if token.startswith("Bearer "):
                token = token[7:]
            logger.info("Получен токен: key=%s source=%s preview=%s...", key, source, token[:20])
            if write_token_file(token):
                self._json({"status": "ok", "message": "Токен сохранён в файл"})
            else:
                self._json({"status": "error", "message": "Не удалось записать файл токена"}, 500)
        elif self.path == "/token/discover":
            logger.info("Получен дамп хранилища:")
            for store_name, keys in body.items():
                logger.info("  %s:", store_name)
                for k, v in keys.items():
                    logger.info("    %s = %s", k, v)
            self._json({"status": "ok"})
        else:
            self._json({"error": "not found"}, 404)

    def log_message(self, fmt: str, *args: Any) -> None:
        pass


# ---------------------------------------------------------------------------
# Запуск сервера
# ---------------------------------------------------------------------------
def start_server() -> None:
    log_startup_info()
    ensure_token_directory()

    for attempt in range(1, 4):
        try:
            server = HTTPServer((HOST, PORT), TokenHandler)
            logger.info("Сервер запущен: http://%s:%s", HOST, PORT)
            logger.info("Файл токена: %s", TOKEN_FILE_PATH.resolve())
            logger.info("Нажмите Ctrl+C для остановки")
            server.serve_forever()
            break
        except OSError as exc:
            logger.error("Ошибка запуска сервера (попытка %s/3): %s", attempt, exc)
            if attempt < 3:
                logger.info("Повтор через 3 секунды...")
                time.sleep(3)
            else:
                logger.critical("Не удалось запустить сервер на порту %s", PORT)
                logger.critical(traceback.format_exc())
                raise


if __name__ == "__main__":
    try:
        start_server()
    except KeyboardInterrupt:
        logger.info("Остановлено пользователем")
    except Exception as exc:
        logger.critical("Критическая ошибка: %s", exc)
        logger.critical(traceback.format_exc())
        print("\n*** ОШИБКА АГЕНТА ТОКЕНА ***")
        print(str(exc))
        print("\nПолный лог:", LOG_FILE.resolve())
        print("\nНажмите Enter для выхода...")
        try:
            input()
        except KeyboardInterrupt:
            pass
        sys.exit(1)
