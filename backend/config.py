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
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() == "true"

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
