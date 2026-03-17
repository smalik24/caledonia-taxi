"""
Caledonia Taxi — Backend API (FastAPI)
======================================
Professional dispatch system for Hamilton, Ontario.
Includes: bookings, dispatch, SMS, PDF invoicing, heatmap, Voice AI hooks.
"""

import os
import json
import asyncio
import hashlib
from datetime import datetime, timezone
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request, Cookie, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from config import (
    SUPABASE_URL, SUPABASE_KEY,
    DISPATCH_TIMEOUT_SECONDS, MAX_DISPATCH_ATTEMPTS,
    ADMIN_PASSWORD, APP_SECRET_KEY, COOKIE_SECURE, ALLOWED_ORIGINS
)
from auth_service import create_session_token, verify_session_token, safe_compare, SESSION_DURATION_SECONDS
from models import (
    BookingRequest, FareEstimateRequest, DriverLoginRequest,
    DriverLocationUpdate, DriverStatusUpdate, RideActionRequest,
    AdminAssignRequest, FareEstimate, VoiceAIBookingRequest
)
from services import (
    geocode_address, get_route_distance, calculate_fare, find_nearest_driver,
    haversine_distance
)
from sms_service import (
    sms_booking_confirmed, sms_driver_assigned, sms_driver_arrived,
    sms_ride_started, sms_ride_completed, sms_dispatch_failed,
    sms_booking_cancelled, sms_voice_ai_booking, get_sms_log
)
from invoice_service import send_receipt_email, generate_invoice_pdf, get_email_log


# ============================================================
# APP SETUP
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚕  Caledonia Taxi API starting — Hamilton, ON")
    yield
    print("🚕  Caledonia Taxi API stopped.")


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
    data = await request.json()
    password = data.get("password", "")
    if not safe_compare(password, ADMIN_PASSWORD):
        raise HTTPException(status_code=401, detail="Invalid password")
    token = create_session_token(APP_SECRET_KEY)
    response = JSONResponse({"ok": True})
    response.set_cookie(
        "admin_session", token,
        httponly=True, samesite="lax",
        max_age=SESSION_DURATION_SECONDS,
        secure=COOKIE_SECURE
    )
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

@app.post("/api/estimate-fare", response_model=FareEstimate)
async def estimate_fare(req: FareEstimateRequest):
    pickup  = await geocode_address(req.pickup_address)
    dropoff = await geocode_address(req.dropoff_address)
    if not pickup or not dropoff:
        raise HTTPException(400, "Could not geocode one or both addresses")
    distance = await get_route_distance(
        pickup["lat"], pickup["lng"], dropoff["lat"], dropoff["lng"]
    )
    return FareEstimate(
        distance_km=distance,
        estimated_fare=calculate_fare(distance),
        pickup_coords=pickup,
        dropoff_coords=dropoff
    )


# ============================================================
# BOOKINGS
# ============================================================

@app.post("/api/bookings")
async def create_booking(req: BookingRequest):
    global _booking_counter
    pickup  = await geocode_address(req.pickup_address)
    dropoff = await geocode_address(req.dropoff_address)
    if not pickup or not dropoff:
        raise HTTPException(400, "Could not geocode addresses")

    distance = await get_route_distance(
        pickup["lat"], pickup["lng"], dropoff["lat"], dropoff["lng"]
    )
    fare = calculate_fare(distance)
    db   = get_db()

    if db:
        result = db.table("bookings").insert({
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
            "status":                  "pending",
            "source":                  req.source.value
        }).execute()
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
            "status":                  "pending",
            "assigned_driver_id":      None,
            "source":                  req.source.value,
            "dispatch_attempts":       0,
            "created_at":              datetime.now(timezone.utc).isoformat(),
            "updated_at":              datetime.now(timezone.utc).isoformat()
        }
        demo_bookings.append(booking)

    await manager.broadcast("admin", {"type": "new_booking", "booking": booking})

    # SMS: booking confirmed
    try:
        sms_booking_confirmed(
            req.customer_phone, req.customer_name,
            booking["id"], fare
        )
    except Exception as e:
        print(f"[SMS] booking_confirmed error: {e}")

    asyncio.create_task(dispatch_booking(booking))
    return {"success": True, "booking": booking}


async def dispatch_booking(booking: dict):
    """Auto-dispatch to nearest driver. Escalate on timeout/decline."""
    db       = get_db()
    excluded: list[str] = []
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

        await manager.send_to_driver(did, {
            "type": "new_ride",
            "booking": booking,
            "timeout_seconds": DISPATCH_TIMEOUT_SECONDS,
            "eta_mins": eta_mins
        })
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
    else:
        if db:
            db.table("dispatch_log").update({
                "status": "declined", "responded_at": now
            }).eq("booking_id", booking_id).eq("driver_id", driver_id).execute()
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
    fare = calculate_fare(distance)
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
    fare = calculate_fare(distance)
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
    fare = calculate_fare(dist)
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
        fare = calculate_fare(dist)
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
        fare = calculate_fare(dist)
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
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
