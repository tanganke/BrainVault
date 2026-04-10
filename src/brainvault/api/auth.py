"""JWT-based authentication for the BrainVault REST API.

Tokens carry ``sub`` (user id) and optional ``vault_id`` claims.
The signing secret is read from the ``BRAINVAULT_API_SECRET`` environment
variable (falls back to a dev-only default that is **not** safe for
production).

Usage::

    token = create_token(user_id="alice")
    payload = verify_token(token)        # {"sub": "alice", ...}
"""

from __future__ import annotations

import os
import time
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_SECRET = "brainvault-dev-secret-change-me!"  # noqa: S105 – dev only (≥32 bytes)
API_SECRET: str = os.environ.get("BRAINVAULT_API_SECRET", _DEFAULT_SECRET)
ALGORITHM = "HS256"
TOKEN_EXPIRE_SECONDS = 86400  # 24 h

_bearer_scheme = HTTPBearer(auto_error=True)


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------


def create_token(user_id: str, extra: dict[str, Any] | None = None) -> str:
    """Return a signed JWT for *user_id*.

    Args:
        user_id: The ``sub`` claim value.
        extra: Optional additional claims merged into the payload.
    """
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": user_id,
        "iat": now,
        "exp": now + TOKEN_EXPIRE_SECONDS,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, API_SECRET, algorithm=ALGORITHM)


def verify_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT, returning its payload dict.

    Raises:
        jwt.ExpiredSignatureError: If the token has expired.
        jwt.InvalidTokenError: If the token is malformed or signature fails.
    """
    return jwt.decode(token, API_SECRET, algorithms=[ALGORITHM])


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),  # noqa: B008
) -> str:
    """FastAPI dependency that extracts and validates the JWT.

    Returns:
        The ``sub`` (user id) string from the token.

    Raises:
        HTTPException 401: If the token is missing, expired, or invalid.
    """
    try:
        payload = verify_token(credentials.credentials)
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from exc
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing 'sub' claim",
        )
    return sub
