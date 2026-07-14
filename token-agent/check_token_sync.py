r"""
Проверка синхронизации токена с сервером.

Использование:
    python check_token_sync.py [путь_к_файлу_на_сервере]

Пример:
    python check_token_sync.py "\\\\server\\share\\tokens\\jwt-arshin-token.json"
    python check_token_sync.py "C:\\Users\\mflkee\\SynologyDrive\\...\\tokens\\test\\jwt-arshin-token.json"
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

LOCAL_TOKEN_FILE = Path(os.environ.get("TOKEN_FILE_PATH", str(AGENT_DIR / "jwt-arshin-token.json")))


def read_token_info(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        stat = path.stat()
        return {
            "token_preview": data.get("token", "")[:40] + "...",
            "updated_at": data.get("updated_at", 0),
            "expires_in": data.get("expires_in", "?"),
            "file_size": stat.st_size,
            "file_mtime": stat.st_mtime,
        }
    except Exception as e:
        return {"error": str(e)}


def format_time(ts: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def main() -> int:
    remote_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None

    print("=" * 50)
    print("Проверка токена")
    print("=" * 50)

    local = read_token_info(LOCAL_TOKEN_FILE)
    if local is None:
        print(f"[LOCAL] Файл не найден: {LOCAL_TOKEN_FILE}")
    elif "error" in local:
        print(f"[LOCAL] Ошибка чтения: {local['error']}")
    else:
        print(f"[LOCAL] OK: {LOCAL_TOKEN_FILE}")
        print(f"        token: {local['token_preview']}")
        print(f"        updated_at: {format_time(local['updated_at'])}")
        print(f"        expires_in: {local['expires_in']}s")
        print(f"        size: {local['file_size']} байт")

    if remote_path:
        remote = read_token_info(remote_path)
        print()
        if remote is None:
            print(f"[REMOTE] Файл не найден: {remote_path}")
            print("         Синхронизация еще не произошла или путь неверный.")
        elif "error" in remote:
            print(f"[REMOTE] Ошибка чтения: {remote['error']}")
        else:
            print(f"[REMOTE] OK: {remote_path}")
            print(f"         token: {remote['token_preview']}")
            print(f"         updated_at: {format_time(remote['updated_at'])}")
            print(f"         size: {remote['file_size']} байт")
            if local and "error" not in local and "error" not in remote:
                if local["token_preview"] == remote["token_preview"]:
                    print("[SYNC]   Токены совпадают. Синхронизация работает.")
                else:
                    print("[SYNC]   Токены РАЗЛИЧАЮТСЯ. Синхронизация не завершена.")
    else:
        print()
        print("[INFO] Укажи путь к файлу на сервере для проверки синхронизации:")
        print('       python check_token_sync.py "\\\\server\\share\\tokens\\jwt-arshin-token.json"')

    return 0


if __name__ == "__main__":
    sys.exit(main())
