"""
Caledonia Taxi — Auth Service
- Admin: itsdangerous TimestampSigner (session cookie, 8h)
- Driver: JWT (python-jose, HS256, configurable expiry)
- Passwords: bcrypt via passlib
"""
from __future__ import annotations
import secrets as _secrets
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from itsdangerous import TimestampSigner, BadSignature, SignatureExpired
from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import HTTPException, Request, Cookie

logger = logging.getLogger("caledonia.auth")

# ── Constants ─────────────────────────────────────────────────────────────────
SESSION_DURATION_SECONDS = 8 * 3600   # 8 hours (admin sessions)
ALGORITHM = "HS256"

# bcrypt context
_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Password Hashing ──────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return _pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return _pwd_ctx.verify(plain, hashed)


# ── Admin Session Tokens (itsdangerous) ───────────────────────────────────────

def create_session_token(secret_key: str) -> str:
    """Create a signed admin session token (8h TTL)."""
    signer = TimestampSigner(secret_key)
    return signer.sign(b"admin").decode()


def verify_session_token(token: str, secret_key: str) -> bool:
    """Verify an admin session token."""
    signer = TimestampSigner(secret_key)
    try:
        signer.unsign(token, max_age=SESSION_DURATION_SECONDS)
        return True
    except (BadSignature, SignatureExpired):
        return False


def safe_compare(a: str, b: str) -> bool:
    """Timing-safe string comparison to prevent timing attacks."""
    return _secrets.compare_digest(a.encode(), b.encode())


# ── Driver JWT Tokens ─────────────────────────────────────────────────────────

def create_driver_token(
    driver_id: str,
    phone: str,
    expire_minutes: Optional[int] = None,
    secret: Optional[str] = None,
) -> str:
    """Create a signed JWT for driver authentication."""
    from config import settings

    if expire_minutes is None:
        expire_minutes = settings.jwt_expire_minutes
    if secret is None:
        secret = settings.jwt_secret

    expire = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)
    payload = {
        "sub": driver_id,
        "driver_id": driver_id,
        "phone": phone,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "driver",
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def verify_driver_token(
    token: str,
    secret: Optional[str] = None,
) -> dict:
    """
    Verify a driver JWT and return the payload dict.
    Raises HTTPException 401 if invalid or expired.
    """
    from config import settings

    if secret is None:
        secret = settings.jwt_secret

    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
        if payload.get("type") != "driver":
            raise HTTPException(status_code=401, detail="Invalid token type")
        return payload
    except JWTError as exc:
        logger.warning(f"[Auth] Invalid driver token: {exc}")
        raise HTTPException(status_code=401, detail="Driver token invalid or expired")


# ── FastAPI Dependencies ───────────────────────────────────────────────────────

def get_current_admin(request: Request, admin_session: str = Cookie(default=None)):
    """
    FastAPI dependency: validate admin session cookie.
    Raises 401 if missing or expired.
    """
    from config import APP_SECRET_KEY
    if not admin_session or not verify_session_token(admin_session, APP_SECRET_KEY):
        raise HTTPException(status_code=401, detail="Admin authentication required")
    return {"role": "admin"}


def get_current_driver(request: Request) -> dict:
    """
    FastAPI dependency: validate driver JWT from Authorization header or cookie.
    Raises 401 if missing or expired.
    """
    # Try Bearer header first, then cookie
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    else:
        token = request.cookies.get("driver_token", "")

    if not token:
        raise HTTPException(status_code=401, detail="Driver authentication required")

    return verify_driver_token(token)
