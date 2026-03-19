"""
Caledonia Taxi — Backend API (FastAPI)
======================================
Professional dispatch system for Hamilton, Ontario.
Includes: bookings, dispatch, SMS, PDF invoicing, heatmap, Voice AI hooks.
"""

import os
import uuid
import json
import asyncio
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from contextlib import asynccontextmanager

# Structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger("caledonia")

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request, Cookie, Depends, Body
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

import stripe as stripe_lib

from config import (
    SUPABASE_URL, SUPABASE_KEY,
    DISPATCH_TIMEOUT_SECONDS, MAX_DISPATCH_ATTEMPTS,
    ADMIN_PASSWORD, APP_SECRET_KEY, COOKIE_SECURE, ALLOWED_ORIGINS,
    STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY,
    VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_SUBJECT,
    PROMO_CODES
)
from auth_service import create_session_token, verify_session_token, safe_compare, SESSION_DURATION_SECONDS
from models import (
    BookingRequest, FareEstimateRequest, DriverLoginRequest,
    DriverLocationUpdate, DriverStatusUpdate, RideActionRequest,
    AdminAssignRequest, FareEstimate, VoiceAIBookingRequest
)
from services import (
    geocode_address, get_route_distance, calculate_fare, fare_from_distance,
    find_nearest_driver, haversine_distance, geocode_route, get_current_surge_multiplier
)
from oasr_parser import parse_oasr_email
from sms_service import (
    sms_booking_confirmed, sms_driver_assigned, sms_driver_arrived,
    sms_ride_started, sms_ride_completed, sms_dispatch_failed,
    sms_booking_cancelled, sms_voice_ai_booking, get_sms_log
)
from invoice_service import send_receipt_email, generate_invoice_pdf, get_email_log
from scheduler import setup_scheduler


# ============================================================
# APP SETUP
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup security warnings ────────────────────────────────────────────
    if APP_SECRET_KEY in ("dev-secret-key", "caledonia-taxi-secret-change-me"):
        logger.warning("⚠️  APP_SECRET_KEY is using an insecure default. Set a strong random value in production!")
    if ADMIN_PASSWORD in ("admin1234", "admin", "password", ""):
        logger.warning("⚠️  ADMIN_PASSWORD is weak or default. Change it before going to production!")
    if not COOKIE_SECURE:
        logger.warning("⚠️  COOKIE_SECURE=false — cookies are not HTTPS-only. Set COOKIE_SECURE=true in production!")
    if not SUPABASE_URL:
        logger.info("ℹ️  Running in demo mode (no Supabase) — data is in-memory only")
    if not VAPID_PRIVATE_KEY:
        logger.warning("⚠️  VAPID_PRIVATE_KEY not set — push notifications disabled")

    logger.info("🚕  Caledonia Taxi API starting — Hamilton, ON")
    sched = setup_scheduler(bookings_db, dispatch_booking, sms_fn=None)
    sched.start()
    yield
    sched.shutdown(wait=False)
    logger.info("🚕  Caledonia Taxi API stopped.")


app = FastAPI(
    title="Caledonia Taxi API",
    description="Professional Dispatch System — Hamilton, Ontario",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Security headers middleware ──────────────────────────────────────────────
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"]  = "nosniff"
        response.headers["X-Frame-Options"]          = "DENY"
        response.headers["X-XSS-Protection"]         = "1; mode=block"
        response.headers["Referrer-Policy"]           = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"]        = "geolocation=(), camera=(), microphone=()"
        # Only set HSTS in production (when COOKIE_SECURE is true)
        if COOKIE_SECURE:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        # Never cache HTML pages — ensures browsers always fetch the latest template
        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        return response

app.add_middleware(SecurityHeadersMiddleware)


# ── Simple in-memory rate limiter for auth endpoints ────────────────────────
import time as _time
_auth_attempts: dict[str, list] = {}  # ip -> [timestamp, ...]
_RATE_LIMIT_WINDOW = 60   # seconds
_RATE_LIMIT_MAX    = 10   # attempts per window

def _check_rate_limit(ip: str) -> bool:
    """Return True if the IP is within rate limit, False if exceeded."""
    now  = _time.time()
    hits = _auth_attempts.get(ip, [])
    hits = [t for t in hits if now - t < _RATE_LIMIT_WINDOW]
    hits.append(now)
    _auth_attempts[ip] = hits
    return len(hits) <= _RATE_LIMIT_MAX

BASE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "frontend", "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "frontend", "static")), name="static")


# ============================================================
# DATABASE (Supabase or in-memory demo)
# ============================================================

def get_db():
    if SUPABASE_URL and SUPABASE_KEY:
        from supabase import create_client
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    return None


# ---- Demo data ----
demo_drivers = [
    {
        "id": "d1", "name": "Saqib",    "phone": "+12895551001", "pin": "1234",
        "status": "available", "latitude": 43.2557, "longitude": -79.8711,
        "vehicle": "White Honda CR-V", "plate": "CTXI-001",
        "rating": 4.9, "trips_completed": 342,
        "last_location_update": None
    },
    {
        "id": "d2", "name": "Marcus",   "phone": "+12895551002", "pin": "2345",
        "status": "available", "latitude": 43.2500, "longitude": -79.8650,
        "vehicle": "Black Toyota Camry", "plate": "CTXI-002",
        "rating": 4.8, "trips_completed": 215,
        "last_location_update": None
    },
    {
        "id": "d3", "name": "Priya",    "phone": "+12895551003", "pin": "3456",
        "status": "offline",   "latitude": 43.2600, "longitude": -79.8800,
        "vehicle": "Silver Ford Escape", "plate": "CTXI-003",
        "rating": 4.7, "trips_completed": 189,
        "last_location_update": None
    },
    {
        "id": "d4", "name": "James",    "phone": "+12895551004", "pin": "4567",
        "status": "offline",   "latitude": 43.2450, "longitude": -79.8750,
        "vehicle": "Blue Hyundai Sonata", "plate": "CTXI-004",
        "rating": 4.9, "trips_completed": 401,
        "last_location_update": None
    },
]
demo_bookings: list[dict] = []
_booking_counter = 0

# Dict view of demo_drivers keyed by driver ID (for WebSocket handler and tests)
drivers_db: dict[str, dict] = {d["id"]: d for d in demo_drivers}

# Dict view of bookings keyed by booking ID (used by scheduler for advance dispatch)
bookings_db: dict[str, dict] = {}

# Push notification subscriptions keyed by driver_id
push_subscriptions: dict[str, dict] = {}

# Ratings: list of {booking_id, driver_id, rating, comment, created_at}
ratings_db: list[dict] = []

# Dispatch log: list of {booking_id, driver_id, action, timestamp}
dispatch_log: list[dict] = []

# Idempotency store: {key: {created_at: iso, booking_id: str}} — 24h TTL
_idempotency_store: dict[str, dict] = {}


# ============================================================
# WEBSOCKET MANAGER
# ============================================================

class ConnectionManager:
    def __init__(self):
        self.connections: dict[str, list] = {}

    async def connect(self, ws: WebSocket, channel: str):
        await ws.accept()
        self.connections.setdefault(channel, []).append(ws)

    def disconnect(self, ws: WebSocket, channel: str):
        self.connections[channel] = [
            c for c in self.connections.get(channel, []) if c != ws
        ]

    async def broadcast(self, channel: str, data: dict):
        dead = []
        for ws in self.connections.get(channel, []):
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, channel)

    async def send_to_driver(self, driver_id: str, data: dict):
        await self.broadcast(f"driver_{driver_id}", data)


manager = ConnectionManager()


# ============================================================
# ADMIN AUTH
# ============================================================

def require_admin(admin_session: str = Cookie(default=None)):
    if not admin_session or not verify_session_token(admin_session, APP_SECRET_KEY):
        raise HTTPException(status_code=401, detail="Unauthorized")


# ============================================================
# PAGE ROUTES
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/booking", response_class=HTMLResponse)
async def booking_page(request: Request):
    return templates.TemplateResponse("booking.html", {"request": request})


@app.get("/driver", response_class=HTMLResponse)
async def driver_page(request: Request):
    return templates.TemplateResponse("driver.html", {"request": request})


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    admin_session = request.cookies.get("admin_session", "")
    authed = verify_session_token(admin_session, APP_SECRET_KEY) if admin_session else False
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "authed": authed
    })


@app.get("/heatmap", response_class=HTMLResponse)
async def heatmap_page(request: Request):
    return templates.TemplateResponse("heatmap.html", {"request": request})


@app.get("/track/{booking_id}", response_class=HTMLResponse)
async def track_page(request: Request, booking_id: str):
    return templates.TemplateResponse("track.html", {"request": request, "booking_id": booking_id})


@app.post("/admin/login")
async def admin_login(request: Request):
    # Rate-limit auth endpoint
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        logger.warning(f"[Auth] Rate limit exceeded for {client_ip}")
        raise HTTPException(status_code=429, detail="Too many login attempts. Wait 60 seconds.")

    data = await request.json()
    password = data.get("password", "")
    if not safe_compare(password, ADMIN_PASSWORD):
        logger.warning(f"[Auth] Failed admin login attempt from {client_ip}")
        raise HTTPException(status_code=401, detail="Invalid password")

    token = create_session_token(APP_SECRET_KEY)
    response = JSONResponse({"ok": True})
    response.set_cookie(
        "admin_session", token,
        httponly=True, samesite="lax",
        max_age=SESSION_DURATION_SECONDS,
        secure=COOKIE_SECURE
    )
    logger.info(f"[Auth] Admin login successful from {client_ip}")
    return response


@app.get("/admin/logout")
async def admin_logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie("admin_session")
    return response


# ============================================================
# LIVE TRACKING API
# ============================================================

