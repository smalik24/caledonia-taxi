"""
SMS Service — Caledonia Taxi
============================
Uses real Twilio API when credentials are set in environment.
Falls back to mock logging if credentials are missing.
"""

import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_sms_log: list[dict] = []


def _send_sms(to: str, body: str) -> dict:
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    from_num = os.getenv("TWILIO_FROM_NUMBER")

    if sid and token and from_num:
        try:
            from twilio.rest import Client
            client = Client(sid, token)
            msg = client.messages.create(body=body, from_=from_num, to=to)
            entry = {
                "id": msg.sid,
                "to": to,
                "message": body,
                "sent_at": datetime.now(timezone.utc).isoformat(),
                "status": msg.status,
                "provider": "twilio"
            }
            _sms_log.append(entry)
            logger.info(f"[SMS] Sent via Twilio to {to}")
            return entry
        except Exception as e:
            logger.error(f"[SMS] Twilio error: {e}")
            # Fall through to mock

    # Mock fallback
    entry = {
        "id": f"SMS_{len(_sms_log)+1:04d}",
        "to": to,
        "message": body,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "status": "delivered_mock",
        "provider": "MOCK"
    }
    _sms_log.append(entry)
    border = "─" * 50
    print(f"\n📱  MOCK SMS\n{border}")
    print(f"  To:  {to}")
    print(f"  Msg: {body}")
    print(f"{border}\n")
    logger.info(f"[MOCK SMS] To={to} | {body[:80]}…")
    return entry


def sms_booking_confirmed(customer_phone, customer_name, booking_id, fare, base_url="https://caledonia-taxi-production.up.railway.app"):
    short_id = booking_id[:8].upper()
    return _send_sms(customer_phone,
        f"Hi {customer_name}! Your Caledonia Taxi is booked! Ref: #{short_id}. Fare: ~${fare:.2f}. "
        f"We'll text when your driver is on the way.")


def sms_driver_assigned(customer_phone, driver_name, vehicle, eta_mins, booking_id="", base_url="https://caledonia-taxi-production.up.railway.app"):
    return _send_sms(customer_phone,
        f"Your driver {driver_name} ({vehicle}) is on the way! ETA: {eta_mins} min. "
        f"Track: caledonia.taxi/track/{booking_id}")


def sms_driver_arrived(customer_phone, driver_name, vehicle=""):
    return _send_sms(customer_phone,
        f"Your driver {driver_name} has arrived. Please come out when ready.")


def sms_ride_started(customer_phone, dropoff_address=""):
    return _send_sms(customer_phone,
        f"Your ride has started. Have a safe trip! — Caledonia Taxi")


def sms_ride_completed(customer_phone, customer_name, fare, booking_id):
    short_id = booking_id[:8].upper()
    return _send_sms(customer_phone,
        f"Thanks {customer_name}! Your trip is complete. Fare: ${fare:.2f}. "
        f"Receipt: caledonia.taxi/receipt/{booking_id}")


def sms_dispatch_failed(customer_phone, customer_name):
    return _send_sms(customer_phone,
        f"Hi {customer_name}, sorry — no drivers available right now. "
        f"Please call (289) 555-1001 or try again in a few minutes.")


def sms_booking_cancelled(customer_phone, customer_name, booking_id):
    short_id = booking_id[:8].upper()
    return _send_sms(customer_phone,
        f"Hi {customer_name}, your booking #{short_id} has been cancelled. "
        f"Call us to rebook: (289) 555-1001")


def sms_voice_ai_booking(customer_phone, pickup, dropoff, fare):
    return _send_sms(customer_phone,
        f"Caledonia Taxi: Your phone booking is confirmed! "
        f"Pickup: {str(pickup)[:30]}. Drop-off: {str(dropoff)[:30]}. "
        f"Est. fare: ${fare:.2f} CAD. Booked via phone. -Caledonia Taxi")


def get_sms_log() -> list[dict]:
    return list(reversed(_sms_log))


def clear_sms_log() -> None:
    _sms_log.clear()
