#!/usr/bin/env python3
"""Проверка единой версии: фронтенд, бэкенд и запись в CHANGELOG.

Правило проекта: любое изменение функциональности поднимает версию и оставляет
запись в CHANGELOG.md. Скрипт запускается в CI до сборки образов.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    frontend = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    version = frontend["version"]

    main_py = (ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    match = re.search(r'version="([^"]+)"', main_py)
    backend_version = match.group(1) if match else ""

    changelog_path = ROOT / "CHANGELOG.md"
    changelog = changelog_path.read_text(encoding="utf-8") if changelog_path.exists() else ""

    problems: list[str] = []
    if backend_version != version:
        problems.append(
            f"версия фронтенда ({version}) и бэкенда ({backend_version}) разошлись — "
            "поправьте frontend/package.json и backend/app/main.py"
        )
    if f"## {version}" not in changelog:
        problems.append(f"в CHANGELOG.md нет раздела «## {version}» — добавьте запись об изменении")

    print(f"версия: {version} · бэкенд: {backend_version}")
    if problems:
        for problem in problems:
            print(f"::error::{problem}")
        return 1
    print("OK: версия едина и запись в CHANGELOG есть")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