@app.get("/api/track/{booking_id}")
async def get_tracking_data(booking_id: str):
    """Returns live driver location + booking status for the tracking page."""
    db = get_db()
    booking = None
    if db:
        r = db.table("bookings").select("*").eq("id", booking_id).execute()
        if r.data:
            booking = r.data[0]
    else:
        for b in demo_bookings:
            if b["id"] == booking_id:
                booking = b
                break

    if not booking:
        raise HTTPException(404, "Booking not found")

    driver = None
    if booking.get("assigned_driver_id"):
        if db:
            r = db.table("drivers").select("*").eq("id", booking["assigned_driver_id"]).execute()
            if r.data:
                driver = r.data[0]
        else:
            for d in demo_drivers:
                if d["id"] == booking["assigned_driver_id"]:
                    driver = d
                    break

    result = {
        "booking_id":    booking["id"],
        "status":        booking["status"],
        "customer_name": booking["customer_name"],
        "pickup":        booking["pickup_address"],
        "dropoff":       booking["dropoff_address"],
        "fare":          booking.get("estimated_fare", 0),
        "driver":        None,
    }

    if driver:
        result["driver"] = {
            "name":    driver["name"],
            "vehicle": driver.get("vehicle", "Taxi"),
            "plate":   driver.get("plate", ""),
            "lat":     driver.get("latitude"),
            "lng":     driver.get("longitude"),
            "rating":  driver.get("rating", 5.0),
        }

    return result


# ============================================================
# FARE ESTIMATE
# ============================================================

@app.post("/api/estimate-fare")
async def estimate_fare(request: FareEstimateRequest):
    # Build full address list: pickup + intermediate stops + dropoff
    addresses = [request.pickup_address] + list(request.stops or []) + [request.dropoff_address]

    # Geocode all addresses and compute legs
    legs = await geocode_route(addresses)

    # Get current surge
    surge_mult = get_current_surge_multiplier(bookings_db, drivers_db)

    # Get promo discount
    promo_disc = 0.0
    if request.promo_code:
        try:
            from config import get_active_promo_codes
        except ImportError:
            from backend.config import get_active_promo_codes
        for pc in get_active_promo_codes():
            if pc["code"].upper() == request.promo_code.upper():
                promo_disc = pc["discount_pct"] / 100.0
                break

    breakdown = calculate_fare(legs, request.service_type or "standard", surge_mult, promo_disc)
    return {**breakdown, "legs_geocoded": legs, "surge_multiplier": surge_mult}


# ============================================================
# STRIPE PAYMENTS
# ============================================================

@app.post("/api/payments/create-intent")
async def create_payment_intent(req: FareEstimateRequest):
    """Create a Stripe PaymentIntent for the given trip. Amount is always calculated server-side."""
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured")
    stripe_lib.api_key = STRIPE_SECRET_KEY

    # Geocode and calculate fare server-side (never trust client amounts)
    pc = await geocode_address(req.pickup_address)
    dc = await geocode_address(req.dropoff_address)
    if not pc or not dc:
        raise HTTPException(status_code=400, detail="Could not geocode addresses")
    legs = await geocode_route([req.pickup_address] + list(req.stops or []) + [req.dropoff_address])
    fare_breakdown = calculate_fare(legs, req.service_type or "standard")
    fare = fare_breakdown["total"]
    amount_cents = max(int(fare * 100), 50)  # Stripe minimum 50 cents

    intent = stripe_lib.PaymentIntent.create(
        amount=amount_cents,
        currency="cad",
        automatic_payment_methods={"enabled": True},
        metadata={
            "pickup": req.pickup_address,
            "dropoff": req.dropoff_address
        }
    )
    return {
        "client_secret": intent.client_secret,
        "amount": fare,
        "publishable_key": STRIPE_PUBLISHABLE_KEY
    }


# ============================================================
# BOOKINGS
# ============================================================

@app.post("/api/bookings")
async def create_booking(request: Request, req: BookingRequest):
    global _booking_counter

    # Idempotency key deduplication (24h)
    idem_key = request.headers.get("X-Idempotency-Key")
    if idem_key:
        now_ts = datetime.now(timezone.utc)
        existing = _idempotency_store.get(idem_key)
        if existing:
            # Check if within 24h
            created = datetime.fromisoformat(existing["created_at"])
            if (now_ts - created).total_seconds() < 86400:
                # Return cached response
                cached_booking = next((b for b in demo_bookings if b["id"] == existing["booking_id"]), None)
                if cached_booking:
                    return {"success": True, "booking": cached_booking, "idempotent": True}
        # Register key (booking_id filled in after creation)
        _idempotency_store[idem_key] = {"created_at": now_ts.isoformat(), "booking_id": None}

    pickup  = await geocode_address(req.pickup_address)
    dropoff = await geocode_address(req.dropoff_address)
    if not pickup or not dropoff:
        raise HTTPException(400, "Could not geocode addresses")

    addresses = [req.pickup_address] + list(req.stops or []) + [req.dropoff_address]
    legs = await geocode_route(addresses)
    surge_mult = get_current_surge_multiplier(bookings_db, drivers_db)
    fare_breakdown = calculate_fare(legs, req.service_type or "standard", surge_mult)
    fare = fare_breakdown["total"]
    distance = sum(l.get("km", 0.0) for l in legs)
    db   = get_db()

    # ── Advance booking validation ──────────────────────────────
    scheduled_for_iso: Optional[str] = None
    is_scheduled = False
    if req.scheduled_for is not None:
        now_utc = datetime.now(timezone.utc)
        sf = req.scheduled_for
        if sf.tzinfo is None:
            sf = sf.replace(tzinfo=timezone.utc)
        lead_minutes = (sf - now_utc).total_seconds() / 60
        if lead_minutes < 30:
            raise HTTPException(
                status_code=400,
                detail="Scheduled pickup must be at least 30 minutes from now"
            )
        is_scheduled = True
        scheduled_for_iso = sf.isoformat()

    initial_status = "scheduled" if is_scheduled else "pending"

    if db:
        insert_payload = {
            "customer_name":           req.customer_name,
            "customer_phone":          req.customer_phone,
            "pickup_address":          req.pickup_address,
            "pickup_lat":              pickup["lat"],
            "pickup_lng":              pickup["lng"],
            "dropoff_address":         req.dropoff_address,
            "dropoff_lat":             dropoff["lat"],
            "dropoff_lng":             dropoff["lng"],
            "estimated_distance_km":   distance,
            "estimated_fare":          fare,
            "status":                  initial_status,
            "source":                  req.source.value
        }
        if scheduled_for_iso is not None:
            insert_payload["scheduled_for"] = scheduled_for_iso
        result = db.table("bookings").insert(insert_payload).execute()
        booking = result.data[0]
    else:
        _booking_counter += 1
        booking = {
            "id":                      f"b{_booking_counter}",
            "customer_name":           req.customer_name,
            "customer_phone":          req.customer_phone,
            "pickup_address":          req.pickup_address,
            "pickup_lat":              pickup["lat"],
            "pickup_lng":              pickup["lng"],
            "dropoff_address":         req.dropoff_address,
            "dropoff_lat":             dropoff["lat"],
            "dropoff_lng":             dropoff["lng"],
            "estimated_distance_km":   distance,
            "estimated_fare":          fare,
            "status":                  initial_status,
            "assigned_driver_id":      None,
            "source":                  req.source.value,
            "dispatch_attempts":       0,
            "scheduled_for":           scheduled_for_iso,
            "created_at":              datetime.now(timezone.utc).isoformat(),
            "updated_at":              datetime.now(timezone.utc).isoformat()
        }
        demo_bookings.append(booking)

    booking["payment_method"] = req.payment_method if hasattr(req, 'payment_method') else "cash"
    booking["payment_status"] = "paid" if booking.get("payment_method") == "stripe" else "pending"

    await manager.broadcast("admin", {"type": "new_booking", "booking": booking})

    # SMS: booking confirmed
    try:
        sms_booking_confirmed(
            req.customer_phone, req.customer_name,
            booking["id"], fare
        )
    except Exception as e:
        print(f"[SMS] booking_confirmed error: {e}")

    # Store idempotency result
    if idem_key:
        _idempotency_store[idem_key]["booking_id"] = booking["id"]

    if is_scheduled:
        # Do NOT dispatch now — APScheduler will handle this in Task 10
        pass
    else:
        asyncio.create_task(dispatch_booking(booking))

    return {"success": True, "booking": booking}


