"""Auth dependencies for FastAPI routes."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader

from app.core.auth import decode_access_token, get_admin_info
from app.core.config import settings

bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_current_user(
    bearer: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    api_key: str | None = Depends(api_key_header),
) -> dict:
    if bearer:
        payload = decode_access_token(bearer.credentials)
        if payload and payload.get("sub") == "admin":
            info = get_admin_info()
            info["auth_method"] = "jwt"
            return info

    if api_key and api_key == settings.FASTAPI_API_KEY:
        return {"username": "admin", "role": "admin", "auth_method": "api_key"}

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
