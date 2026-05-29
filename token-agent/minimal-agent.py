"""Minimal token-agent — no pip install needed, pure Python 3."""
import json, os, sys, time
from http.server import HTTPServer, BaseHTTPRequestHandler

TOKEN_FILE_PATH = os.environ.get("TOKEN_FILE_PATH", "arshin-token.json")
HOST = "0.0.0.0"
PORT = 8003
token_data = {"token": None, "updated_at": 0}


def write_token(token):
    global token_data
    token_data = {"token": token, "updated_at": int(time.time()), "expires_in": 3600, "source": "chrome-extension"}
    os.makedirs(os.path.dirname(TOKEN_FILE_PATH) or ".", exist_ok=True)
    with open(TOKEN_FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(token_data, f, indent=2, ensure_ascii=False)
    print(f"[OK] Token written to {TOKEN_FILE_PATH}")


class Handler(BaseHTTPRequestHandler):
    def _json(self, data, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def do_GET(self):
        if self.path == "/health":
            self._json({
                "status": "ok",
                "has_token": token_data["token"] is not None,
                "token_file": TOKEN_FILE_PATH,
                "token_file_exists": os.path.exists(TOKEN_FILE_PATH),
            })
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        if self.path == "/token/callback":
            raw = body.get("token", "")
            if raw.startswith("Bearer "):
                raw = raw[7:]
            write_token(raw)
            self._json({"status": "ok", "message": "Token saved"})
        else:
            self._json({"error": "not found"}, 404)

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {args[0]} {args[1]} {args[2]}")


if __name__ == "__main__":
    print("=" * 50)
    print("  ARSHIN Token Agent (no-deps)")
    print("=" * 50)
    print(f"  Token file: {TOKEN_FILE_PATH}")
    print(f"  Listening on {HOST}:{PORT}")
    print("=" * 50)
    HTTPServer((HOST, PORT), Handler).serve_forever()