async def dispatch_booking(booking: dict, excluded_drivers: list[str] = None):
    """Auto-dispatch to nearest driver. Escalate on timeout/decline."""
    db       = get_db()
    excluded: list[str] = list(excluded_drivers or [])
    bid      = booking["id"]
    plat     = booking.get("pickup_lat",  43.2557)
    plng     = booking.get("pickup_lng", -79.8711)

    for attempt in range(MAX_DISPATCH_ATTEMPTS):
        if db:
            drivers = db.table("drivers").select("*").eq("status", "available").execute().data
        else:
            drivers = [d for d in demo_drivers if d["status"] == "available"]

        nearest = find_nearest_driver(drivers, plat, plng, excluded)

        if not nearest:
            await manager.broadcast("admin", {
                "type": "dispatch_failed", "booking_id": bid,
                "message": "No available drivers"
            })
            # SMS: no drivers available
            try:
                sms_dispatch_failed(booking["customer_phone"], booking["customer_name"])
            except Exception:
                pass
            return

        did = nearest["id"]
        excluded.append(did)

        if db:
            db.table("bookings").update({
                "status": "dispatched",
                "assigned_driver_id": did,
                "dispatch_attempts": attempt + 1
            }).eq("id", bid).execute()
            db.table("dispatch_log").insert({
                "booking_id": bid, "driver_id": did, "status": "pending"
            }).execute()
        else:
            for b in demo_bookings:
                if b["id"] == bid:
                    b["status"]            = "dispatched"
                    b["assigned_driver_id"] = did
                    b["dispatch_attempts"] = attempt + 1

        # Calculate rough ETA (straight-line distance / 30 km/h in mins)
        dist_to_pickup = haversine_distance(
            nearest["latitude"], nearest["longitude"], plat, plng
        )
        eta_mins = max(1, int((dist_to_pickup / 30) * 60))

        ride_msg = {
            "type": "new_ride",
            "booking": booking,
            "timeout_seconds": DISPATCH_TIMEOUT_SECONDS,
            "eta_mins": eta_mins
        }
        await manager.send_to_driver(did, ride_msg)

        # Web Push — fires even when the driver app tab is closed
        push_payload = {
            "title":      "🚕 New Ride Request!",
            "body":       f"{booking.get('pickup_address','Pickup')} → {booking.get('dropoff_address','Drop-off')}  •  ${float(booking.get('estimated_fare',0)):.2f}",
            "booking_id": bid,
        }
        asyncio.create_task(send_push_to_driver(did, push_payload))
        await manager.broadcast("admin", {
            "type": "dispatched",
            "booking_id": bid,
            "driver_id": did,
            "driver_name": nearest["name"],
            "attempt": attempt + 1
        })

        await asyncio.sleep(DISPATCH_TIMEOUT_SECONDS)

        # Check if accepted
        accepted = False
        if db:
            row = db.table("bookings").select("status").eq("id", bid).execute().data
            accepted = row and row[0]["status"] == "accepted"
        else:
            for b in demo_bookings:
                if b["id"] == bid and b["status"] == "accepted":
                    accepted = True

        if accepted:
            # SMS: driver assigned
            try:
                vehicle = nearest.get("vehicle", "a taxi")
                sms_driver_assigned(
                    booking["customer_phone"],
                    nearest["name"],
                    vehicle,
                    eta_mins,
                    booking_id=bid
                )
            except Exception:
                pass
            return

        await manager.broadcast("admin", {
            "type": "dispatch_timeout",
            "booking_id": bid,
            "driver_id": did
        })

    await manager.broadcast("admin", {
        "type": "dispatch_failed",
        "booking_id": bid,
        "message": "All drivers timed out or declined"
    })
    try:
        sms_dispatch_failed(booking["customer_phone"], booking["customer_name"])
    except Exception:
        pass


@app.get("/api/bookings")
async def list_bookings(status: Optional[str] = None):
    db = get_db()
    if db:
        q = db.table("bookings").select("*").order("created_at", desc=True)
        if status:
            q = q.eq("status", status)
        return {"bookings": q.execute().data}
    bookings = [b for b in demo_bookings if not status or b["status"] == status]
    return {"bookings": sorted(bookings, key=lambda b: b["created_at"], reverse=True)}


@app.get("/api/bookings/{booking_id}")
async def get_booking(booking_id: str):
    db = get_db()
    if db:
        r = db.table("bookings").select("*").eq("id", booking_id).execute()
        if not r.data:
            raise HTTPException(404, "Not found")
        return {"booking": r.data[0]}
    for b in demo_bookings:
        if b["id"] == booking_id:
            return {"booking": b}
    raise HTTPException(404, "Not found")


@app.patch("/api/bookings/{booking_id}/cancel")
async def cancel_booking(booking_id: str):
    db = get_db()
    booking = None
    if db:
        r = db.table("bookings").select("*").eq("id", booking_id).execute()
        if r.data:
            booking = r.data[0]
        db.table("bookings").update({"status": "cancelled"}).eq("id", booking_id).execute()
    else:
        for b in demo_bookings:
            if b["id"] == booking_id:
                booking = b
                b["status"] = "cancelled"

    await manager.broadcast("admin", {"type": "booking_cancelled", "booking_id": booking_id})

    # Notify assigned driver
    if booking and booking.get("assigned_driver_id"):
        await manager.send_to_driver(booking["assigned_driver_id"], {
            "type": "ride_cancelled",
            "booking_id": booking_id
        })
        # Reset driver status
        if db:
            db.table("drivers").update({"status": "available"}).eq("id", booking["assigned_driver_id"]).execute()
        else:
            for d in demo_drivers:
                if d["id"] == booking["assigned_driver_id"]:
                    d["status"] = "available"

    # SMS: cancellation
    if booking:
        try:
            sms_booking_cancelled(
                booking["customer_phone"],
                booking["customer_name"],
                booking_id
            )
        except Exception:
            pass

    return {"success": True}


@app.get("/api/bookings/{booking_id}/receipt")
async def download_receipt(booking_id: str):
    """Generate and return a PDF receipt for a completed booking."""
    db = get_db()
    booking = None
    if db:
        r = db.table("bookings").select("*").eq("id", booking_id).execute()
        if r.data:
            booking = r.data[0]
    else:
        for b in demo_bookings:
            if b["id"] == booking_id:
                booking = b

    if not booking:
        raise HTTPException(404, "Booking not found")

    pdf_bytes = generate_invoice_pdf(booking)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=receipt_{booking_id[:8]}.pdf"}
    )


# ============================================================
# DRIVERS
# ============================================================

@app.post("/api/drivers/login")
async def driver_login(req: DriverLoginRequest):
    db = get_db()
    if db:
        r = db.table("drivers").select("*").eq("phone", req.phone).eq("pin", req.pin).execute()
        if not r.data:
            raise HTTPException(401, "Invalid credentials")
        driver = r.data[0]
        db.table("drivers").update({"status": "available"}).eq("id", driver["id"]).execute()
    else:
        driver = next(
            (d for d in demo_drivers if d["phone"] == req.phone and d["pin"] == req.pin),
            None
        )
        if not driver:
            raise HTTPException(401, "Invalid credentials")
        driver["status"] = "available"

    return {"success": True, "driver": {
        "id":       driver["id"],
        "name":     driver["name"],
        "phone":    driver["phone"],
        "status":   driver["status"],
        "vehicle":  driver.get("vehicle", ""),
        "plate":    driver.get("plate", ""),
        "rating":   driver.get("rating", 5.0),
    }}


@app.get("/api/drivers")
async def list_drivers():
    db = get_db()
    if db:
        return {"drivers": db.table("drivers").select(
            "id,name,phone,status,latitude,longitude,vehicle,plate,rating,last_location_update"
        ).execute().data}
    safe_fields = {"id","name","phone","status","latitude","longitude","vehicle","plate","rating","last_location_update"}
    return {"drivers": [{k: v for k,v in d.items() if k in safe_fields} for d in demo_drivers]}


@app.patch("/api/drivers/{driver_id}/status")
async def update_driver_status(driver_id: str, req: DriverStatusUpdate):
    db = get_db()
    if db:
        db.table("drivers").update({"status": req.status.value}).eq("id", driver_id).execute()
    else:
        for d in demo_drivers:
            if d["id"] == driver_id:
                d["status"] = req.status.value
    await manager.broadcast("admin", {
        "type": "driver_status_changed",
        "driver_id": driver_id,
        "status": req.status.value
    })
    return {"success": True}


@app.patch("/api/drivers/{driver_id}/location")
async def update_driver_location(driver_id: str, req: DriverLocationUpdate):
    now = datetime.now(timezone.utc).isoformat()
    db  = get_db()
    if db:
        db.table("drivers").update({
            "latitude": req.latitude, "longitude": req.longitude,
            "last_location_update": now
        }).eq("id", driver_id).execute()
    else:
        for d in demo_drivers:
            if d["id"] == driver_id:
                d["latitude"]  = req.latitude
                d["longitude"] = req.longitude
                d["last_location_update"] = now
    return {"success": True}


# ============================================================
# RIDE ACTIONS
# ============================================================

@app.post("/api/rides/{booking_id}/action/{driver_id}")
async def ride_action(booking_id: str, driver_id: str, req: RideActionRequest):
    db  = get_db()
    now = datetime.now(timezone.utc).isoformat()

    if req.action == "accept":
        if db:
            db.table("bookings").update({
                "status": "accepted", "assigned_driver_id": driver_id
            }).eq("id", booking_id).execute()
            db.table("drivers").update({"status": "busy"}).eq("id", driver_id).execute()
            db.table("dispatch_log").update({
                "status": "accepted", "responded_at": now
            }).eq("booking_id", booking_id).eq("driver_id", driver_id).execute()
        else:
            for b in demo_bookings:
                if b["id"] == booking_id:
                    b["status"] = "accepted"
                    b["assigned_driver_id"] = driver_id
            for d in demo_drivers:
                if d["id"] == driver_id:
                    d["status"] = "busy"

        await manager.broadcast("admin", {
            "type": "ride_accepted",
            "booking_id": booking_id,
            "driver_id": driver_id
        })
    elif req.action == "decline":
        # Set driver back to available
        if db:
            db.table("drivers").update({"status": "available"}).eq("id", driver_id).execute()
            db.table("dispatch_log").update({
                "status": "declined", "responded_at": now
            }).eq("booking_id", booking_id).eq("driver_id", driver_id).execute()
        else:
            for d in demo_drivers:
                if d["id"] == driver_id:
                    d["status"] = "available"

        dispatch_log.append({
            "booking_id": booking_id, "driver_id": driver_id,
            "action": "decline", "timestamp": now
        })

        await manager.broadcast("admin", {
            "type": "driver_declined",
            "booking_id": booking_id,
            "driver_id": driver_id
        })

        # Re-dispatch excluding this driver
        booking = None
        if db:
            r = db.table("bookings").select("*").eq("id", booking_id).execute()
            if r.data: booking = r.data[0]
        else:
            for b in demo_bookings:
                if b["id"] == booking_id:
                    booking = b
                    break

        if booking and booking.get("status") not in ("accepted", "completed", "cancelled"):
            asyncio.create_task(dispatch_booking(booking, excluded_drivers=[driver_id]))

        return {"success": True, "message": "declined, re-dispatching"}
    else:
        # legacy fallback
        await manager.broadcast("admin", {
            "type": "ride_declined",
            "booking_id": booking_id,
            "driver_id": driver_id
        })

    return {"success": True}


