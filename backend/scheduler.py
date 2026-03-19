"""APScheduler setup for advance booking dispatch."""
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler(timezone="UTC")
MAX_DISPATCH_ATTEMPTS = 3


async def dispatch_scheduled_now(bookings_db: dict, dispatch_fn, sms_fn=None) -> None:
    """
    Find scheduled bookings within 10 minutes and dispatch them.
    Sets status to 'dispatching' atomically before calling dispatch_fn
    to prevent double-dispatch across poll cycles.
    After MAX_DISPATCH_ATTEMPTS failures, marks booking as dispatch_failed.
    """
    now = datetime.now(timezone.utc)
    window = now + timedelta(minutes=10)

    for booking in list(bookings_db.values()):
        if booking.get("status") != "scheduled":
            continue
        sf_raw = booking.get("scheduled_for")
        if not sf_raw:
            continue
        try:
            sf = datetime.fromisoformat(sf_raw)
            if sf.tzinfo is None:
                sf = sf.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
        if sf <= window:
            attempts = booking.get("dispatch_attempts", 0)
            if attempts >= MAX_DISPATCH_ATTEMPTS:
                booking["status"] = "dispatch_failed"
                if sms_fn and booking.get("customer_phone"):
                    try:
                        await sms_fn(
                            booking["customer_phone"],
                            f"Sorry, we could not find a driver for your scheduled ride. "
                            f"Please call us or book again. Booking: {booking['id'][:8].upper()}"
                        )
                    except Exception:
                        pass
                continue
            # Atomically claim — prevents double-dispatch on next poll cycle
            booking["status"] = "dispatching"
            booking["dispatch_attempts"] = attempts + 1
            try:
                await dispatch_fn(booking)
            except Exception:
                # Revert to scheduled so next poll retries
                booking["status"] = "scheduled"


def setup_scheduler(bookings_db: dict, dispatch_fn, sms_fn=None) -> AsyncIOScheduler:
    """Configure and return the scheduler. Call scheduler.start() in lifespan."""

    @scheduler.scheduled_job("interval", seconds=60, id="dispatch_scheduled")
    async def _job():
        await dispatch_scheduled_now(bookings_db, dispatch_fn, sms_fn)

    return scheduler
