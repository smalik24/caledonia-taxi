"""
test_demo.py — Full integration tests running entirely in demo mode.
No external services (Supabase, Stripe, Twilio) required.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from main import app, demo_bookings, demo_drivers, drivers_db


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as c:
        yield c


@pytest_asyncio.fixture
async def admin_client():
    """Client with admin session cookie."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as c:
        resp = await c.post("/admin/login", json={"password": "admin1234"})
        assert resp.status_code == 200
        yield c


# ── Health Check ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "demo_mode" in data
    assert "services" in data
    assert "uptime_seconds" in data
    assert data["services"]["database"] in ("ok", "demo", "error")


# ── Admin Auth ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_login_success(client):
    resp = await client.post("/admin/login", json={"password": "admin1234"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert "admin_session" in resp.cookies


@pytest.mark.asyncio
async def test_admin_login_wrong_password(client):
    resp = await client.post("/admin/login", json={"password": "wrongpass"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_protected_without_auth(client):
    resp = await client.get("/api/admin/stats")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_stats(admin_client):
    resp = await admin_client.get("/api/admin/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_bookings" in data
    assert "drivers_available" in data


# ── Driver Auth ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_driver_login_success(client):
    resp = await client.post("/api/drivers/login", json={
        "phone": "+12895551001", "pin": "1234"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["driver"]["name"] == "Saqib"


@pytest.mark.asyncio
async def test_driver_login_wrong_pin(client):
    resp = await client.post("/api/drivers/login", json={
        "phone": "+12895551001", "pin": "9999"
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_drivers(client):
    resp = await client.get("/api/drivers")
    assert resp.status_code == 200
    assert "drivers" in resp.json()
    assert len(resp.json()["drivers"]) >= 4


# ── Booking Creation ────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_booking(client):
    resp = await client.post("/api/bookings", json={
        "customer_name": "Test Customer",
        "customer_phone": "+12895559999",
        "pickup_address": "Hamilton GO Station",
        "dropoff_address": "McMaster University",
        "payment_method": "cash"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    booking = data["booking"]
    assert booking["customer_name"] == "Test Customer"
    assert booking["status"] in ("pending", "dispatched")
    assert booking["estimated_fare"] > 0
    return booking


@pytest.mark.asyncio
async def test_booking_has_fare(client):
    resp = await client.post("/api/bookings", json={
        "customer_name": "Fare Test",
        "customer_phone": "+12895558888",
        "pickup_address": "Limeridge Mall",
        "dropoff_address": "Bayfront Park",
    })
    data = resp.json()
    assert data["booking"]["estimated_fare"] > 0
    assert data["booking"]["estimated_distance_km"] > 0


@pytest.mark.asyncio
async def test_get_booking(client):
    # Create then retrieve
    create_resp = await client.post("/api/bookings", json={
        "customer_name": "Get Test",
        "customer_phone": "+12895557777",
        "pickup_address": "Downtown Hamilton",
        "dropoff_address": "Waterdown",
    })
    booking_id = create_resp.json()["booking"]["id"]

    resp = await client.get(f"/api/bookings/{booking_id}")
    assert resp.status_code == 200
    assert resp.json()["booking"]["id"] == booking_id


@pytest.mark.asyncio
async def test_cancel_booking(client):
    create_resp = await client.post("/api/bookings", json={
        "customer_name": "Cancel Test",
        "customer_phone": "+12895556666",
        "pickup_address": "Jackson Square",
        "dropoff_address": "Mohawk College",
    })
    booking_id = create_resp.json()["booking"]["id"]

    cancel_resp = await client.patch(f"/api/bookings/{booking_id}/cancel")
    assert cancel_resp.status_code == 200

    get_resp = await client.get(f"/api/bookings/{booking_id}")
    assert get_resp.json()["booking"]["status"] == "cancelled"


# ── Fare Estimation ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_fare_estimate(client):
    resp = await client.post("/api/estimate-fare", json={
        "pickup_address": "Hamilton GO Station",
        "dropoff_address": "McMaster University"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data or "estimated_fare" in data or "base" in data


# ── Driver Dispatch → Accept Flow ───────────────────────────

@pytest.mark.asyncio
async def test_dispatch_accept_flow(client):
    # Ensure at least one driver is available
    for d in demo_drivers:
        if d["id"] == "d1":
            d["status"] = "available"

    # Create booking
    create_resp = await client.post("/api/bookings", json={
        "customer_name": "Dispatch Test",
        "customer_phone": "+12895555555",
        "pickup_address": "Hamilton GO",
        "dropoff_address": "Ancaster",
    })
    booking_id = create_resp.json()["booking"]["id"]

    # Manually accept the ride (simulating driver response)
    accept_resp = await client.post(
        f"/api/rides/{booking_id}/action/d1",
        json={"action": "accept"}
    )
    assert accept_resp.status_code == 200

    # Verify booking is accepted
    get_resp = await client.get(f"/api/bookings/{booking_id}")
    assert get_resp.json()["booking"]["status"] == "accepted"


@pytest.mark.asyncio
async def test_dispatch_decline_redispatch(client):
    for d in demo_drivers:
        if d["id"] in ("d1", "d2"):
            d["status"] = "available"

    create_resp = await client.post("/api/bookings", json={
        "customer_name": "Decline Test",
        "customer_phone": "+12895554444",
        "pickup_address": "Limeridge",
        "dropoff_address": "Dundas",
    })
    booking_id = create_resp.json()["booking"]["id"]

    # Driver 1 declines
    decline_resp = await client.post(
        f"/api/rides/{booking_id}/action/d1",
        json={"action": "decline"}
    )
    assert decline_resp.status_code == 200
    assert "declined" in decline_resp.json().get("message", "")


# ── Complete Ride Flow ──────────────────────────────────────

@pytest.mark.asyncio
async def test_full_ride_flow(client):
    for d in demo_drivers:
        if d["id"] == "d1":
            d["status"] = "available"

    # Create
    create_resp = await client.post("/api/bookings", json={
        "customer_name": "Full Flow",
        "customer_phone": "+12895553333",
        "pickup_address": "Stoney Creek",
        "dropoff_address": "Downtown Hamilton",
    })
    booking_id = create_resp.json()["booking"]["id"]

    # Accept
    await client.post(f"/api/rides/{booking_id}/action/d1", json={"action": "accept"})

    # Start ride
    start_resp = await client.post(f"/api/rides/{booking_id}/start/d1")
    assert start_resp.status_code == 200

    # Complete ride
    complete_resp = await client.post(f"/api/rides/{booking_id}/complete/d1")
    assert complete_resp.status_code == 200

    # Verify completed
    get_resp = await client.get(f"/api/bookings/{booking_id}")
    assert get_resp.json()["booking"]["status"] == "completed"


# ── Payment State ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_booking_payment_method(client):
    resp = await client.post("/api/bookings", json={
        "customer_name": "Payment Test",
        "customer_phone": "+12895552222",
        "pickup_address": "Hamilton Airport",
        "dropoff_address": "Jackson Square",
        "payment_method": "cash"
    })
    assert resp.status_code == 200
    booking = resp.json()["booking"]
    assert booking.get("payment_method") == "cash"


# ── SMS Log in Demo Mode ────────────────────────────────────

@pytest.mark.asyncio
async def test_sms_log_demo(admin_client):
    # Create a booking which triggers SMS
    await admin_client.post("/api/bookings", json={
        "customer_name": "SMS Demo",
        "customer_phone": "+12895551234",
        "pickup_address": "McMaster",
        "dropoff_address": "Mohawk College",
    })
    resp = await admin_client.get("/api/admin/sms-log")
    assert resp.status_code == 200
    assert "sms_log" in resp.json()


# ── Driver Location Update ──────────────────────────────────

@pytest.mark.asyncio
async def test_driver_location_update(client):
    resp = await client.patch("/api/drivers/d1/location", json={
        "latitude": 43.2600,
        "longitude": -79.8750
    })
    assert resp.status_code == 200
    assert resp.json()["success"] is True


# ── Surge Pricing ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_surge_endpoint(client):
    resp = await client.get("/api/surge")
    assert resp.status_code == 200
    data = resp.json()
    assert "multiplier" in data
    assert "active" in data
    assert data["multiplier"] >= 1.0


# ── Voice AI ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_voice_ai_fare_estimate(client):
    resp = await client.post("/api/voice-ai/fare-estimate", json={
        "pickup_address": "Hamilton GO",
        "dropoff_address": "Burlington"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "estimated_fare" in data
    assert "tts_message" in data


@pytest.mark.asyncio
async def test_voice_ai_booking(client):
    resp = await client.post("/api/voice-ai/booking", json={
        "customer_name": "Voice Customer",
        "customer_phone": "+12895550000",
        "pickup_address": "McMaster University",
        "dropoff_address": "Hamilton Airport",
        "agent_id": "test_agent"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "booking_id" in data


# ── PDF Receipt ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_receipt_generation(client):
    # Create and complete a booking first
    for d in demo_drivers:
        if d["id"] == "d1":
            d["status"] = "available"

    create_resp = await client.post("/api/bookings", json={
        "customer_name": "Receipt Test",
        "customer_phone": "+12895559000",
        "pickup_address": "Dundurn Castle",
        "dropoff_address": "Limeridge Mall",
    })
    booking_id = create_resp.json()["booking"]["id"]

    await client.post(f"/api/rides/{booking_id}/action/d1", json={"action": "accept"})
    await client.post(f"/api/rides/{booking_id}/start/d1")
    await client.post(f"/api/rides/{booking_id}/complete/d1")

    resp = await client.get(f"/api/bookings/{booking_id}/receipt")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"


# ── SMS Inbound Webhook ──────────────────────────────────

@pytest.mark.asyncio
async def test_sms_inbound_unknown_command(client):
    """Unknown SMS body returns TwiML help message."""
    r = await client.post("/sms/inbound", data={
        "From": "+12895550099",
        "To": "+12895551001",
        "Body": "HELLO",
        "MessageSid": "SM_test_1",
        "AccountSid": "AC_test"
    })
    assert r.status_code == 200
    assert "text/xml" in r.headers.get("content-type", "")
    assert "<Response>" in r.text
    assert "<Message>" in r.text


@pytest.mark.asyncio
async def test_sms_inbound_status_no_booking(client):
    """STATUS with no active booking returns appropriate TwiML."""
    r = await client.post("/sms/inbound", data={
        "From": "+19999999999",  # phone with no bookings
        "To": "+12895551001",
        "Body": "STATUS",
        "MessageSid": "SM_test_2",
        "AccountSid": "AC_test"
    })
    assert r.status_code == 200
    assert "<Response>" in r.text


# ── WebSocket Envelope Schema ───────────────────────────────

def test_ws_envelope_function():
    """ws_envelope creates correctly structured WebSocket messages."""
    import sys; sys.path.insert(0, "/Users/saqib/Downloads/caledonia-taxi/backend")
    from main import ws_envelope
    msg = ws_envelope("test_type", {"key": "value"})
    assert msg["type"] == "test_type"
    assert msg["payload"] == {"key": "value"}
    assert "timestamp" in msg
    assert "message_id" in msg
    assert len(msg["message_id"]) == 36  # UUID format