@app.post("/api/rides/{booking_id}/start/{driver_id}")
async def start_ride(booking_id: str, driver_id: str):
    db = get_db()
    booking = None
    if db:
        r = db.table("bookings").select("*").eq("id", booking_id).execute()
        if r.data:
            booking = r.data[0]
        db.table("bookings").update({"status": "in_progress"}).eq("id", booking_id).execute()
    else:
        for b in demo_bookings:
            if b["id"] == booking_id:
                booking = b
                b["status"] = "in_progress"

    await manager.broadcast("admin", {
        "type": "ride_started",
        "booking_id": booking_id,
        "driver_id": driver_id
    })

    # SMS: ride started
    if booking:
        try:
            sms_ride_started(booking["customer_phone"], booking["dropoff_address"])
        except Exception:
            pass

    return {"success": True}


@app.post("/api/rides/{booking_id}/complete/{driver_id}")
async def complete_ride(booking_id: str, driver_id: str):
    db = get_db()
    booking = None
    if db:
        r = db.table("bookings").select("*").eq("id", booking_id).execute()
        if r.data:
            booking = r.data[0]
        db.table("bookings").update({"status": "completed"}).eq("id", booking_id).execute()
        db.table("drivers").update({"status": "available"}).eq("id", driver_id).execute()
    else:
        for b in demo_bookings:
            if b["id"] == booking_id:
                booking = b
                b["status"] = "completed"
        for d in demo_drivers:
            if d["id"] == driver_id:
                d["status"] = "available"

    await manager.broadcast("admin", {
        "type": "ride_completed",
        "booking_id": booking_id,
        "driver_id": driver_id
    })

    # SMS + PDF receipt email
    if booking:
        try:
            sms_ride_completed(
                booking["customer_phone"], booking["customer_name"],
                float(booking.get("estimated_fare", 0)), booking_id
            )
        except Exception:
            pass
        try:
            send_receipt_email(booking)
        except Exception as e:
            print(f"[Receipt] email error: {e}")

    return {"success": True}


# ============================================================
# ADMIN
# ============================================================

@app.post("/api/admin/assign", dependencies=[Depends(require_admin)])
async def admin_assign(req: AdminAssignRequest):
    db = get_db()
    if db:
        db.table("bookings").update({
            "status": "dispatched", "assigned_driver_id": req.driver_id
        }).eq("id", req.booking_id).execute()
    else:
        for b in demo_bookings:
            if b["id"] == req.booking_id:
                b["status"] = "dispatched"
                b["assigned_driver_id"] = req.driver_id

    # Get booking for dispatch
    booking = None
    for b in demo_bookings:
        if b["id"] == req.booking_id:
            booking = b

    await manager.send_to_driver(req.driver_id, {
        "type": "new_ride",
        "booking": booking or {"id": req.booking_id},
        "timeout_seconds": DISPATCH_TIMEOUT_SECONDS
    })
    await manager.broadcast("admin", {
        "type": "manually_assigned",
        "booking_id": req.booking_id,
        "driver_id": req.driver_id
    })
    return {"success": True}


@app.post("/api/admin/dispatch", dependencies=[Depends(require_admin)])
async def admin_dispatch(body: dict = Body(...)):
    """Re-trigger auto-dispatch for a pending/failed booking."""
    booking_id = body.get("booking_id")
    db = get_db()
    booking = None
    if db:
        r = db.table("bookings").select("*").eq("id", booking_id).execute()
        if r.data:
            booking = r.data[0]
    else:
        for b in demo_bookings:
            if b["id"] == booking_id:
                booking = b
                break
    if not booking:
        raise HTTPException(404, "Booking not found")
    asyncio.create_task(dispatch_booking(booking))
    return {"success": True}


@app.get("/api/admin/stats", dependencies=[Depends(require_admin)])
async def admin_stats():
    db       = get_db()
    bookings = db.table("bookings").select("status").execute().data if db else demo_bookings
    drivers  = db.table("drivers").select("status").execute().data  if db else demo_drivers
    return {
        "total_bookings":    len(bookings),
        "pending":   sum(1 for b in bookings if b["status"] == "pending"),
        "active":    sum(1 for b in bookings if b["status"] in ("dispatched","accepted","in_progress")),
        "completed": sum(1 for b in bookings if b["status"] == "completed"),
        "cancelled": sum(1 for b in bookings if b["status"] == "cancelled"),
        "drivers_available": sum(1 for d in drivers if d["status"] == "available"),
        "drivers_busy":      sum(1 for d in drivers if d["status"] == "busy"),
        "drivers_offline":   sum(1 for d in drivers if d["status"] == "offline"),
    }


@app.get("/api/admin/sms-log", dependencies=[Depends(require_admin)])
async def sms_log():
    return {"sms_log": get_sms_log()}


@app.get("/api/admin/email-log", dependencies=[Depends(require_admin)])
async def email_log():
    return {"email_log": get_email_log()}


@app.get("/api/admin/heatmap-data", dependencies=[Depends(require_admin)])
async def heatmap_data():
    """
    Returns booking pickup coordinates for the heatmap.
    Also returns zone aggregation (top 10 pickup zones).
    """
    from services import HAMILTON_LANDMARKS

    db = get_db()
    if db:
        bookings = db.table("bookings").select(
            "pickup_lat,pickup_lng,pickup_address,created_at,status"
        ).execute().data
    else:
        bookings = demo_bookings

    points = []
    for b in bookings:
        lat = b.get("pickup_lat")
        lng = b.get("pickup_lng")
        if lat and lng:
            points.append({
                "lat": lat,
                "lng": lng,
                "weight": 1.0,
                "address": b.get("pickup_address", ""),
                "timestamp": b.get("created_at", "")
            })

    # Build zone aggregations from known landmarks + address matching
    zone_counts: dict[str, int] = {}
    for b in bookings:
        addr = (b.get("pickup_address") or "").lower()
        matched = False
        for landmark, coords in HAMILTON_LANDMARKS.items():
            if landmark in addr:
                zone_counts[landmark.title()] = zone_counts.get(landmark.title(), 0) + 1
                matched = True
                break
        if not matched:
            zone_counts["Other Hamilton"] = zone_counts.get("Other Hamilton", 0) + 1

    zones = sorted(
        [{"name": k, "count": v} for k, v in zone_counts.items()],
        key=lambda x: x["count"], reverse=True
    )

    return {
        "points": points,
        "zones": zones,
        "total_bookings": len(bookings)
    }


# ============================================================
# VOICE AI HOOKS
# ============================================================

@app.post("/api/voice-ai/booking")
async def voice_ai_booking(req: VoiceAIBookingRequest):
    """
    Endpoint for Voice AI agents (Vapi, Bland, Retell) to create bookings.

    Example POST body:
    {
        "customer_name": "Jane Smith",
        "customer_phone": "+12895559999",
        "pickup_address": "Hamilton GO Station",
        "dropoff_address": "McMaster University",
        "agent_id": "vapi_agent_abc123",
        "call_id": "call_xyz789",
        "notes": "Customer prefers rear seat"
    }
    """
    global _booking_counter

    pickup  = await geocode_address(req.pickup_address)
    dropoff = await geocode_address(req.dropoff_address)
    if not pickup or not dropoff:
        raise HTTPException(400, "Could not geocode addresses")

    distance = await get_route_distance(
        pickup["lat"], pickup["lng"], dropoff["lat"], dropoff["lng"]
    )
    fare = fare_from_distance(distance)
    db   = get_db()

    if db:
        result = db.table("bookings").insert({
            "customer_name":         req.customer_name,
            "customer_phone":        req.customer_phone,
            "pickup_address":        req.pickup_address,
            "pickup_lat":            pickup["lat"],
            "pickup_lng":            pickup["lng"],
            "dropoff_address":       req.dropoff_address,
            "dropoff_lat":           dropoff["lat"],
            "dropoff_lng":           dropoff["lng"],
            "estimated_distance_km": distance,
            "estimated_fare":        fare,
            "status":                "pending",
            "source":                "voice_ai"
        }).execute()
        booking = result.data[0]
    else:
        _booking_counter += 1
        booking = {
            "id":                    f"b{_booking_counter}",
            "customer_name":         req.customer_name,
            "customer_phone":        req.customer_phone,
            "pickup_address":        req.pickup_address,
            "pickup_lat":            pickup["lat"],
            "pickup_lng":            pickup["lng"],
            "dropoff_address":       req.dropoff_address,
            "dropoff_lat":           dropoff["lat"],
            "dropoff_lng":           dropoff["lng"],
            "estimated_distance_km": distance,
            "estimated_fare":        fare,
            "status":                "pending",
            "assigned_driver_id":    None,
            "source":                "voice_ai",
            "dispatch_attempts":     0,
            "voice_agent_id":        req.agent_id,
            "call_id":               req.call_id,
            "notes":                 req.notes,
            "created_at":            datetime.now(timezone.utc).isoformat(),
            "updated_at":            datetime.now(timezone.utc).isoformat()
        }
        demo_bookings.append(booking)

    await manager.broadcast("admin", {"type": "new_booking", "booking": booking})

    # SMS confirmation
    try:
        sms_voice_ai_booking(
            req.customer_phone, req.pickup_address, req.dropoff_address, fare
        )
    except Exception:
        pass

    asyncio.create_task(dispatch_booking(booking))

    return {
        "success": True,
        "booking_id": booking["id"],
        "estimated_fare": fare,
        "distance_km": distance,
        "message": f"Booking confirmed. Est. fare ${fare:.2f} CAD. Driver dispatching now.",
        "booking": booking
    }


