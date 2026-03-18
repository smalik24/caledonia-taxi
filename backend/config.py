import os
from pathlib import Path
from dotenv import load_dotenv

# Always load .env from the project root (one level up from backend/)
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

# OpenRouteService
ORS_API_KEY = os.getenv("ORS_API_KEY", "")

# Twilio
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")

# App
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))
APP_SECRET_KEY = os.getenv("APP_SECRET_KEY", "dev-secret-key")

# Admin
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin1234")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"

# Fare Configuration (CAD)
BASE_FARE = float(os.getenv("BASE_FARE", "4.50"))
PER_KM_RATE = float(os.getenv("PER_KM_RATE", "2.10"))
MINIMUM_FARE = float(os.getenv("MINIMUM_FARE", "8.00"))

# Dispatch
DISPATCH_TIMEOUT_SECONDS = 30
MAX_DISPATCH_ATTEMPTS = 4

# CORS — comma-separated list of allowed origins
ALLOWED_ORIGINS = [o.strip() for o in os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000"
).split(",")]

# Stripe
STRIPE_SECRET_KEY      = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")

# Web Push / VAPID
VAPID_PUBLIC_KEY  = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_SUBJECT     = os.getenv("VAPID_SUBJECT", "mailto:admin@example.com")

# Promo codes — stored as {CODE: percent_off} e.g. {"FIRST10": 10}
def _parse_promo_codes() -> dict:
    raw = os.getenv("PROMO_CODES", "FIRST10:10,CALEDONIA20:20")
    codes = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if ":" in pair:
            code, pct = pair.split(":", 1)
            try:
                codes[code.strip().upper()] = int(pct.strip())
            except ValueError:
                pass
    return codes

PROMO_CODES: dict = _parse_promo_codes()

import json as _json
import pathlib as _pathlib

_SETTINGS_FILE = _pathlib.Path(__file__).parent / "settings.json"

def load_settings() -> dict:
    """Hot-load settings from settings.json every call. Falls back to env vars."""
    if _SETTINGS_FILE.exists():
        with open(_SETTINGS_FILE) as f:
            return _json.load(f)
    return {}

def save_settings(data: dict) -> None:
    """Persist settings to settings.json."""
    with open(_SETTINGS_FILE, "w") as f:
        _json.dump(data, f, indent=2)

def get_pricing() -> dict:
    """Get current pricing config (hot-loaded)."""
    s = load_settings()
    p = s.get("pricing", {})
    return {
        "base_fare":      float(p.get("base_fare",      BASE_FARE)),
        "per_km_rate":    float(p.get("per_km_rate",    PER_KM_RATE)),
        "minimum_fare":   float(p.get("minimum_fare",   MINIMUM_FARE)),
        "stop_surcharge": float(p.get("stop_surcharge", 3.00)),
    }

def get_flat_rates() -> dict:
    """Get long-distance flat rates (hot-loaded)."""
    s = load_settings()
    return s.get("flat_rates", {})

def get_surge_config() -> dict:
    """Get surge pricing configuration (hot-loaded)."""
    s = load_settings()
    return s.get("surge", {
        "enabled": True,
        "tier1_pending_min": 3, "tier1_available_max": 2, "tier1_multiplier": 1.5,
        "tier2_pending_min": 5, "tier2_available_max": 1, "tier2_multiplier": 2.0,
    })

def get_active_promo_codes() -> list:
    """Get active promo codes (hot-loaded)."""
    s = load_settings()
    return [pc for pc in s.get("promo_codes", []) if pc.get("active", True)]
