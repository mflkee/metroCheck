import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer


# === Загрузка .env из папки скрипта ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(BASE_DIR, ".env")


def _load_env(path):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]
            if key not in os.environ:
                os.environ[key] = value


_load_env(ENV_FILE)


# === Настройки ===
OUTPUT_FILE = os.environ.get(
    "OUTPUT_FILE",
    os.path.join(BASE_DIR, "test", "arshin-token.json"),
)
if not os.path.isabs(OUTPUT_FILE):
    OUTPUT_FILE = os.path.join(BASE_DIR, OUTPUT_FILE)

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8003"))


def _prepare_payload(data):
    token = data.get("token", "")
    if token.startswith("Bearer "):
        token = token[7:]
    return {
        "token": token,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "source": data.get("source", "chrome_extension"),
        "expires_in": 3600,
    }


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

        # 3. Создаем папку для токена, если ее нет.
        output_dir = os.path.dirname(OUTPUT_FILE)
        os.makedirs(output_dir, exist_ok=True)

        # 4. Пишем в файл в формате, ожидаемом backend.
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(_prepare_payload(data), f, ensure_ascii=False, indent=2)

        print(f"[SERVER] Сохранено в {OUTPUT_FILE}")

        # 5. Отвечаем расширению.
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))


if __name__ == "__main__":
    server = HTTPServer((HOST, PORT), TokenHandler)
    print(f"[SERVER] Запущен на http://{HOST}:{PORT}")
    print(f"[SERVER] Токен будет записан в: {OUTPUT_FILE}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[SERVER] Остановлен")
