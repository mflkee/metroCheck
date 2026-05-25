"""token-agent: receives ARSHIN token from Chrome Extension, serves to backend.

Environment variables:
  TOKEN_AGENT_FILE  — optional path to write token to file (e.g. C:\Users\Zonov\token.txt)
"""

import os
import time
from typing import Optional

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
        print("[token-agent] Failed to write token file: {}".format(e))


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
    print(
        "[token-agent] Token received — {}/{}: {}...".format(
            data.key or "?", data.source or "?",
            (_token or "")[:20]
        )
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
    print("[token-agent] Discovery dump:")
    for store_name, keys in data.items():
        print("  {}:".format(store_name))
        for k, v in keys.items():
            print("    {} = {}".format(k, v))
    return {"status": "ok"}


@app.get("/health")
async def health():
    return {"status": "ok", "has_token": _token is not None}
