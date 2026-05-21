import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

TOKEN_URL = "https://api-uat.cotality.com/oauth/token?grant_type=client_credentials"

_cache = {"token": None, "expires_at": 0.0}
_bearer_scheme = HTTPBearer(auto_error=False)

JWT_ALGORITHM = "HS256"
JWT_EXPIRES_SECONDS = 60 * 60 * 24


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET")
    if secret:
        return secret

    if os.getenv("ENVIRONMENT") == "production":
        raise RuntimeError("Missing JWT_SECRET in production")

    return "dev-only-protopilot-secret"


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or _b64url_encode(os.urandom(16))
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"{salt}${_b64url_encode(digest)}"


def verify_password(password: str, password_hash: str) -> bool:
    salt, expected = password_hash.split("$", 1)
    candidate = hash_password(password, salt).split("$", 1)[1]
    return hmac.compare_digest(candidate, expected)


def create_access_token(subject: str, expires_seconds: int = JWT_EXPIRES_SECONDS) -> str:
    now = int(time.time())
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    payload = {"sub": subject, "iat": now, "exp": now + expires_seconds}

    signing_input = ".".join(
        [
            _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8")),
            _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
        ]
    )
    signature = hmac.new(_jwt_secret().encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256)
    return f"{signing_input}.{_b64url_encode(signature.digest())}"


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        header_raw, payload_raw, signature_raw = token.split(".")
        signing_input = f"{header_raw}.{payload_raw}"
        expected_signature = hmac.new(
            _jwt_secret().encode("utf-8"),
            signing_input.encode("ascii"),
            hashlib.sha256,
        ).digest()

        if not hmac.compare_digest(_b64url_decode(signature_raw), expected_signature):
            raise ValueError("Invalid token signature")

        header = json.loads(_b64url_decode(header_raw))
        if header.get("alg") != JWT_ALGORITHM:
            raise ValueError("Unsupported token algorithm")

        payload = json.loads(_b64url_decode(payload_raw))
        if int(payload.get("exp", 0)) < int(time.time()):
            raise ValueError("Token expired")

        if not payload.get("sub"):
            raise ValueError("Token subject missing")

        return payload
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict[str, str]:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(credentials.credentials)
    return {"username": payload["sub"]}

async def get_oauth_token() -> str:
    now = time.time()
    if _cache["token"] and now < _cache["expires_at"]:
        return _cache["token"]

    client_id = os.getenv("CLIENT_ID", "")
    client_secret = os.getenv("CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise RuntimeError("Missing CLIENT_ID or CLIENT_SECRET in .env")

    auth_string = f"{client_id}:{client_secret}"
    encoded_auth = base64.b64encode(auth_string.encode("utf-8")).decode("utf-8")

    headers = {
        "Authorization": f"Basic {encoded_auth}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            TOKEN_URL,
            data={"grant_type": "client_credentials"},
            headers=headers,
        )
        response.raise_for_status()
        token = response.json()["access_token"]

    # keep 55 mins
    _cache["token"] = token
    _cache["expires_at"] = now + 55 * 60
    return token
