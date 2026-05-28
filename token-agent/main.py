"""token-agent: receives ARSHIN token from Chrome Extension, serves to backend.

Environment variables:
  TOKEN_AGENT_FILE  — optional path to write token to file (e.g. C:\\Users\\Zonov\\token.txt)
"""

import uvicorn.protocols.http.auto
import os
import sys
import time
import traceback
import logging
from typing import Optional

LOG_FILE = os.environ.get("TOKEN_AGENT_LOG", "token-agent.log")
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
# Also log to console if available
console = logging.StreamHandler(sys.stdout)
console.setLevel(logging.INFO)
logging.getLogger("").addHandler(console)

logger = logging.getLogger("token-agent")

logger.info("=" * 50)
logger.info("token-agent starting...")
logger.info("Python: %s", sys.executable)
logger.info("CWD: %s", os.getcwd())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="ARSHIN Token Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_token = None  # type: Optional[str]
_updated_at = 0  # type: int

TOKEN_TTL = 3600
TOKEN_FILE = os.environ.get("TOKEN_AGENT_FILE", "")


def _write_token_file(token):
    if not TOKEN_FILE:
        return
    try:
        import json
        with open(TOKEN_FILE, "w") as f:
            json.dump({
                "token": token,
                "updated_at": int(time.time()),
                "expires_in": TOKEN_TTL,
            }, f)
    except Exception as e:
        logger.error("Failed to write token file: %s", e)


class TokenCallback(BaseModel):
    token: str
    key: Optional[str] = None
    source: Optional[str] = None


class TokenRequestResponse(BaseModel):
    status: str
    token: Optional[str] = None
    expires_in: int = 0


@app.post("/token/callback")
async def receive_token(data: TokenCallback):
    global _token, _updated_at
    raw = data.token
    if raw.startswith("Bearer "):
        raw = raw[7:]
    _token = raw
    _updated_at = int(time.time())
    logger.info(
        "Token received — %s/%s: %s...",
        data.key or "?", data.source or "?",
        (_token or "")[:20]
    )
    _write_token_file(_token)
    return {"status": "ok"}


@app.post("/token/request", response_model=TokenRequestResponse)
async def request_token():
    global _token, _updated_at
    if not _token:
        return TokenRequestResponse(status="waiting")
    age = int(time.time()) - _updated_at
    expires_in = max(0, TOKEN_TTL - age)
    if expires_in <= 0:
        _token = None
        return TokenRequestResponse(status="waiting")
    return TokenRequestResponse(
        status="ok",
        token=_token,
        expires_in=expires_in,
    )


@app.post("/token/discover")
async def discover_storage(data: dict):
    logger.info("Discovery dump:")
    for store_name, keys in data.items():
        logger.info("  %s:", store_name)
        for k, v in keys.items():
            logger.info("    %s = %s", k, v)
    return {"status": "ok"}


@app.get("/health")
async def health():
    return {"status": "ok", "has_token": _token is not None}


# ── Polling backend (исходящие соединения — работают через Netbird) ──

BACKEND_URL = os.environ.get("BACKEND_URL", "http://100.89.59.195:8002")
BACKEND_API_KEY = os.environ.get("BACKEND_API_KEY", "mkair-secret-key")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "30"))


def _poll_backend():
    """Background thread: poll backend every N seconds."""
    import threading
    import requests

    def _loop():
        logger.info("[POLL] Starting polling thread, interval=%ds", POLL_INTERVAL)
        while True:
            try:
                # 1. Ask if backend needs token
                poll_url = f"{BACKEND_URL}/api/v1/arshin/token/poll"
                r = requests.post(
                    poll_url,
                    headers={"X-API-Key": BACKEND_API_KEY},
                    timeout=10,
                )
                data = r.json()
                logger.debug("[POLL] token/poll → %s", data)

                if data.get("need_token"):
                    # 2. Backend needs token — deliver if we have it
                    if _token:
                        deliver_url = f"{BACKEND_URL}/api/v1/arshin/token/deliver"
                        r2 = requests.post(
                            deliver_url,
                            headers={
                                "X-API-Key": BACKEND_API_KEY,
                                "Content-Type": "application/json",
                            },
                            json={"token": _token},
                            timeout=10,
                        )
                        logger.info(
                            "[POLL] Token delivered to backend → %s",
                            r2.json(),
                        )
                    else:
                        logger.info("[POLL] Backend needs token, but we don't have one yet")

            except Exception as e:
                logger.warning("[POLL] Error: %s", e)

            time.sleep(POLL_INTERVAL)

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()
    logger.info("[POLL] Background polling thread started")


if __name__ == "__main__":
    import uvicorn
    import uvicorn.loops.asyncio  # force PyInstaller to bundle
    import uvicorn.loops.auto

    # Start polling before uvicorn
    _poll_backend()

    try:
        logger.info("Starting uvicorn on %s:%d", "0.0.0.0", 8003)
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=8003,
            loop="asyncio",
            log_level="info",
            access_log=True,
        )
    except Exception as exc:
        logger.critical("FAILED TO START: %s", exc)
        logger.critical("Traceback:\n%s", traceback.format_exc())
        print("\n*** ERROR STARTING TOKEN-AGENT ***")
        print(str(exc))
        print("\nFull details written to:", os.path.abspath(LOG_FILE))
        print("\nPress Enter to exit...")
        try:
            input()
        except KeyboardInterrupt:
            pass
        sys.exit(1)
