import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer


# === Настройки ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "test")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "arshin-token.json")
PORT = 8003


class TokenHandler(BaseHTTPRequestHandler):
    """Простой HTTP-обработчик для приема токена от расширения."""

    def log_message(self, format, *args):
        # Собственный формат логов, без лишнего шума от http.server.
        print(f"[SERVER] {format % args}")

    def _send_cors_headers(self):
        # Расширение в браузере работает с другого origin, нужен CORS.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")

    def do_OPTIONS(self):
        # Preflight-запрос для CORS. Без него fetch из расширения заблокируется.
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_POST(self):
        if self.path != "/token":
            self.send_response(404)
            self.end_headers()
            return

        # 1. Читаем тело запроса.
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        # 2. Парсим JSON.
        try:
            data = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as e:
            print(f"[SERVER] Невалидный JSON: {e}")
            self.send_response(400)
            self._send_cors_headers()
            self.end_headers()
            return

        token = data.get("token")
        print(f"[SERVER] Получен токен: {token}")

        # 3. Создаем папку test, если ее нет.
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        # 4. Пишем в файл.
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"[SERVER] Сохранено в {OUTPUT_FILE}")

        # 5. Отвечаем расширению.
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", PORT), TokenHandler)
    print(f"[SERVER] Запущен на http://127.0.0.1:{PORT}")
    print(f"[SERVER] Токен будет записан в: {OUTPUT_FILE}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[SERVER] Остановлен")
