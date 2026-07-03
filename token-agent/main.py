"""ARSHIN Token Agent for Windows.

Receives ARSHIN JWT token from Chrome Extension and writes it to a JSON file
inside a Synology Drive (or any other) synced folder.

Configuration:
    token-agent/.env     -> TOKEN_FILE_PATH, HOST, PORT
    Environment variable -> TOKEN_FILE_PATH

Logging:
    token-agent/token-agent.log
    Console output (always)

No external dependencies: uses only Python standard library.
Tested with Python 3.10+.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# Folder where this script lives.
AGENT_DIR = Path(__file__).resolve().parent

# Default log file next to the script.
LOG_FILE = Path(os.environ.get("TOKEN_AGENT_LOG", AGENT_DIR / "token-agent.log"))

# ---------------------------------------------------------------------------
# Load .env file from agent directory (not CWD)
# ---------------------------------------------------------------------------
ENV_FILE = AGENT_DIR / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key not in os.environ:
            os.environ[key] = value

# ---------------------------------------------------------------------------
# Logging: console + file with rotation on start (keep last start)
# ---------------------------------------------------------------------------
logger = logging.getLogger("token-agent")
logger.setLevel(logging.DEBUG)

# Keep one backup of previous log.
if LOG_FILE.exists():
    try:
        backup = LOG_FILE.with_suffix(".log.prev")
        backup.write_text(LOG_FILE.read_text(encoding="utf-8"), encoding="utf-8")
    except Exception:
        pass

formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

file_handler = logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# ---------------------------------------------------------------------------
# Configuration with defaults
# ---------------------------------------------------------------------------
TOKEN_FILE_PATH = Path(
    os.environ.get(
        "TOKEN_FILE_PATH",
        r"C:\Users\Zonov\SynologyDrive\tokens\arshin-token.json",
    )
)
HOST = os.environ.get("TOKEN_AGENT_HOST", "127.0.0.1")
PORT = int(os.environ.get("TOKEN_AGENT_PORT", "8003"))
TOKEN_TTL = int(os.environ.get("TOKEN_TTL", "3600"))

# In-memory state.
_state: dict[str, Any] = {"token": None, "updated_at": 0}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def log_startup_info() -> None:
    """Dump useful startup diagnostics."""
    logger.info("=" * 50)
    logger.info("ARSHIN Token Agent starting")
    logger.info("=" * 50)
    logger.info("Python executable: %s", sys.executable)
    logger.info("Python version: %s", sys.version.replace("\n", " "))
    logger.info("Agent directory: %s", AGENT_DIR)
    logger.info("Working directory: %s", Path.cwd())
    logger.info("Env file used: %s", ENV_FILE)
    logger.info("Env file exists: %s", ENV_FILE.exists())
    logger.info("TOKEN_FILE_PATH: %s", TOKEN_FILE_PATH)
    logger.info("TOKEN_FILE_PATH absolute: %s", TOKEN_FILE_PATH.resolve())
    logger.info("Token directory exists: %s", TOKEN_FILE_PATH.parent.exists())
    logger.info("Listen host: %s", HOST)
    logger.info("Listen port: %s", PORT)


def jwt_expires_in(raw_token: str, default: int = TOKEN_TTL) -> int:
    """Decode JWT payload to extract real expiration time."""
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
        logger.warning("Could not decode JWT expiration: %s", exc)
        return default


def ensure_token_directory() -> None:
    """Create target directory if it does not exist; wait if parent is missing."""
    directory = TOKEN_FILE_PATH.parent
    if directory.exists():
        logger.info("Token directory ready: %s", directory)
        return

    logger.warning("Token directory does not exist yet: %s", directory)
    # Synology Drive may start later. Wait up to 60 seconds for parent folders.
    for attempt in range(1, 61):
        if directory.exists():
            logger.info("Token directory appeared after %ss: %s", attempt, directory)
            return
        if attempt == 1 or attempt % 10 == 0:
            logger.info("Waiting for token directory... (%s/60)", attempt)
        time.sleep(1)

    logger.warning("Directory did not appear; will try to create it: %s", directory)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        logger.info("Created token directory: %s", directory)
    except Exception as exc:
        logger.error("Failed to create token directory: %s", exc)
        logger.error(traceback.format_exc())


def write_token_file(token: str) -> bool:
    """Write token to shared JSON file. Returns True on success."""
    ensure_token_directory()
    try:
        data = {
            "token": token,
            "updated_at": int(time.time()),
            "expires_in": jwt_expires_in(token),
            "source": "chrome-extension",
        }
        tmp_path = TOKEN_FILE_PATH.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(TOKEN_FILE_PATH)
        _state["token"] = token
        _state["updated_at"] = data["updated_at"]
        logger.info("Token written successfully: %s", TOKEN_FILE_PATH)
        logger.info("Token file size: %s bytes", TOKEN_FILE_PATH.stat().st_size)
        logger.info("Token expires in: %ss", data["expires_in"])
        return True
    except Exception as exc:
        logger.error("Failed to write token file: %s", exc)
        logger.error(traceback.format_exc())
        return False


# ---------------------------------------------------------------------------
# HTTP request handler
# ---------------------------------------------------------------------------
class TokenHandler(BaseHTTPRequestHandler):
    def _cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, Authorization, X-API-Key",
        )

    def _json(self, payload: dict, code: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(code)
        self._cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        logger.info("GET %s from %s", self.path, self.client_address)
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
        logger.info("POST %s from %s", self.path, self.client_address)
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length)

        try:
            body = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            logger.error("Invalid JSON body: %s", exc)
            self._json({"error": "invalid json"}, 400)
            return

        if self.path == "/token/callback":
            token = body.get("token", "")
            key = body.get("key", "?")
            source = body.get("source", "?")
            if token.startswith("Bearer "):
                token = token[7:]
            logger.info("Token received key=%s source=%s preview=%s...", key, source, token[:20])
            if write_token_file(token):
                self._json({"status": "ok", "message": "Token saved to file"})
            else:
                self._json({"status": "error", "message": "Failed to write token file"}, 500)
        elif self.path == "/token/discover":
            logger.info("Discovery dump received:")
            for store_name, keys in body.items():
                logger.info("  %s:", store_name)
                for k, v in keys.items():
                    logger.info("    %s = %s", k, v)
            self._json({"status": "ok"})
        else:
            self._json({"error": "not found"}, 404)

    def log_message(self, fmt: str, *args: Any) -> None:
        # Suppress default stderr logging; we log via custom logger in methods.
        pass


# ---------------------------------------------------------------------------
# Server startup with retry on port conflicts
# ---------------------------------------------------------------------------
def start_server() -> None:
    log_startup_info()
    ensure_token_directory()

    for attempt in range(1, 4):
        try:
            server = HTTPServer((HOST, PORT), TokenHandler)
            logger.info("Server ready at http://%s:%s", HOST, PORT)
            logger.info("Token target: %s", TOKEN_FILE_PATH.resolve())
            logger.info("Press Ctrl+C to stop")
            server.serve_forever()
            break
        except OSError as exc:
            logger.error("Failed to start server (attempt %s/3): %s", attempt, exc)
            if attempt < 3:
                logger.info("Retrying in 3 seconds...")
                time.sleep(3)
            else:
                logger.critical("Could not start server on port %s", PORT)
                logger.critical(traceback.format_exc())
                raise


if __name__ == "__main__":
    try:
        start_server()
    except KeyboardInterrupt:
        logger.info("Stopped by user")
    except Exception as exc:
        logger.critical("Unhandled error: %s", exc)
        logger.critical(traceback.format_exc())
        print("\n*** TOKEN AGENT ERROR ***")
        print(str(exc))
        print("\nFull log:", LOG_FILE.resolve())
        print("\nPress Enter to exit...")
        try:
            input()
        except KeyboardInterrupt:
            pass
        sys.exit(1)
