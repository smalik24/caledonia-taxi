"""
IMAP Email Poller — Caledonia Taxi
===================================
Polls for OASR emails from IMAP inbox every 5 minutes.
Only active if IMAP_HOST is set in environment.
"""
import os
import imaplib
import email
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def fetch_oasr_emails() -> list[str]:
    """Fetch unread emails from OASR sender, mark as read, return raw texts."""
    host     = os.getenv("IMAP_HOST", "")
    port     = int(os.getenv("IMAP_PORT", "993"))
    user     = os.getenv("IMAP_USER", "")
    password = os.getenv("IMAP_PASSWORD", "")
    sender   = os.getenv("OASR_SENDER_EMAIL", "")

    if not host:
        return []

    results = []
    try:
        mail = imaplib.IMAP4_SSL(host, port)
        mail.login(user, password)
        mail.select("INBOX")
        search_criteria = f'(UNSEEN FROM "{sender}")' if sender else '(UNSEEN)'
        _, data = mail.search(None, search_criteria)
        for num in data[0].split():
            _, raw = mail.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(raw[0][1])
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                        break
            else:
                body = msg.get_payload(decode=True).decode("utf-8", errors="replace")
            if body:
                results.append(body)
            mail.store(num, "+FLAGS", "\\Seen")
        mail.logout()
        logger.info(f"[IMAP] Fetched {len(results)} OASR emails")
    except Exception as e:
        logger.error(f"[IMAP] Error fetching emails: {e}")
    return results


def setup_imap_poller(scheduler, parse_fn, bookings_db: dict, demo_bookings: list, broadcast_fn=None):
    """Add IMAP polling job to existing APScheduler if IMAP_HOST is set."""
    if not os.getenv("IMAP_HOST"):
        logger.info("[IMAP] IMAP_HOST not set — email polling disabled")
        return

    @scheduler.scheduled_job("interval", minutes=5, id="imap_poll_oasr")
    async def _poll():
        emails = fetch_oasr_emails()
        for raw_text in emails:
            try:
                parsed = parse_fn(raw_text)
                confidence = parsed.get("confidence", 0)
                needs_review = parsed.get("needs_review", True) or confidence < 3
                import uuid
                from datetime import datetime, timezone
                booking_id = str(uuid.uuid4())[:8].upper()
                now = datetime.now(timezone.utc).isoformat()
                booking = {
                    "id": booking_id,
                    "customer_name": parsed.get("patient_name") or "OASR Patient",
                    "customer_phone": "",
                    "pickup_address": parsed.get("pickup_address") or "",
                    "dropoff_address": parsed.get("dropoff_address") or "",
                    "estimated_fare": 0.0,
                    "status": "needs_review" if needs_review else "pending_assignment",
                    "source": "oasr",
                    "needs_review": needs_review,
                    "dispatch_attempts": 0,
                    "assigned_driver_id": None,
                    "created_at": now,
                    "updated_at": now,
                }
                bookings_db[booking_id] = booking
                demo_bookings.append(booking)
                logger.info(f"[IMAP] Created OASR booking {booking_id}")
                if broadcast_fn:
                    import asyncio
                    asyncio.create_task(broadcast_fn("admin", {"type": "new_oasr_booking", "booking": booking}))
            except Exception as e:
                logger.error(f"[IMAP] Failed to process email: {e}")
