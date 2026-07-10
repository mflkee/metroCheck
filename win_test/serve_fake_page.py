"""
Простой HTTP-сервер для fake-arshin.html.

Запуск:
    python serve_fake_page.py

Открывай в браузере:
    http://localhost:8080/fake-arshin.html

Почему это важно:
    Если открыть fake-arshin.html как файл (file://...), content-script расширения
    не запустится на такой странице. Нужен http://localhost.
"""
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import os
import sys

PORT = int(os.environ.get("FAKE_PAGE_PORT", "8080"))
ROOT = Path(__file__).resolve().parent

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def log_message(self, format, *args):
        print(f"[fake-page] {self.address_string()} - {format % args}")


def main():
    os.chdir(ROOT)
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"[fake-page] Сервер запущен: http://127.0.0.1:{PORT}/fake-arshin.html")
    print(f"[fake-page] Для остановки: Ctrl+C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[fake-page] Остановлено")


if __name__ == "__main__":
    main()
