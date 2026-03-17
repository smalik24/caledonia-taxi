"""Admin session management using itsdangerous TimestampSigner."""
import secrets as _secrets
from itsdangerous import TimestampSigner, BadSignature, SignatureExpired

SESSION_DURATION_SECONDS = 8 * 3600  # 8 hours


def create_session_token(secret_key: str) -> str:
    signer = TimestampSigner(secret_key)
    return signer.sign(b"admin").decode()


def verify_session_token(token: str, secret_key: str) -> bool:
    signer = TimestampSigner(secret_key)
    try:
        signer.unsign(token, max_age=SESSION_DURATION_SECONDS)
        return True
    except (BadSignature, SignatureExpired):
        return False


def safe_compare(a: str, b: str) -> bool:
    """Timing-safe string comparison."""
    return _secrets.compare_digest(a.encode(), b.encode())
