"""Test config.py Pydantic BaseSettings."""
import sys
sys.path.insert(0, "/Users/saqib/Downloads/caledonia-taxi/backend")


def test_settings_have_defaults():
    """Settings class provides sensible defaults without any env vars."""
    from config import settings
    assert settings.app_name == "Caledonia Taxi"
    assert settings.demo_mode is True  # no supabase → demo
    assert settings.base_fare_cad > 0
    assert settings.jwt_expire_minutes > 0


def test_backward_compat_exports():
    """Old-style module-level names still work."""
    from config import (
        SUPABASE_URL, ADMIN_PASSWORD, APP_SECRET_KEY,
        BASE_FARE, PER_KM_RATE, DISPATCH_TIMEOUT_SECONDS,
        ALLOWED_ORIGINS, STRIPE_SECRET_KEY, VAPID_PUBLIC_KEY,
        PROMO_CODES, COOKIE_SECURE
    )
    assert isinstance(ADMIN_PASSWORD, str)
    assert isinstance(BASE_FARE, float)
    assert DISPATCH_TIMEOUT_SECONDS > 0
    assert isinstance(ALLOWED_ORIGINS, list)
    assert isinstance(PROMO_CODES, dict)


def test_demo_mode_auto_enabled():
    """demo_mode is True when SUPABASE_URL is empty."""
    import os
    from config import settings
    if not os.getenv("SUPABASE_URL"):
        assert settings.demo_mode is True


def test_get_pricing_returns_dict():
    """get_pricing() returns a dict with expected keys."""
    from config import get_pricing
    p = get_pricing()
    assert "base_fare" in p
    assert "per_km_rate" in p
    assert "minimum_fare" in p
    assert p["base_fare"] > 0
