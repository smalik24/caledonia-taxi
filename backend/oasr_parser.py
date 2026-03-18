"""
OASR Email Parser — Caledonia Taxi
Extracts booking fields from Ontario Association of Scheduled Rides emails.
Low confidence (< 3 fields extracted) → needs_review = True.
"""
import re
from datetime import datetime
from typing import Optional


HOSPITAL_KEYWORDS = [
    "hospital", "clinic", "medical", "health centre", "health center",
    "doctors", "dr.", "dialysis", "cancer care", "cancer centre",
    "mcmaster", "henderson", "juravinski", "st. joseph", "st joseph",
    "general hospital", "regional", "centre for", "center for",
    "health sciences", "children's", "childrens", "women's",
]


def parse_oasr_email(raw_text: str) -> dict:
    """
    Parse raw OASR email text into booking fields.

    Returns dict with:
      patient_name: str | None
      pickup_address: str | None
      dropoff_address: str | None
      ride_date: str | None   — ISO date "YYYY-MM-DD"
      ride_time: str | None   — "HH:MM" (24hr)
      notes: str | None
      confidence: int         — 0–5, how many key fields extracted
      needs_review: bool      — True if confidence < 3
      raw: str                — original input
    """
    text = raw_text.strip()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    result: dict = {
        "patient_name": None,
        "pickup_address": None,
        "dropoff_address": None,
        "ride_date": None,
        "ride_time": None,
        "notes": None,
        "raw": text,
    }

    # ── Date extraction ─────────────────────────────────────────────
    date_patterns = [
        r'\b([A-Za-z]+ \d{1,2},?\s*\d{4})\b',   # March 19, 2026
        r'\b(\d{4}-\d{2}-\d{2})\b',               # 2026-03-19
        r'\b(\d{1,2}/\d{1,2}/\d{2,4})\b',         # 19/03/26 or 3/19/2026
        r'\b(\d{1,2}-\d{1,2}-\d{2,4})\b',         # 19-03-26
    ]
    for pat in date_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            normalised = _normalise_date(m.group(1))
            if normalised:
                result["ride_date"] = normalised
                break

    # ── Time extraction ──────────────────────────────────────────────
    time_m = re.search(r'\b(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?)\b', text)
    if time_m:
        result["ride_time"] = _normalise_time(time_m.group(1))

    # ── Patient name ─────────────────────────────────────────────────
    name_patterns = [
        r'(?:patient|client|name|passenger)[:\s]+([A-Z][a-z]+(?: [A-Z][a-z.]+)+)',
        r'(?:for|transporting)[:\s]+([A-Z][a-z]+(?: [A-Z][a-z.]+)+)',
    ]
    for pat in name_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            result["patient_name"] = m.group(1).strip()
            break

    # ── Pickup address ───────────────────────────────────────────────
    pickup_m = re.search(
        r'(?:pickup|pick[ -]?up|from|origin|pick up at)[:\s]+(.+?)(?:\n|drop|destination|to[:\s]|$)',
        text, re.IGNORECASE | re.DOTALL
    )
    if pickup_m:
        addr = pickup_m.group(1).strip().split('\n')[0].strip().rstrip(',;')
        if len(addr) > 5:
            result["pickup_address"] = addr

    # ── Dropoff address ──────────────────────────────────────────────
    dropoff_m = re.search(
        r'(?:dropoff|drop[ -]?off|destination|to|deliver to)[:\s]+(.+?)(?:\n|notes?|special|$)',
        text, re.IGNORECASE | re.DOTALL
    )
    if dropoff_m:
        addr = dropoff_m.group(1).strip().split('\n')[0].strip().rstrip(',;')
        if len(addr) > 5:
            result["dropoff_address"] = addr

    # ── Hospital name fallback for dropoff ───────────────────────────
    if not result["dropoff_address"]:
        for line in lines:
            if any(kw in line.lower() for kw in HOSPITAL_KEYWORDS):
                result["dropoff_address"] = line
                break

    # ── Notes ────────────────────────────────────────────────────────
    notes_m = re.search(
        r'(?:notes?|special instructions?|comments?|requirements?)[:\s]+(.+)',
        text, re.IGNORECASE | re.DOTALL
    )
    if notes_m:
        result["notes"] = notes_m.group(1).strip()[:500]

    # ── Confidence score ─────────────────────────────────────────────
    key_fields = ["patient_name", "pickup_address", "dropoff_address", "ride_date", "ride_time"]
    result["confidence"] = sum(1 for f in key_fields if result[f])
    result["needs_review"] = result["confidence"] < 3

    return result


def _normalise_date(raw: str) -> Optional[str]:
    """Return ISO date string YYYY-MM-DD or None."""
    raw = raw.replace(",", "").strip()
    formats = [
        "%B %d %Y", "%b %d %Y",     # March 19 2026, Mar 19 2026
        "%Y-%m-%d",                   # 2026-03-19
        "%d/%m/%Y", "%m/%d/%Y",      # 19/03/2026 or 03/19/2026
        "%d/%m/%y",  "%m/%d/%y",     # 19/03/26
        "%d-%m-%Y",  "%m-%d-%Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _normalise_time(raw: str) -> Optional[str]:
    """Return 24-hour time string HH:MM or None."""
    raw = raw.strip().upper().replace(" ", "")
    for fmt in ["%I:%M%p", "%H:%M"]:
        try:
            return datetime.strptime(raw, fmt).strftime("%H:%M")
        except ValueError:
            continue
    return None


# ── Quick self-test (run: python3 backend/oasr_parser.py) ────────────
if __name__ == "__main__":
    sample = """
    OASR Booking Confirmation

    Patient: John Smith
    Pickup: 123 Argyle St North, Caledonia ON N3W 1B9
    Destination: McMaster University Medical Centre, 1280 Main St W, Hamilton ON
    Date: March 25, 2026
    Time: 9:30 AM
    Notes: Wheelchair accessible vehicle required. Please arrive 10 minutes early.
    """
    r = parse_oasr_email(sample)
    print(f"Patient:  {r['patient_name']}")
    print(f"Pickup:   {r['pickup_address']}")
    print(f"Dropoff:  {r['dropoff_address']}")
    print(f"Date:     {r['ride_date']}")
    print(f"Time:     {r['ride_time']}")
    print(f"Notes:    {r['notes']}")
    print(f"Confidence: {r['confidence']}/5  needs_review={r['needs_review']}")
