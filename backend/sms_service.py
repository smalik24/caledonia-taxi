"""
Mock SMS Service — Caledonia Taxi
=================================
Simulates Twilio SMS sending with professional message templates.
All messages are logged to console and an in-memory store.

To go live: see MORNING_SETUP.md → "Enable Real SMS (Twilio)"
Replace `_send_mock()` body with:
    from twilio.rest import Client
    client = Client(account_sid, auth_token)
    client.messages.create(body=message, from_=twilio_number, to=to_phone)
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# In-memory SMS log (survives only while server is running)
_sms_log: list[dict] = []


# ============================================================
# CORE MOCK SENDER
# ============================================================

def _send_mock(to_phone: str, message: str) -> dict:
    """
    Core mock SMS dispatcher.
    Logs the message and stores it in memory.
    Replace this function body with real Twilio calls in production.
    """
    entry = {
        "id": f"SMS_{len(_sms_log)+1:04d}",
        "to": to_phone,
        "message": message,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "status": "delivered_mock",
        "provider": "MOCK"
    }
    _sms_log.append(entry)

    # Console output — easy to see during development
    border = "─" * 50
    print(f"\n📱  MOCK SMS\n{border}")
    print(f"  To:  {to_phone}")
    print(f"  Msg: {message}")
    print(f"{border}\n")

    logger.info(f"[MOCK SMS] To={to_phone} | {message[:80]}…")
    return entry


# ============================================================
# PROFESSIONAL MESSAGE TEMPLATES
# ============================================================

def sms_booking_confirmed(
    customer_phone: str,
    customer_name: str,
    booking_id: str,
    fare: float
) -> dict:
    """Step 1 — Sent immediately when booking is created."""
    short_id = booking_id[:8].upper()
    msg = (
        f"Hi {customer_name}! Your Caledonia Taxi is booked "
        f"(Ref #{short_id}). Est. fare: ${fare:.2f} CAD. "
        f"We'll text when your driver is on the way. -Caledonia Taxi"
    )
    return _send_mock(customer_phone, msg)


def sms_driver_assigned(
    customer_phone: str,
    driver_name: str,
    vehicle: str,
    eta_mins: int
) -> dict:
    """Step 2 — Sent when a driver accepts the ride."""
    msg = (
        f"Your driver {driver_name} is on the way in a {vehicle}. "
        f"ETA: ~{eta_mins} min. Track your ride at caledonia.taxi. "
        f"-Caledonia Taxi"
    )
    return _send_mock(customer_phone, msg)


def sms_driver_arrived(
    customer_phone: str,
    driver_name: str,
    vehicle: str
) -> dict:
    """Step 3 — Sent when driver marks 'Arrived at pickup'."""
    msg = (
        f"{driver_name} has arrived at your pickup in a {vehicle}. "
        f"Please come outside. -Caledonia Taxi"
    )
    return _send_mock(customer_phone, msg)


def sms_ride_started(
    customer_phone: str,
    dropoff_address: str
) -> dict:
    """Step 4 — Sent when ride begins (customer picked up)."""
    msg = (
        f"Your ride has started. Heading to {dropoff_address}. "
        f"Sit back and relax! -Caledonia Taxi"
    )
    return _send_mock(customer_phone, msg)


def sms_ride_completed(
    customer_phone: str,
    customer_name: str,
    fare: float,
    booking_id: str
) -> dict:
    """Step 5 — Sent when ride is complete. Includes receipt notice."""
    short_id = booking_id[:8].upper()
    msg = (
        f"Thanks for riding, {customer_name}! "
        f"Final fare: ${fare:.2f} CAD (Ref #{short_id}). "
        f"Your PDF receipt has been emailed. -Caledonia Taxi"
    )
    return _send_mock(customer_phone, msg)


def sms_dispatch_failed(
    customer_phone: str,
    customer_name: str
) -> dict:
    """Sent if all dispatch attempts fail."""
    msg = (
        f"Hi {customer_name}, we're sorry — no drivers are available right now. "
        f"Please call us at (289) 555-1001 or try again shortly. -Caledonia Taxi"
    )
    return _send_mock(customer_phone, msg)


def sms_booking_cancelled(
    customer_phone: str,
    customer_name: str,
    booking_id: str
) -> dict:
    """Sent when a booking is cancelled."""
    short_id = booking_id[:8].upper()
    msg = (
        f"Hi {customer_name}, your booking #{short_id} has been cancelled. "
        f"No charge applies. Call (289) 555-1001 to re-book. -Caledonia Taxi"
    )
    return _send_mock(customer_phone, msg)


def sms_voice_ai_booking(
    customer_phone: str,
    pickup: str,
    dropoff: str,
    fare: float
) -> dict:
    """Sent when a booking comes in via Voice AI."""
    msg = (
        f"Caledonia Taxi: Your phone booking is confirmed! "
        f"Pickup: {pickup[:30]}. Drop-off: {dropoff[:30]}. "
        f"Est. fare: ${fare:.2f} CAD. -Caledonia Taxi"
    )
    return _send_mock(customer_phone, msg)


# ============================================================
# ADMIN ACCESS
# ============================================================

def get_sms_log() -> list[dict]:
    """Return all logged SMS messages (newest first)."""
    return list(reversed(_sms_log))


def clear_sms_log() -> None:
    """Clear the in-memory SMS log."""
    _sms_log.clear()
