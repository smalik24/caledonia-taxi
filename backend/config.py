"""
Caledonia Taxi — Application Settings
Uses Pydantic BaseSettings for type-safe, validated env-var configuration.
Backward-compatible module-level exports maintained for main.py imports.
"""
from __future__ import annotations
import json
import pathlib
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # ── Supabase ──────────────────────────────────────────────────────────────
    supabase_url:         Optional[str] = None
    supabase_key:         Optional[str] = None
    supabase_service_key: Optional[str] = None

    # ── OpenRouteService ──────────────────────────────────────────────────────
    ors_api_key: str = ""

    # ── Twilio ────────────────────────────────────────────────────────────────
    twilio_account_sid:   str = ""
    twilio_auth_token:    str = ""
    twilio_phone_number:  str = ""

    # ── App / Security ────────────────────────────────────────────────────────
    app_host:        str   = "0.0.0.0"
    app_port:        int   = 8000
    app_secret_key:  str   = "dev-secret-key"
    app_name:        str   = "Caledonia Taxi"
    city:            str   = "Hamilton, Ontario"
    cookie_secure:   bool  = False

    # ── Admin ─────────────────────────────────────────────────────────────────
    admin_password: str = "admin1234"

    # ── JWT ───────────────────────────────────────────────────────────────────
    jwt_secret:          str = "caledonia-dev-secret-change-in-prod"
    jwt_expire_minutes:  int = 1440   # 24 hours for driver tokens

    # ── Demo mode (auto-detected if Supabase not configured) ──────────────────
    demo_mode: bool = True

    # ── Fare Configuration (CAD) ──────────────────────────────────────────────
    base_fare_cad:       float = 4.50
    per_km_rate_cad:     float = 2.10
    per_minute_wait_cad: float = 0.35
    minimum_fare_cad:    float = 8.00
    surge_multiplier:    float = 1.0
    hst_percent:         float = 13.0

    # ── Dispatch ──────────────────────────────────────────────────────────────
    dispatch_timeout_seconds: int   = 30
    max_dispatch_attempts:    int   = 4

    # ── CORS ──────────────────────────────────────────────────────────────────
    allowed_origins: str = "http://localhost:8000,http://127.0.0.1:8000"

    # ── Stripe ────────────────────────────────────────────────────────────────
    stripe_secret_key:      str = ""
    stripe_publishable_key: str = ""

    # ── VAPID / Web Push ──────────────────────────────────────────────────────
    vapid_public_key:  str = ""
    vapid_private_key: str = ""
    vapid_subject:     str = "mailto:admin@example.com"

    # ── External Services ──────────────────────────────────────────────────────
    resend_api_key:     str = ""
    vapi_api_key:       str = ""
    vapi_assistant_id:  str = ""

    # ── Promo Codes (raw env string "CODE:pct,CODE:pct") ─────────────────────
    promo_codes_raw: str = "FIRST10:10,CALEDONIA20:20"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]

    @property
    def promo_codes(self) -> dict:
        codes: dict[str, int] = {}
        for pair in self.promo_codes_raw.split(","):
            pair = pair.strip()
            if ":" in pair:
                code, pct = pair.split(":", 1)
                try:
                    codes[code.strip().upper()] = int(pct.strip())
                except ValueError:
                    pass
        return codes


# ── Singleton ─────────────────────────────────────────────────────────────────
settings = Settings()

# Auto-enable demo mode if Supabase not configured
if not settings.supabase_url:
    settings.demo_mode = True

# ── Settings JSON (runtime-editable pricing) ─────────────────────────────────
_SETTINGS_FILE = pathlib.Path(__file__).parent / "settings.json"


def load_settings() -> dict:
    """Hot-load settings from settings.json every call."""
    if _SETTINGS_FILE.exists():
        with open(_SETTINGS_FILE) as f:
            return json.load(f)
    return {}


def save_settings(data: dict) -> None:
    """Persist settings to settings.json."""
    with open(_SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_pricing() -> dict:
    s = load_settings()
    p = s.get("pricing", {})
    return {
        "base_fare":      float(p.get("base_fare",      settings.base_fare_cad)),
        "per_km_rate":    float(p.get("per_km_rate",    settings.per_km_rate_cad)),
        "minimum_fare":   float(p.get("minimum_fare",   settings.minimum_fare_cad)),
        "stop_surcharge": float(p.get("stop_surcharge", 3.00)),
    }


def get_flat_rates() -> dict:
    return load_settings().get("flat_rates", {})


def get_surge_config() -> dict:
    return load_settings().get("surge", {
        "enabled": True,
        "tier1_pending_min": 3, "tier1_available_max": 2, "tier1_multiplier": 1.5,
        "tier2_pending_min": 5, "tier2_available_max": 1, "tier2_multiplier": 2.0,
    })


def get_active_promo_codes() -> list:
    return [pc for pc in load_settings().get("promo_codes", []) if pc.get("active", True)]


# ── Backward-compatible module-level exports ──────────────────────────────────
# All existing `from config import SUPABASE_URL, ...` imports continue to work.
SUPABASE_URL             = settings.supabase_url or ""
SUPABASE_KEY             = settings.supabase_key or ""
SUPABASE_SERVICE_KEY     = settings.supabase_service_key or ""
ORS_API_KEY              = settings.ors_api_key
TWILIO_ACCOUNT_SID       = settings.twilio_account_sid
TWILIO_AUTH_TOKEN        = settings.twilio_auth_token
TWILIO_PHONE_NUMBER      = settings.twilio_phone_number
APP_HOST                 = settings.app_host
APP_PORT                 = settings.app_port
APP_SECRET_KEY           = settings.app_secret_key
ADMIN_PASSWORD           = settings.admin_password
COOKIE_SECURE            = settings.cookie_secure
BASE_FARE                = settings.base_fare_cad
PER_KM_RATE              = settings.per_km_rate_cad
MINIMUM_FARE             = settings.minimum_fare_cad
DISPATCH_TIMEOUT_SECONDS = settings.dispatch_timeout_seconds
MAX_DISPATCH_ATTEMPTS    = settings.max_dispatch_attempts
ALLOWED_ORIGINS          = settings.allowed_origins_list
STRIPE_SECRET_KEY        = settings.stripe_secret_key
STRIPE_PUBLISHABLE_KEY   = settings.stripe_publishable_key
VAPID_PUBLIC_KEY         = settings.vapid_public_key
VAPID_PRIVATE_KEY        = settings.vapid_private_key
VAPID_SUBJECT            = settings.vapid_subject
PROMO_CODES              = settings.promo_codes
