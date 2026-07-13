r"""
Простой сервер для фейковой страницы Аршина.

Запуск:
    python serve_fake_page.py

Открыть в браузере:
    http://127.0.0.1:8080/fake-arshin.html
"""
from __future__ import annotations

import os
import socketserver
from http.server import SimpleHTTPRequestHandler
from pathlib import Path

HOST = os.environ.get("FAKE_PAGE_HOST", "127.0.0.1")
PORT = int(os.environ.get("FAKE_PAGE_PORT", "8080"))
BASE_DIR = Path(__file__).resolve().parent


class CORSRequestHandler(SimpleHTTPRequestHandler):
    """HTTP-сервер с CORS-заголовками для тестирования fetch с фейковой страницы."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


if __name__ == "__main__":
    with ReusableTCPServer((HOST, PORT), CORSRequestHandler) as httpd:
        print(f"[FAKE PAGE] http://{HOST}:{PORT}/fake-arshin.html")
        httpd.serve_forever()
