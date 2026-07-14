"""
Мониторинг файла токена. Показывает, когда токен появился или изменился.

Запуск:
    python watch_token.py

По Ctrl+C останавливается.
"""
from __future__ import annotations

import json
import os
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

TOKEN_FILE_PATH = Path(os.environ.get("TOKEN_FILE_PATH", str(AGENT_DIR / "jwt-arshin-lk.json")))


def format_time(ts: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def main() -> int:
    print(f"Мониторинг: {TOKEN_FILE_PATH}")
    print("Ожидание токена... Ctrl+C для выхода")
    last_size = None
    try:
        while True:
            if TOKEN_FILE_PATH.exists():
                size = TOKEN_FILE_PATH.stat().st_size
                mtime = TOKEN_FILE_PATH.stat().st_mtime
                if last_size != size:
                    last_size = size
                    print(f"[{format_time(int(mtime))}] Файл изменен. Размер: {size} байт")
                    try:
                        data = json.loads(TOKEN_FILE_PATH.read_text(encoding="utf-8"))
                        token = data.get("token", "")
                        exp = data.get("expires_in", "?")
                        print(f"  token preview: {token[:40]}...")
                        print(f"  expires_in: {exp}s")
                    except Exception as e:
                        print(f"  Ошибка чтения JSON: {e}")
            else:
                if last_size is not None:
                    print("Файл удален")
                    last_size = None
            time.sleep(2)
    except KeyboardInterrupt:
        print("\nОстановлено")
    return 0


if __name__ == "__main__":
    sys.exit(main())
