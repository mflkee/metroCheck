"""
Проверка окружения token-agent без запуска сервера.

Запуск:
    python test_env.py
"""
from __future__ import annotations

import base64
import json
import os
import socket
import sys
import time
from pathlib import Path

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

TOKEN_FILE_PATH = Path(os.environ.get("TOKEN_FILE_PATH", str(AGENT_DIR / "arshin-token.json")))
HOST = os.environ.get("TOKEN_AGENT_HOST", "127.0.0.1")
PORT = int(os.environ.get("TOKEN_AGENT_PORT", "8003"))

def check_port(host: str, port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            return s.connect_ex((host, port)) != 0
    except Exception as e:
        print(f"[FAIL] Ошибка проверки порта: {e}")
        return False

def main() -> int:
    errors = 0
    print("=" * 50)
    print("Проверка окружения token-agent")
    print("=" * 50)

    print(f"[INFO] Путь к файлу токена: {TOKEN_FILE_PATH}")
    if not TOKEN_FILE_PATH.parent.exists():
        try:
            TOKEN_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
            print(f"[OK]   Создана папка: {TOKEN_FILE_PATH.parent}")
        except Exception as e:
            print(f"[FAIL] Не удалось создать папку: {e}")
            errors += 1
    else:
        print(f"[OK]   Папка существует")

    try:
        test_file = TOKEN_FILE_PATH.parent / ".write_test"
        test_file.write_text("test", encoding="utf-8")
        test_file.unlink()
        print(f"[OK]   Папка доступна для записи")
    except Exception as e:
        print(f"[FAIL] Папка НЕ доступна для записи: {e}")
        errors += 1

    if check_port(HOST, PORT):
        print(f"[OK]   Порт {HOST}:{PORT} свободен")
    else:
        print(f"[WARN] Порт {HOST}:{PORT} занят. Возможно, агент уже запущен.")

    print()
    print("=" * 50)
    if errors == 0:
        print("[OK] Окружение в порядке. Можно запускать run.cmd")
        return 0
    else:
        print(f"[FAIL] Найдено ошибок: {errors}. Исправь их перед запуском.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
