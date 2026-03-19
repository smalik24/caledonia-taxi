"""Tests for auth_service JWT + bcrypt functionality."""
import sys
sys.path.insert(0, "/Users/saqib/Downloads/caledonia-taxi/backend")
import pytest


def test_hash_and_verify_password():
    from auth_service import hash_password, verify_password
    hashed = hash_password("secret123")
    assert hashed != "secret123"
    assert hashed.startswith("$2b$") or hashed.startswith("$2a$")  # bcrypt prefix
    assert verify_password("secret123", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_create_and_verify_driver_token():
    from auth_service import create_driver_token, verify_driver_token
    token = create_driver_token("driver-uuid-123", "+12895551002")
    assert isinstance(token, str)
    payload = verify_driver_token(token)
    assert payload["driver_id"] == "driver-uuid-123"
    assert payload["phone"] == "+12895551002"


def test_verify_expired_token_raises():
    from auth_service import create_driver_token, verify_driver_token
    from fastapi import HTTPException
    # negative minutes = already expired
    token = create_driver_token("driver-1", "+1", expire_minutes=-1)
    with pytest.raises(HTTPException) as exc:
        verify_driver_token(token)
    assert exc.value.status_code == 401


def test_admin_session_token_still_works():
    """Backward compat: itsdangerous session tokens still work."""
    from auth_service import create_session_token, verify_session_token
    token = create_session_token("test-secret-key")
    assert verify_session_token(token, "test-secret-key") is True
    assert verify_session_token("invalid-token", "test-secret-key") is False


def test_safe_compare_still_works():
    from auth_service import safe_compare, SESSION_DURATION_SECONDS
    assert safe_compare("abc", "abc") is True
    assert safe_compare("abc", "xyz") is False
    assert SESSION_DURATION_SECONDS == 8 * 3600
