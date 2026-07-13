"""
Production-robust token-agent для Windows.

Простой HTTP-сервер на чистой стандартной библиотеке Python.
Принимает токен от Chrome-расширения и записывает его в JSON-файл.

Запуск:
    python server.py

Настройка через .env файл в этой же папке:
    TOKEN_FILE_PATH  - куда сохранять токен
    TOKEN_AGENT_HOST - адрес прослушивания (по умолчанию 127.0.0.1)
    TOKEN_AGENT_PORT - порт (по умолчанию 8003)
"""
from __future__ import annotations

import base64
import json
import logging
import os
import socket
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Загрузка .env из папки сервера
# ---------------------------------------------------------------------------
AGENT_DIR = Path(__file__).resolve().parent
ENV_FILE = AGENT_DIR / ".env"

if ENV_FILE.exists():
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value

# ---------------------------------------------------------------------------
# Настройки
# ---------------------------------------------------------------------------
TOKEN_FILE_PATH = Path(
    os.environ.get(
        "TOKEN_FILE_PATH",
        str(AGENT_DIR / "arshin-token.json"),
    )
)
HOST = os.environ.get("TOKEN_AGENT_HOST", "127.0.0.1")
PORT = int(os.environ.get("TOKEN_AGENT_PORT", "8003"))
LOG_FILE_PATH = Path(
    os.environ.get("TOKEN_AGENT_LOG", str(AGENT_DIR / "token-agent.log"))
)

# ---------------------------------------------------------------------------
# Логирование: консоль + файл
# ---------------------------------------------------------------------------
logger = logging.getLogger("token-agent")
logger.setLevel(logging.DEBUG)

formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

file_handler = logging.FileHandler(LOG_FILE_PATH, mode="a", encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

_state: dict[str, Any] = {"token": None, "updated_at": 0}


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------
def jwt_expires_in(raw_token: str, default: int = 3600) -> int:
    """Расшифровать payload JWT и вернуть оставшееся время жизни в секундах."""
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
        logger.warning("Не удалось декодировать срок JWT: %s", exc)
        return default


def write_token_file(token: str) -> bool:
    """Записать токен в JSON-файл. Атомарная запись через .tmp."""
    try:
        TOKEN_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "token": token,
            "updated_at": int(time.time()),
            "expires_in": jwt_expires_in(token),
            "source": "chrome-extension",
        }
        tmp = TOKEN_FILE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(TOKEN_FILE_PATH)
        _state["token"] = token
        _state["updated_at"] = data["updated_at"]
        logger.info("Токен записан: %s", TOKEN_FILE_PATH)
        logger.info("Размер файла: %s байт", TOKEN_FILE_PATH.stat().st_size)
        logger.info("Токен истекает через: %ss", data["expires_in"])
        return True
    except Exception as exc:
        logger.error("Ошибка записи токена: %s", exc)
        logger.error(traceback.format_exc())
        return False


def read_existing_token() -> None:
    """При старте попытаться прочитать уже существующий файл токена."""
    try:
        if TOKEN_FILE_PATH.exists():
            data = json.loads(TOKEN_FILE_PATH.read_text(encoding="utf-8"))
            token = data.get("token")
            if token:
                _state["token"] = token
                _state["updated_at"] = data.get("updated_at", 0)
                logger.info("Загружен существующий токен из файла")
    except Exception as exc:
        logger.warning("Не удалось прочитать существующий токен: %s", exc)


# ---------------------------------------------------------------------------
# Startup checks
# ---------------------------------------------------------------------------
def check_port_available(host: str, port: int) -> bool:
    """Проверить, свободен ли порт."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex((host, port))
            return result != 0
    except Exception as exc:
        logger.error("Ошибка проверки порта: %s", exc)
        return False


def verify_environment() -> bool:
    """Проверить окружение перед запуском."""
    ok = True
    logger.info("=" * 50)
    logger.info("Проверка окружения")
    logger.info("=" * 50)
    logger.info("Путь к файлу токена: %s", TOKEN_FILE_PATH.resolve())
    logger.info("Папка для токена существует: %s", TOKEN_FILE_PATH.parent.exists())

    if not TOKEN_FILE_PATH.parent.exists():
        try:
            TOKEN_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
            logger.info("Создана папка для токена")
        except Exception as exc:
            logger.error("Не удалось создать папку для токена: %s", exc)
            ok = False

    try:
        test_file = TOKEN_FILE_PATH.parent / ".write_test"
        test_file.write_text("test", encoding="utf-8")
        test_file.unlink()
        logger.info("Папка для токена доступна для записи")
    except Exception as exc:
        logger.error("Папка для токена НЕ доступна для записи: %s", exc)
        ok = False

    if not check_port_available(HOST, PORT):
        logger.error("Порт %s:%s уже занят", HOST, PORT)
        ok = False
    else:
        logger.info("Порт %s:%s свободен", HOST, PORT)

    logger.info("Лог-файл: %s", LOG_FILE_PATH.resolve())
    try:
        LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.error("Не удалось создать папку для логов: %s", exc)

    return ok


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
class TokenHandler(BaseHTTPRequestHandler):
    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _json(self, payload: dict, code: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:
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
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length)

        try:
            body = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self._json({"error": "invalid json"}, 400)
            return

        if self.path == "/token/callback":
            token = body.get("token", "")
            if token.startswith("Bearer "):
                token = token[7:]
            if not token:
                logger.warning("Получен пустой токен")
                self._json({"error": "token missing"}, 400)
                return
            if write_token_file(token):
                self._json({"status": "ok", "message": "Токен сохранен"})
            else:
                self._json({"status": "error", "message": "Не удалось записать токен"}, 500)
        elif self.path == "/token/discover":
            logger.info("Получен дамп хранилища: %s", body)
            self._json({"status": "ok"})
        else:
            self._json({"error": "not found"}, 404)

    def log_message(self, fmt: str, *args: Any) -> None:
        logger.info(fmt, *args)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def start_server() -> None:
    logger.info("Запуск token-agent")
    logger.info("Адрес: http://%s:%s", HOST, PORT)
    logger.info("Файл токена: %s", TOKEN_FILE_PATH.resolve())

    read_existing_token()

    for attempt in range(1, 4):
        try:
            server = HTTPServer((HOST, PORT), TokenHandler)
            logger.info("Сервер запущен. Ctrl+C для остановки.")
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


def main() -> None:
    if not verify_environment():
        logger.critical("Проверка окружения не пройдена. Запуск отменен.")
        sys.exit(1)
    try:
        start_server()
    except KeyboardInterrupt:
        logger.info("Остановлено пользователем")
    except Exception as exc:
        logger.critical("Критическая ошибка: %s", exc)
        logger.critical(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