@app.get("/api/voice-ai/status/{booking_id}")
async def voice_ai_status(booking_id: str):
    """
    Voice AI polls this to get ride status for verbal readback.
    Returns a human-readable status string.
    """
    db = get_db()
    booking = None
    if db:
        r = db.table("bookings").select("*").eq("id", booking_id).execute()
        if r.data:
            booking = r.data[0]
    else:
        for b in demo_bookings:
            if b["id"] == booking_id:
                booking = b

    if not booking:
        raise HTTPException(404, "Booking not found")

    status = booking["status"]
    driver_name = None
    if booking.get("assigned_driver_id"):
        for d in demo_drivers:
            if d["id"] == booking["assigned_driver_id"]:
                driver_name = d["name"]

    # Human-readable for TTS
    tts_messages = {
        "pending":     "Your ride is pending. We are searching for a driver.",
        "dispatched":  f"A driver has been notified. {'Driver ' + driver_name + ' is responding.' if driver_name else ''}",
        "accepted":    f"{'Driver ' + driver_name + ' has accepted' if driver_name else 'Your driver has accepted'} your ride and is on the way.",
        "in_progress": "Your ride is currently in progress.",
        "completed":   "Your ride is complete. Thank you for choosing Caledonia Taxi!",
        "cancelled":   "This booking has been cancelled."
    }

    return {
        "booking_id": booking_id,
        "status": status,
        "driver_name": driver_name,
        "estimated_fare": booking.get("estimated_fare"),
        "tts_message": tts_messages.get(status, f"Status: {status}.")
    }


@app.post("/api/voice-ai/fare-estimate")
async def voice_ai_fare_estimate(req: FareEstimateRequest):
    """
    Voice AI calls this to get a fare to read back to the caller.
    Returns a TTS-friendly response.
    """
    pickup  = await geocode_address(req.pickup_address)
    dropoff = await geocode_address(req.dropoff_address)
    if not pickup or not dropoff:
        raise HTTPException(400, "Could not geocode addresses")
    distance = await get_route_distance(
        pickup["lat"], pickup["lng"], dropoff["lat"], dropoff["lng"]
    )
    fare = fare_from_distance(distance)
    return {
        "distance_km": distance,
        "estimated_fare": fare,
        "tts_message": (
            f"Your estimated fare is {fare:.0f} dollars "
            f"for approximately {distance:.1f} kilometres. "
            f"Shall I confirm your booking?"
        )
    }


# ============================================================
# WEBSOCKETS
# ============================================================

@app.websocket("/ws/{channel}")
async def ws_generic(ws: WebSocket, channel: str):
    await manager.connect(ws, channel)
    try:
        while True:
            msg = json.loads(await ws.receive_text())
            if msg.get("type") == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(ws, channel)


@app.websocket("/ws/driver/{driver_id}")
async def ws_driver(ws: WebSocket, driver_id: str):
    await manager.connect(ws, f"driver_{driver_id}")
    try:
        while True:
            msg = json.loads(await ws.receive_text())
            if msg.get("type") == "ping":
                await ws.send_json({"type": "pong"})
            elif msg.get("type") == "location_update":
                lat = msg.get("lat")
                lng = msg.get("lng")
                if lat is not None and lng is not None and driver_id in drivers_db:
                    drivers_db[driver_id]["latitude"] = lat
                    drivers_db[driver_id]["longitude"] = lng
                    drivers_db[driver_id]["last_location_update"] = datetime.now(timezone.utc).isoformat()
                    await manager.broadcast(f"track_{driver_id}", {
                        "type": "location_update",
                        "driver_id": driver_id,
                        "lat": lat,
                        "lng": lng,
                        "accuracy": msg.get("accuracy"),
                        "timestamp": drivers_db[driver_id]["last_location_update"],
                    })
    except WebSocketDisconnect:
        manager.disconnect(ws, f"driver_{driver_id}")


# ============================================================
# TWILIO PHONE AGENT
# ============================================================

@app.post("/api/twilio/voice")
async def twilio_voice(request: Request):
    try:
        from twilio.twiml.voice_response import VoiceResponse, Gather
        resp   = VoiceResponse()
        gather = Gather(input="speech", action="/api/twilio/gather-pickup",
                        speech_timeout="auto", language="en-CA")
        gather.say(
            "Welcome to Caledonia Taxi! Please say your pickup address.",
            voice="Polly.Joanna"
        )
        resp.append(gather)
        resp.say("Sorry, I didn't catch that. Please call back. Goodbye!")
        return HTMLResponse(content=str(resp), media_type="application/xml")
    except ImportError:
        return HTMLResponse(content="<?xml version='1.0' encoding='UTF-8'?><Response><Say>Twilio not configured.</Say></Response>", media_type="application/xml")


@app.post("/api/twilio/gather-pickup")
async def twilio_pickup(request: Request):
    from twilio.twiml.voice_response import VoiceResponse, Gather
    form   = await request.form()
    pickup = form.get("SpeechResult", "")
    caller = form.get("From", "unknown")
    resp   = VoiceResponse()
    gather = Gather(
        input="speech",
        action=f"/api/twilio/gather-dropoff?pickup={pickup}&caller={caller}",
        speech_timeout="auto", language="en-CA"
    )
    gather.say(f"Got it, picking up from {pickup}. Where are you going?", voice="Polly.Joanna")
    resp.append(gather)
    return HTMLResponse(content=str(resp), media_type="application/xml")


@app.post("/api/twilio/gather-dropoff")
async def twilio_dropoff(request: Request):
    from twilio.twiml.voice_response import VoiceResponse, Gather
    form    = await request.form()
    dropoff = form.get("SpeechResult", "")
    pickup  = request.query_params.get("pickup", "")
    caller  = request.query_params.get("caller", "unknown")
    pc = await geocode_address(pickup)
    dc = await geocode_address(dropoff)
    dist = 5.0
    if pc and dc:
        d = await get_route_distance(pc["lat"], pc["lng"], dc["lat"], dc["lng"])
        if d: dist = d
    fare = fare_from_distance(dist)
    resp   = VoiceResponse()
    gather = Gather(
        input="speech",
        action=f"/api/twilio/confirm?pickup={pickup}&dropoff={dropoff}&fare={fare}&caller={caller}",
        speech_timeout="auto", language="en-CA"
    )
    gather.say(
        f"Your ride from {pickup} to {dropoff} will cost about "
        f"{int(fare)} dollars Canadian. Say yes to confirm, or no to cancel.",
        voice="Polly.Joanna"
    )
    resp.append(gather)
    return HTMLResponse(content=str(resp), media_type="application/xml")


@app.post("/api/twilio/confirm")
async def twilio_confirm(request: Request):
    from twilio.twiml.voice_response import VoiceResponse
    form    = await request.form()
    speech  = form.get("SpeechResult", "").lower()
    pickup  = request.query_params.get("pickup", "")
    dropoff = request.query_params.get("dropoff", "")
    caller  = request.query_params.get("caller", "unknown")
    fare    = float(request.query_params.get("fare", "0"))
    resp    = VoiceResponse()
    if "yes" in speech or "yeah" in speech or "confirm" in speech:
        await create_booking(BookingRequest(
            customer_name="Phone Customer",
            customer_phone=caller,
            pickup_address=pickup,
            dropoff_address=dropoff,
            source="phone"
        ))
        resp.say(
            f"Your ride is booked for {int(fare)} dollars. "
            f"A driver is on the way. You'll receive a text confirmation. "
            f"Thank you for choosing Caledonia Taxi!",
            voice="Polly.Joanna"
        )
    else:
        resp.say(
            "No problem, booking cancelled. "
            "Call us any time at Caledonia Taxi. Goodbye!",
            voice="Polly.Joanna"
        )
    return HTMLResponse(content=str(resp), media_type="application/xml")


# ============================================================
# VAPI VOICE AI WEBHOOK
# ============================================================

