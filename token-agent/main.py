"""token-agent: receives ARSHIN token from Chrome Extension, writes to shared file.

Environment variables:
  TOKEN_FILE_PATH   - path to write token JSON file (required)
  TOKEN_AGENT_LOG   - log file path (default: token-agent.log)

Example TOKEN_FILE_PATH:
  Windows: C:/Users/Zonov/SynologyDrive/tokens/arshin-token.json
  Linux:   /home/zonov/synology/tokens/arshin-token.json
"""

import uvicorn.protocols.http.auto
import os
import sys
import time
import traceback
import logging
import json
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
TOKEN_FILE_PATH = os.environ.get("TOKEN_FILE_PATH", "arshin-token.json")


def _write_token_file(token: str):
    """Write token to shared file for Synology Drive sync."""
    try:
        # Ensure directory exists
        dir_path = os.path.dirname(TOKEN_FILE_PATH)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        data = {
            "token": token,
            "updated_at": int(time.time()),
            "expires_in": TOKEN_TTL,
            "source": "chrome-extension",
        }

        with open(TOKEN_FILE_PATH, "w") as f:
            json.dump(data, f, indent=2)

        logger.info("Token written to: %s", TOKEN_FILE_PATH)
        logger.info("File size: %d bytes", os.path.getsize(TOKEN_FILE_PATH))
    except Exception as e:
        logger.error("Failed to write token file: %s", e)


class TokenCallback(BaseModel):
    token: str
    key: Optional[str] = None
    source: Optional[str] = None


@app.post("/token/callback")
async def receive_token(data: TokenCallback):
    global _token, _updated_at
    raw = data.token
    if raw.startswith("Bearer "):
        raw = raw[7:]
    _token = raw
    _updated_at = int(time.time())
    logger.info(
        "Token received - %s/%s: %s...",
        data.key or "?", data.source or "?",
        (_token or "")[:20]
    )
    _write_token_file(_token)
    return {"status": "ok", "message": "Token saved to file"}


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
    return {
        "status": "ok",
        "has_token": _token is not None,
        "token_file": TOKEN_FILE_PATH,
        "token_file_exists": os.path.exists(TOKEN_FILE_PATH),
    }


if __name__ == "__main__":
    import uvicorn
    import uvicorn.loops.asyncio
    import uvicorn.loops.auto

    logger.info("Token file path: %s", TOKEN_FILE_PATH)

    try:
        logger.info("Starting uvicorn on %s:%d", "0.0.0.0", 8003)
        uvicorn.run(
            app,
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