@app.post("/api/vapi/webhook")
async def vapi_webhook(request: Request):
    """
    Unified Vapi tool-call handler.
    Vapi POSTs here for every tool the assistant invokes.
    Returns results in the format Vapi expects:
      { "results": [{ "toolCallId": "...", "result": "..." }] }
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    msg = body.get("message", {})

    # Vapi sends type="tool-calls" for function tool invocations
    if msg.get("type") != "tool-calls":
        return {"status": "ok"}

    results = []
    for call in msg.get("toolCallList", []):
        fn   = call.get("function", {})
        name = fn.get("name", "")
        try:
            raw_args = fn.get("arguments", "{}")
            args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        except Exception:
            args = {}

        result = await _dispatch_vapi_tool(name, args)
        results.append({
            "toolCallId": call.get("id", ""),
            "result": json.dumps(result)
        })

    return {"results": results}


async def _dispatch_vapi_tool(name: str, args: dict) -> dict:
    """Route a Vapi tool call to the correct internal handler."""

    if name == "get_fare_estimate":
        pickup  = await geocode_address(args.get("pickup_address", ""))
        dropoff = await geocode_address(args.get("dropoff_address", ""))
        if not pickup or not dropoff:
            return {"error": "Could not locate one of those addresses. Please try again."}
        dist = await get_route_distance(pickup["lat"], pickup["lng"], dropoff["lat"], dropoff["lng"])
        fare = fare_from_distance(dist)
        return {
            "distance_km": dist,
            "estimated_fare": fare,
            "tts_message": (
                f"The estimated fare is ${fare:.2f} Canadian dollars "
                f"for approximately {dist:.1f} kilometres. "
                f"Shall I confirm this booking?"
            )
        }

    elif name == "create_booking":
        global _booking_counter
        pickup  = await geocode_address(args.get("pickup_address", ""))
        dropoff = await geocode_address(args.get("dropoff_address", ""))
        if not pickup or not dropoff:
            return {"error": "Could not geocode addresses."}
        dist = await get_route_distance(pickup["lat"], pickup["lng"], dropoff["lat"], dropoff["lng"])
        fare = fare_from_distance(dist)
        _booking_counter += 1
        booking = {
            "id": f"b{_booking_counter}",
            "customer_name":         args.get("customer_name", "Phone Customer"),
            "customer_phone":        args.get("customer_phone", "unknown"),
            "pickup_address":        args.get("pickup_address", ""),
            "pickup_lat":            pickup["lat"],
            "pickup_lng":            pickup["lng"],
            "dropoff_address":       args.get("dropoff_address", ""),
            "dropoff_lat":           dropoff["lat"],
            "dropoff_lng":           dropoff["lng"],
            "estimated_distance_km": dist,
            "estimated_fare":        fare,
            "status":                "pending",
            "assigned_driver_id":    None,
            "source":                "voice_ai",
            "dispatch_attempts":     0,
            "created_at":            datetime.now(timezone.utc).isoformat(),
            "updated_at":            datetime.now(timezone.utc).isoformat()
        }
        demo_bookings.append(booking)
        await manager.broadcast("admin", {"type": "new_booking", "booking": booking})
        asyncio.create_task(dispatch_booking(booking))
        short_id = booking["id"].upper()
        return {
            "booking_id": booking["id"],
            "estimated_fare": fare,
            "tts_message": (
                f"Your ride is booked! Reference number {short_id}. "
                f"Estimated fare is ${fare:.2f} Canadian. "
                f"A driver is being dispatched now. "
                f"You will receive a text message confirmation. "
                f"Thank you for choosing Caledonia Taxi!"
            )
        }

    elif name == "check_booking_status":
        bid = args.get("booking_id", "")
        for b in demo_bookings:
            if b["id"] == bid:
                status = b["status"]
                driver_name = None
                for d in demo_drivers:
                    if d["id"] == b.get("assigned_driver_id"):
                        driver_name = d["name"]
                msgs = {
                    "pending":     "Your booking is pending. We are finding a driver.",
                    "dispatched":  f"A driver has been notified{' — ' + driver_name if driver_name else ''}.",
                    "accepted":    f"{'Driver ' + driver_name if driver_name else 'Your driver'} has accepted and is on the way.",
                    "in_progress": "Your ride is in progress.",
                    "completed":   "Your ride is complete. Thank you for riding with Caledonia Taxi!",
                    "cancelled":   "This booking has been cancelled."
                }
                return {"status": status, "tts_message": msgs.get(status, f"Status is {status}.")}
        return {"error": "Booking not found.", "tts_message": "I couldn't find that booking reference."}

    else:
        return {"error": f"Unknown tool: {name}"}


# ============================================================
# PUSH NOTIFICATIONS (Web Push / VAPID)
# ============================================================

@app.get("/api/push/vapid-public-key")
async def get_vapid_public_key():
    """Return the VAPID public key so the driver app can subscribe."""
    if not VAPID_PUBLIC_KEY:
        raise HTTPException(503, "Push notifications not configured")
    return {"public_key": VAPID_PUBLIC_KEY}


@app.post("/api/drivers/{driver_id}/push-subscribe")
async def push_subscribe(driver_id: str, request: Request):
    """Save a browser push subscription for a driver."""
    data = await request.json()
    sub = data.get("subscription")
    if not sub or "endpoint" not in sub:
        raise HTTPException(400, "Invalid subscription object")
    push_subscriptions[driver_id] = sub
    logger.info(f"[Push] Driver {driver_id} subscribed — {sub['endpoint'][:60]}…")
    return {"success": True}


@app.delete("/api/drivers/{driver_id}/push-subscribe")
async def push_unsubscribe(driver_id: str):
    push_subscriptions.pop(driver_id, None)
    return {"success": True}


async def send_push_to_driver(driver_id: str, payload: dict):
    """Send a Web Push message to a driver's browser even when the tab is closed."""
    sub = push_subscriptions.get(driver_id)
    if not sub:
        return  # driver hasn't subscribed

    if not VAPID_PRIVATE_KEY:
        logger.warning("[Push] VAPID not configured — skipping push")
        return

    try:
        from pywebpush import webpush, WebPushException
        webpush(
            subscription_info=sub,
            data=json.dumps(payload),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={"sub": VAPID_SUBJECT},
        )
        logger.info(f"[Push] Sent to driver {driver_id}")
    except Exception as e:
        logger.error(f"[Push] Failed for driver {driver_id}: {e}")


# ============================================================
# PROMO CODES
# ============================================================

@app.post("/api/promo/validate")
async def validate_promo(request: Request):
    """Validate a promo code and return the discount percentage."""
    data = await request.json()
    code = str(data.get("code", "")).strip().upper()
    if not code:
        raise HTTPException(400, "No code provided")
    discount = PROMO_CODES.get(code)
    if discount is None:
        raise HTTPException(404, "Invalid or expired promo code")
    return {"code": code, "discount_percent": discount, "valid": True}


# ============================================================
# DRIVER RATINGS
# ============================================================

@app.post("/api/bookings/{booking_id}/rate")
async def rate_driver(booking_id: str, request: Request):
    """Customer rates their driver after a completed ride (1–5 stars)."""
    data = await request.json()
    rating  = int(data.get("rating", 0))
    comment = str(data.get("comment", "")).strip()[:280]

    if not 1 <= rating <= 5:
        raise HTTPException(400, "Rating must be between 1 and 5")

    # Check booking exists and is completed
    db = get_db()
    booking = None
    if db:
        r = db.table("bookings").select("*").eq("id", booking_id).execute()
        if r.data:
            booking = r.data[0]
    else:
        booking = next((b for b in demo_bookings if b["id"] == booking_id), None)

    if not booking:
        raise HTTPException(404, "Booking not found")
    if booking["status"] != "completed":
        raise HTTPException(400, "Can only rate a completed ride")

    # Prevent duplicate ratings
    if any(r["booking_id"] == booking_id for r in ratings_db):
        raise HTTPException(409, "This ride has already been rated")

    driver_id = booking.get("assigned_driver_id")
    entry = {
        "booking_id": booking_id,
        "driver_id":  driver_id,
        "rating":     rating,
        "comment":    comment,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    ratings_db.append(entry)

    # Update driver's running average
    if driver_id:
        driver_ratings = [r["rating"] for r in ratings_db if r["driver_id"] == driver_id]
        avg = sum(driver_ratings) / len(driver_ratings)
        for d in demo_drivers:
            if d["id"] == driver_id:
                d["rating"] = round(avg, 2)
        if db:
            db.table("drivers").update({"rating": round(avg, 2)}).eq("id", driver_id).execute()

    return {"success": True, "average_rating": round(avg, 2) if driver_id else None}


@app.get("/api/drivers/{driver_id}/ratings")
async def get_driver_ratings(driver_id: str):
    """Return all ratings for a driver."""
    driver_ratings = [r for r in ratings_db if r["driver_id"] == driver_id]
    avg = (sum(r["rating"] for r in driver_ratings) / len(driver_ratings)) if driver_ratings else None
    return {
        "driver_id":      driver_id,
        "ratings":        driver_ratings,
        "average_rating": round(avg, 2) if avg else None,
        "total_ratings":  len(driver_ratings),
    }


# ============================================================
# SURGE PRICING CHECK
# ============================================================

@app.get("/api/surge")
async def get_surge_status():
    """
    Returns current surge multiplier based on live demand (config-driven thresholds).
    """
    multiplier = get_current_surge_multiplier(bookings_db, drivers_db)
    pending   = sum(1 for b in bookings_db.values() if b.get("status") == "pending")
    available = sum(1 for d in drivers_db.values()  if d.get("status") == "available")
    return {
        "multiplier":        multiplier,
        "active":            multiplier > 1.0,
        "pending_count":     pending,
        "available_drivers": available,
    }


# ============================================================
# ADMIN — EXTENDED DATA ENDPOINTS
# ============================================================

@app.get("/api/admin/driver-history", dependencies=[Depends(require_admin)])
async def admin_driver_history():
    """Return per-driver trip history with totals for the admin centre."""
    db = get_db()
    if db:
        all_bookings = db.table("bookings").select("*").order("created_at", desc=True).execute().data
        all_drivers_data = db.table("drivers").select("*").execute().data
    else:
        all_bookings    = sorted(demo_bookings, key=lambda b: b["created_at"], reverse=True)
        all_drivers_data = demo_drivers

    result = []
    for d in all_drivers_data:
        did   = d["id"]
        rides = [b for b in all_bookings if b.get("assigned_driver_id") == did]
        completed = [b for b in rides if b["status"] == "completed"]
        total_earnings = sum(float(b.get("actual_fare") or b.get("estimated_fare") or 0) for b in completed)
        driver_rts = [r for r in ratings_db if r["driver_id"] == did]
        avg_rating = round(sum(r["rating"] for r in driver_rts) / len(driver_rts), 2) if driver_rts else d.get("rating", 5.0)
        dispatched_to_driver = [e for e in dispatch_log if e.get("driver_id") == did]
        accepted_by_driver   = [e for e in dispatched_to_driver if e.get("action") == "accept"]
        acceptance_rate = round(len(accepted_by_driver) / len(dispatched_to_driver) * 100) if dispatched_to_driver else 100
        result.append({
            "id":              did,
            "name":            d["name"],
            "phone":           d["phone"],
            "status":          d["status"],
            "vehicle":         d.get("vehicle", ""),
            "plate":           d.get("plate", ""),
            "rating":          avg_rating,
            "total_rides":     len(rides),
            "completed_rides": len(completed),
            "total_earnings":  round(total_earnings, 2),
            "acceptance_rate": acceptance_rate,
            "bookings":        rides[:50],  # cap at 50 per driver
        })
    return {"drivers": result}


@app.get("/api/admin/revenue", dependencies=[Depends(require_admin)])
async def admin_revenue(period: str = "day"):
    """
    Return revenue grouped by period.
    period: "day" (last 30 days), "week" (last 12 weeks), "month" (last 12 months)
    """
    db = get_db()
    if db:
        bookings = db.table("bookings").select("*").eq("status", "completed").execute().data
    else:
        bookings = [b for b in demo_bookings if b["status"] == "completed"]

    buckets: dict[str, float] = {}
    now = datetime.now(timezone.utc)

    for b in bookings:
        try:
            created = datetime.fromisoformat(b["created_at"].replace("Z", "+00:00"))
        except Exception:
            continue
        fare = float(b.get("actual_fare") or b.get("estimated_fare") or 0)

        if period == "day":
            if (now - created).days > 30:
                continue
            key = created.strftime("%Y-%m-%d")
        elif period == "week":
            if (now - created).days > 84:
                continue
            # ISO week key
            key = f"{created.isocalendar()[0]}-W{created.isocalendar()[1]:02d}"
        else:  # month
            if (now - created).days > 365:
                continue
            key = created.strftime("%Y-%m")

        buckets[key] = buckets.get(key, 0.0) + fare

    # Sort chronologically
    sorted_buckets = sorted(buckets.items())
    total = sum(v for _, v in sorted_buckets)
    completed_count = len(bookings)

    return {
        "period":    period,
        "buckets":   [{"label": k, "revenue": round(v, 2)} for k, v in sorted_buckets],
        "total":     round(total, 2),
        "completed": completed_count,
    }


@app.get("/api/admin/receipts", dependencies=[Depends(require_admin)])
async def admin_receipts(
    period: str = "all",
    driver_id: Optional[str] = None,
):
    """Return completed bookings (receipts) with optional period and driver filters."""
    db = get_db()
    if db:
        bookings = db.table("bookings").select("*").eq("status", "completed").order("created_at", desc=True).execute().data
    else:
        bookings = sorted(
            [b for b in demo_bookings if b["status"] == "completed"],
            key=lambda b: b["created_at"], reverse=True
        )

    now = datetime.now(timezone.utc)

    def _cutoff(days: int) -> datetime:
        return now - timedelta(days=days)

    if period == "today":
        cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        cutoff = _cutoff(7)
    elif period == "month":
        cutoff = _cutoff(30)
    else:
        cutoff = None

    result = []
    for b in bookings:
        if driver_id and b.get("assigned_driver_id") != driver_id:
            continue
        if cutoff:
            try:
                created = datetime.fromisoformat(b["created_at"].replace("Z", "+00:00"))
                if created < cutoff:
                    continue
            except Exception:
                pass
        # Attach driver name
        driver = next((d for d in demo_drivers if d["id"] == b.get("assigned_driver_id")), None)
        row = dict(b)
        row["driver_name"] = driver["name"] if driver else "—"
        result.append(row)

    total_revenue = sum(float(b.get("actual_fare") or b.get("estimated_fare") or 0) for b in result)
    return {
        "receipts": result,
        "count":    len(result),
        "total_revenue": round(total_revenue, 2),
    }


# ============================================================
# BOOKING STOPS (add a stop to an in-progress ride)
# ============================================================

@app.post("/api/bookings/{booking_id}/stops")
async def add_stop_to_ride(booking_id: str, body: dict = Body(...)):
    booking = bookings_db.get(booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.get("status") != "in_progress":
        raise HTTPException(status_code=400, detail="Can only add stops to in-progress rides")

    new_addr = body.get("address", "")
    lat = body.get("lat")
    lng = body.get("lng")

    if not lat or not lng:
        coords = await geocode_address(new_addr)
        if coords:
            lat, lng = coords["lat"], coords["lng"]

    stops = list(booking.get("stops", []))
    stops.append(new_addr)
    booking["stops"] = stops
    booking["updated_at"] = datetime.now(timezone.utc).isoformat()

    # Recalculate fare with full updated route
    all_addresses = [booking["pickup_address"]] + stops + [booking["dropoff_address"]]
    legs = await geocode_route(all_addresses)
    breakdown = calculate_fare(legs, booking.get("service_type", "standard"))
    booking["actual_fare"] = breakdown["total"]
    booking["fare_breakdown"] = breakdown

    # Broadcast fare update to tracking page
    await manager.broadcast("admin", {"type": "fare_updated", "booking_id": booking_id,
                     "fare": breakdown["total"], "breakdown": breakdown})

    return {"booking_id": booking_id, "actual_fare": breakdown["total"], "fare_breakdown": breakdown}


# ============================================================
# FLAT RATES
# ============================================================

@app.get("/api/flat-rates")
async def get_flat_rates_endpoint():
    try:
        from config import get_flat_rates
    except ImportError:
        from backend.config import get_flat_rates
    return get_flat_rates()


@app.post("/api/flat-rates")
async def set_flat_rate(body: dict = Body(...), _=Depends(require_admin)):
    try:
        from config import load_settings, save_settings
    except ImportError:
        from backend.config import load_settings, save_settings
    s = load_settings()
    s.setdefault("flat_rates", {})[body["city"]] = float(body["price"])
    save_settings(s)
    return {"ok": True}


@app.delete("/api/flat-rates/{city}")
async def delete_flat_rate(city: str, _=Depends(require_admin)):
    try:
        from config import load_settings, save_settings
    except ImportError:
        from backend.config import load_settings, save_settings
    s = load_settings()
    s.get("flat_rates", {}).pop(city, None)
    save_settings(s)
    return {"ok": True}


# ============================================================
# OASR (Online Advance Service Requests)
# ============================================================

@app.post("/api/oasr/inbound")
async def oasr_inbound(request: Request):
    """Receive OASR email (JSON or SendGrid Inbound Parse form) and create a booking."""
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        data = await request.json()
        raw = data.get("raw_email", "")
    else:
        form = await request.form()
        raw = form.get("text", "") or form.get("html", "") or ""

    if not raw:
        raise HTTPException(status_code=400, detail="No email content provided")

    parsed = parse_oasr_email(raw)

    scheduled_for = None
    if parsed.get("ride_date") and parsed.get("ride_time"):
        try:
            scheduled_for = f"{parsed['ride_date']}T{parsed['ride_time']}:00+00:00"
        except Exception:
            pass

    booking_id = str(uuid.uuid4())[:8].upper()
    now = datetime.now(timezone.utc).isoformat()
    booking = {
        "id": booking_id,
        "customer_name": parsed.get("patient_name") or "OASR Patient",
        "customer_phone": "",
        "pickup_address": parsed.get("pickup_address") or "",
        "dropoff_address": parsed.get("dropoff_address") or "",
        "stops": [],
        "service_type": "medical",
        "estimated_fare": 0.0,
        "actual_fare": 0.0,
        "status": "needs_review" if parsed.get("needs_review") else "scheduled",
        "source": "oasr",
        "oasr_source": True,
        "needs_review": parsed.get("needs_review", False),
        "scheduled_for": scheduled_for,
        "notes": parsed.get("notes"),
        "created_at": now,
        "updated_at": now,
        "assigned_driver_id": None,
        "payment_method": "cash",
        "dispatch_attempts": 0,
        "payment_intent_id": None,
    }
    bookings_db[booking_id] = booking
    logger.info(f"[OASR] Created booking {booking_id} confidence={parsed['confidence']} needs_review={parsed['needs_review']}")
    return {"booking_id": booking_id, "parsed": parsed, "needs_review": parsed.get("needs_review")}


@app.post("/api/bookings/{booking_id}/send-receipt", dependencies=[Depends(require_admin)])
async def send_receipt_endpoint(booking_id: str):
    db = get_db()
    booking = None
    if db:
        r = db.table("bookings").select("*").eq("id", booking_id).execute()
        if r.data: booking = r.data[0]
    else:
        for b in demo_bookings:
            if b["id"] == booking_id:
                booking = b
    if not booking:
        raise HTTPException(404, "Booking not found")
    try:
        result = send_receipt_email(booking)
        return {"success": True, "email_log": result}
    except Exception as e:
        raise HTTPException(500, f"Receipt email failed: {e}")


@app.post("/api/admin/force-complete/{booking_id}", dependencies=[Depends(require_admin)])
async def force_complete_booking(booking_id: str):
    db = get_db()
    booking = None
    if db:
        r = db.table("bookings").select("*").eq("id", booking_id).execute()
        if r.data: booking = r.data[0]
        db.table("bookings").update({"status": "completed"}).eq("id", booking_id).execute()
        if booking and booking.get("assigned_driver_id"):
            db.table("drivers").update({"status": "available"}).eq("id", booking["assigned_driver_id"]).execute()
    else:
        for b in demo_bookings:
            if b["id"] == booking_id:
                booking = b
                b["status"] = "completed"
        if booking and booking.get("assigned_driver_id"):
            for d in demo_drivers:
                if d["id"] == booking["assigned_driver_id"]:
                    d["status"] = "available"
    if not booking:
        raise HTTPException(404, "Booking not found")
    await manager.broadcast("admin", {
        "type": "ride_completed",
        "booking_id": booking_id,
        "fare": booking.get("estimated_fare", 0)
    })
    try:
        send_receipt_email(booking)
    except Exception:
        pass
    try:
        sms_ride_completed(
            booking.get("customer_phone", ""), booking.get("customer_name", ""),
            float(booking.get("estimated_fare", 0)), booking_id
        )
    except Exception:
        pass
    return {"success": True}


@app.post("/api/admin/redispatch/{booking_id}", dependencies=[Depends(require_admin)])
async def redispatch_booking(booking_id: str):
    db = get_db()
    booking = None
    if db:
        r = db.table("bookings").select("*").eq("id", booking_id).execute()
        if r.data: booking = r.data[0]
        db.table("bookings").update({"status": "pending", "dispatch_attempts": 0}).eq("id", booking_id).execute()
    else:
        for b in demo_bookings:
            if b["id"] == booking_id:
                booking = b
                b["status"] = "pending"
                b["dispatch_attempts"] = 0
    if not booking:
        raise HTTPException(404, "Booking not found")
    asyncio.create_task(dispatch_booking(booking))
    return {"success": True}


@app.post("/api/oasr/parse")
async def oasr_parse(request: Request):
    """Parse raw OASR email text and create a booking."""
    data = await request.json()
    raw_text = data.get("raw_email_text", "")
    if not raw_text:
        raise HTTPException(400, "raw_email_text is required")

    parsed = parse_oasr_email(raw_text)

    scheduled_for = None
    if parsed.get("ride_date") and parsed.get("ride_time"):
        try:
            scheduled_for = f"{parsed['ride_date']}T{parsed['ride_time']}:00+00:00"
        except Exception:
            pass

    confidence = parsed.get("confidence", 0)
    needs_review = parsed.get("needs_review", True) or confidence < 3

    booking_id = str(uuid.uuid4())[:8].upper()
    now = datetime.now(timezone.utc).isoformat()
    booking = {
        "id": booking_id,
        "customer_name": parsed.get("patient_name") or "OASR Patient",
        "customer_phone": parsed.get("phone") or "",
        "pickup_address": parsed.get("pickup_address") or "",
        "dropoff_address": parsed.get("dropoff_address") or "",
        "estimated_fare": 0.0,
        "status": "needs_review" if needs_review else "pending_assignment",
        "source": "oasr",
        "needs_review": needs_review,
        "scheduled_for": scheduled_for,
        "notes": parsed.get("notes"),
        "dispatch_attempts": 0,
        "assigned_driver_id": None,
        "created_at": now,
        "updated_at": now,
    }
    bookings_db[booking_id] = booking
    demo_bookings.append(booking)
    await manager.broadcast("admin", {"type": "new_oasr_booking", "booking": booking})
    return {"booking_id": booking_id, "parsed": parsed, "needs_review": needs_review, "booking": booking}


@app.get("/api/admin/oasr")
async def admin_oasr(_=Depends(require_admin)):
    oasr_bookings = [b for b in bookings_db.values() if b.get("source") == "oasr"]
    # Also include from demo_bookings that may not be in bookings_db
    demo_oasr_ids = {b["id"] for b in oasr_bookings}
    for b in demo_bookings:
        if b.get("source") == "oasr" and b["id"] not in demo_oasr_ids:
            oasr_bookings.append(b)
    oasr_bookings.sort(key=lambda b: b.get("created_at", ""), reverse=True)
    return oasr_bookings


# ============================================================
# DRIVER CRUD (admin)
# ============================================================

@app.post("/api/drivers")
async def create_driver_admin(body: dict = Body(...), _=Depends(require_admin)):
    driver_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    driver = {
        "id": driver_id,
        "name": body["name"],
        "phone": body["phone"],
        "pin": body["pin"],
        "vehicle": body.get("vehicle", ""),
        "plate": body.get("plate", ""),
        "status": "offline",
        "latitude": 43.0773,
        "longitude": -79.9408,
        "last_location_update": None,
        "inactive": False,
        "push_subscriptions": [],
        "ratings": [],
        "created_at": now,
        "updated_at": now,
    }
    drivers_db[driver_id] = driver
    logger.info(f"[Admin] Created driver {driver_id}: {body['name']}")
    return driver


@app.put("/api/drivers/{driver_id}")
async def update_driver_admin(driver_id: str, body: dict = Body(...), _=Depends(require_admin)):
    driver = drivers_db.get(driver_id)
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    for field in ["name", "phone", "pin", "vehicle", "plate"]:
        if field in body:
            driver[field] = body[field]
    driver["updated_at"] = datetime.now(timezone.utc).isoformat()
    return driver


@app.patch("/api/drivers/{driver_id}/deactivate")
async def deactivate_driver(driver_id: str, _=Depends(require_admin)):
    driver = drivers_db.get(driver_id)
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    driver["inactive"] = True
    driver["status"] = "offline"
    driver["updated_at"] = datetime.now(timezone.utc).isoformat()
    logger.info(f"[Admin] Deactivated driver {driver_id}")
    return {"ok": True}


# ============================================================
# ADMIN — DRIVER LOCATIONS MAP
# ============================================================

@app.get("/api/admin/driver-locations")
async def admin_driver_locations(_=Depends(require_admin)):
    result = []
    for d in drivers_db.values():
        if d.get("inactive"):
            continue
        active_booking = None
        for b in bookings_db.values():
            if b.get("assigned_driver_id") == d["id"] and b.get("status") in ("accepted", "in_progress"):
                all_stops = [b["pickup_address"]] + list(b.get("stops", [])) + [b["dropoff_address"]]
                active_booking = {
                    "id": b["id"],
                    "customer_name": b.get("customer_name", ""),
                    "pickup_address": b.get("pickup_address", ""),
                    "dropoff_address": b.get("dropoff_address", ""),
                    "stops": list(b.get("stops", [])),
                    "current_leg": b.get("current_leg", 0),
                    "total_legs": max(1, len(all_stops) - 1),
                    "estimated_fare": b.get("estimated_fare", 0),
                    "waypoints": b.get("waypoints", []),
                }
                break
        result.append({
            "id": d["id"],
            "name": d.get("name", ""),
            "phone": d.get("phone", ""),
            "vehicle": d.get("vehicle", ""),
            "plate": d.get("plate", ""),
            "status": d.get("status", "offline"),
            "lat": d.get("latitude"),
            "lng": d.get("longitude"),
            "last_update": d.get("last_location_update"),
            "active_booking": active_booking,
        })
    return result


# ============================================================
# ADMIN — SETTINGS
# ============================================================

@app.get("/api/admin/settings")
async def admin_get_settings(_=Depends(require_admin)):
    try:
        from config import load_settings
    except ImportError:
        from backend.config import load_settings
    return load_settings()


@app.post("/api/admin/settings")
async def admin_save_settings(body: dict = Body(...), _=Depends(require_admin)):
    try:
        from config import save_settings
    except ImportError:
        from backend.config import save_settings
    save_settings(body)
    return {"ok": True}


# ============================================================
# SOS
# ============================================================

# In-memory SOS log (also broadcast to admin WebSocket)
sos_log: list[dict] = []

@app.post("/api/sos")
async def driver_sos(request: Request):
    """Driver SOS alert — broadcasts to admin with GPS coords."""
    data = await request.json()
    driver_id = data.get("driver_id")
    driver_name = data.get("driver_name", "Unknown")
    lat = data.get("lat")
    lng = data.get("lng")
    booking_id = data.get("booking_id")
    now = datetime.now(timezone.utc).isoformat()

    entry = {
        "id": str(uuid.uuid4()),
        "driver_id": driver_id,
        "driver_name": driver_name,
        "booking_id": booking_id,
        "lat": lat,
        "lng": lng,
        "resolved": False,
        "created_at": now,
    }
    sos_log.append(entry)
    logger.warning(f"[SOS] Driver {driver_name} ({driver_id}) at {lat},{lng} booking={booking_id}")

    await manager.broadcast("admin", {
        "type": "sos_alert",
        "payload": entry,
        "timestamp": now,
        "message_id": entry["id"]
    })
    return {"ok": True, "sos_id": entry["id"]}


@app.get("/api/admin/sos", dependencies=[Depends(require_admin)])
async def get_sos_log():
    return {"sos_events": sos_log}


@app.patch("/api/admin/sos/{sos_id}/resolve", dependencies=[Depends(require_admin)])
async def resolve_sos(sos_id: str):
    for entry in sos_log:
        if entry["id"] == sos_id:
            entry["resolved"] = True
            entry["resolved_at"] = datetime.now(timezone.utc).isoformat()
            return {"ok": True}
    raise HTTPException(404, "SOS event not found")


# ============================================================
# HEALTH CHECK
# ============================================================

_start_time = datetime.now(timezone.utc)

@app.get("/health")
async def health():
    db = get_db()
    db_status = "demo"
    if db:
        try:
            db.table("bookings").select("id").limit(1).execute()
            db_status = "ok"
        except Exception:
            db_status = "error"

    stripe_status = "ok" if STRIPE_SECRET_KEY else "demo"
    twilio_status = "ok" if (
        __import__('config').TWILIO_ACCOUNT_SID and
        __import__('config').TWILIO_AUTH_TOKEN
    ) else "demo"

    uptime_seconds = int((datetime.now(timezone.utc) - _start_time).total_seconds())
    active_bookings = sum(
        1 for b in demo_bookings
        if b.get("status") in ("pending", "dispatched", "accepted", "in_progress")
    )
    active_drivers = sum(1 for d in demo_drivers if d.get("status") == "available")

    return {
        "status": "ok",
        "version": "2.0.0",
        "demo_mode": not bool(SUPABASE_URL),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": uptime_seconds,
        "services": {
            "database": db_status,
            "stripe": stripe_status,
            "twilio": twilio_status,
        },
        "active_drivers": active_drivers,
        "active_bookings": active_bookings,
    }


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
