"""
Core services: geocoding, fare calculation, dispatch logic.
Uses OpenRouteService (free) for geocoding + routing.
Falls back to Haversine if ORS key not set.
"""

import math
import hashlib
import httpx
from typing import Optional, List
from config import (
    ORS_API_KEY, BASE_FARE, PER_KM_RATE, MINIMUM_FARE,
    DISPATCH_TIMEOUT_SECONDS, MAX_DISPATCH_ATTEMPTS
)

# Known Hamilton landmarks — used in demo mode (no ORS key needed)
HAMILTON_LANDMARKS = {
    "hamilton go": {"lat": 43.2535, "lng": -79.8711},
    "go station": {"lat": 43.2535, "lng": -79.8711},
    "mcmaster": {"lat": 43.2609, "lng": -79.9192},
    "jackson square": {"lat": 43.2583, "lng": -79.8686},
    "limeridge mall": {"lat": 43.2251, "lng": -79.8487},
    "limeridge": {"lat": 43.2251, "lng": -79.8487},
    "mohawk college": {"lat": 43.2381, "lng": -79.8889},
    "mohawk": {"lat": 43.2381, "lng": -79.8889},
    "hamilton airport": {"lat": 43.1735, "lng": -79.9350},
    "airport": {"lat": 43.1735, "lng": -79.9350},
    "dundurn": {"lat": 43.2694, "lng": -79.8844},
    "bayfront": {"lat": 43.2712, "lng": -79.8728},
    "waterdown": {"lat": 43.3350, "lng": -79.8940},
    "stoney creek": {"lat": 43.2176, "lng": -79.7633},
    "ancaster": {"lat": 43.2287, "lng": -79.9846},
    "dundas": {"lat": 43.2667, "lng": -79.9544},
    "burlington": {"lat": 43.3255, "lng": -79.7990},
    "caledonia": {"lat": 43.0715, "lng": -79.9531},
    "king st": {"lat": 43.2560, "lng": -79.8690},
    "king street": {"lat": 43.2560, "lng": -79.8690},
    "main st": {"lat": 43.2450, "lng": -79.8650},
    "main street": {"lat": 43.2450, "lng": -79.8650},
    "james st": {"lat": 43.2580, "lng": -79.8680},
    "james street": {"lat": 43.2580, "lng": -79.8680},
    "upper james": {"lat": 43.2200, "lng": -79.8700},
    "upper wentworth": {"lat": 43.2350, "lng": -79.8450},
    "stone church": {"lat": 43.2100, "lng": -79.8600},
    "rymal": {"lat": 43.2000, "lng": -79.8600},
    "mountain": {"lat": 43.2200, "lng": -79.8600},
    "westdale": {"lat": 43.2640, "lng": -79.9080},
    "westend": {"lat": 43.2550, "lng": -79.9000},
    "downtown": {"lat": 43.2568, "lng": -79.8690},
    "hamilton city hall": {"lat": 43.2568, "lng": -79.8690},
}


# ============================================
# GEOCODING
# ============================================

async def geocode_address(address: str) -> Optional[dict]:
    """Convert address string to lat/lng. Uses ORS if key set, else landmark/hash fallback."""
    if not ORS_API_KEY:
        return _demo_geocode(address)

    url = "https://api.openrouteservice.org/geocode/search"
    params = {
        "api_key": ORS_API_KEY,
        "text": address,
        "boundary.country": "CA",
        "boundary.rect.min_lat": 43.0,
        "boundary.rect.max_lat": 43.5,
        "boundary.rect.min_lon": -80.2,
        "boundary.rect.max_lon": -79.5,
        "size": 1
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            if data.get("features"):
                coords = data["features"][0]["geometry"]["coordinates"]
                return {"lat": coords[1], "lng": coords[0]}
    except Exception as e:
        print(f"[geocode] ORS error: {e} — using fallback")

    return _demo_geocode(address)


def _demo_geocode(address: str) -> dict:
    """Demo geocoder: checks known Hamilton landmarks, then generates consistent coords from address hash."""
    addr_lower = address.lower()
    for key, coords in HAMILTON_LANDMARKS.items():
        if key in addr_lower:
            return coords
    # Deterministic coords within Hamilton based on address hash
    h = int(hashlib.md5(address.encode()).hexdigest()[:8], 16)
    lat = 43.20 + (h % 1000) / 10000.0
    lng = -79.95 + ((h >> 10) % 1000) / 10000.0
    return {"lat": round(lat, 6), "lng": round(lng, 6)}


async def geocode_route(addresses: list) -> list:
    """
    Geocode a list of addresses and compute Haversine distances between consecutive points.
    Returns list of legs suitable for calculate_fare().

    Each leg: {"from": str, "to": str, "km": float, "from_lat": float, "from_lng": float,
               "to_lat": float, "to_lng": float}
    """
    if len(addresses) < 2:
        return []

    coords = []
    for addr in addresses:
        result = await geocode_address(addr)
        coords.append({"address": addr, "lat": result["lat"], "lng": result["lng"]})

    legs = []
    for i in range(len(coords) - 1):
        a, b = coords[i], coords[i + 1]
        km = haversine_distance(a["lat"], a["lng"], b["lat"], b["lng"])
        legs.append({
            "from":     a["address"],
            "to":       b["address"],
            "km":       round(km, 2),
            "from_lat": a["lat"],
            "from_lng": a["lng"],
            "to_lat":   b["lat"],
            "to_lng":   b["lng"],
        })
    return legs


# ============================================
# ROUTING
# ============================================

async def get_route_distance(
    origin_lat: float, origin_lng: float,
    dest_lat: float, dest_lng: float
) -> float:
    """Get driving distance in km. Uses ORS if key set, else Haversine * 1.3."""
    if not ORS_API_KEY:
        return haversine_distance(origin_lat, origin_lng, dest_lat, dest_lng)

    url = "https://api.openrouteservice.org/v2/directions/driving-car"
    headers = {"Authorization": ORS_API_KEY}
    params = {
        "start": f"{origin_lng},{origin_lat}",
        "end": f"{dest_lng},{dest_lat}"
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
            if data.get("features"):
                distance_m = data["features"][0]["properties"]["segments"][0]["distance"]
                return round(distance_m / 1000, 2)
    except Exception as e:
        print(f"[routing] ORS error: {e} — using haversine")

    return haversine_distance(origin_lat, origin_lng, dest_lat, dest_lng)


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Straight-line distance in km * 1.3 road factor."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c * 1.3, 2)


# ============================================
# FARE CALCULATION
# ============================================

def calculate_fare(
    legs: list,
    service_type: str = "standard",
    surge_multiplier: float = 1.0,
    promo_discount: float = 0.0,
) -> dict:
    """
    Multi-leg fare calculation. AUTHORITATIVE — used for Stripe payment amounts.
    Must stay in sync with frontend/static/js/fare-engine.js.

    Args:
        legs: list of {"from": str, "to": str, "km": float}
        service_type: "standard" | "medical" | "long_distance"
        surge_multiplier: 1.0 = no surge. surge_addition = subtotal * (mult - 1.0)
        promo_discount: 0.0–1.0 fraction (e.g. 0.10 for 10% off)

    Returns dict with keys:
        legs: [{"label": str, "km": float, "subtotal": float}]
        base_fare, stop_surcharge, subtotal,
        promo_discount (negative), surge_addition, total,
        estimated_fare (alias for total), is_flat_rate
    """
    try:
        from backend.config import get_pricing, get_flat_rates
    except ImportError:
        from config import get_pricing, get_flat_rates

    pricing = get_pricing()
    flat_rates = get_flat_rates()

    base_fare  = pricing["base_fare"]
    per_km     = pricing["per_km_rate"]
    min_fare   = pricing["minimum_fare"]
    stop_fee   = pricing["stop_surcharge"]

    if not legs:
        return {
            "legs": [], "base_fare": base_fare, "stop_surcharge": 0.0,
            "subtotal": 0.0, "promo_discount": 0.0, "surge_addition": 0.0,
            "total": min_fare, "estimated_fare": min_fare, "is_flat_rate": False,
        }

    stop_count = max(0, len(legs) - 1)  # intermediate stops only
    is_flat    = service_type == "long_distance"

    computed_legs = []
    if is_flat:
        dest = legs[-1].get("to", "")
        flat = float(flat_rates.get(dest, 0.0))
        for i, leg in enumerate(legs):
            computed_legs.append({
                "label":    f"{leg.get('from', '')} → {leg.get('to', '')}",
                "km":       float(leg.get("km", 0.0)),
                "subtotal": round(flat if i == 0 else 0.0, 2),
            })
    else:
        for i, leg in enumerate(legs):
            km = float(leg.get("km", 0.0))
            subtotal = round((base_fare if i == 0 else 0.0) + km * per_km, 2)
            computed_legs.append({
                "label":    f"{leg.get('from', '')} → {leg.get('to', '')}",
                "km":       km,
                "subtotal": subtotal,
            })

    leg_total  = round(sum(l["subtotal"] for l in computed_legs), 2)
    stop_total = round(stop_count * stop_fee, 2)
    subtotal   = round(leg_total + stop_total, 2)
    promo_amt  = round(subtotal * promo_discount, 2)
    surge_amt  = round(subtotal * (surge_multiplier - 1.0), 2)
    total      = round(max(subtotal - promo_amt + surge_amt, min_fare), 2)

    return {
        "legs":            computed_legs,
        "base_fare":       base_fare if not is_flat else 0.0,
        "stop_surcharge":  stop_total,
        "subtotal":        subtotal,
        "promo_discount":  -promo_amt,
        "surge_addition":  surge_amt,
        "total":           total,
        "estimated_fare":  total,
        "is_flat_rate":    is_flat,
    }


# ============================================
# DISPATCH
# ============================================

def find_nearest_driver(
    drivers: List[dict],
    pickup_lat: float,
    pickup_lng: float,
    exclude_driver_ids: List[str] = None
) -> Optional[dict]:
    """Return the nearest available driver, excluding already-tried ones."""
    exclude_ids = set(exclude_driver_ids or [])
    available = [
        d for d in drivers
        if d.get("status") == "available"
        and d.get("id") not in exclude_ids
        and d.get("latitude") is not None
        and d.get("longitude") is not None
    ]
    if not available:
        return None
    available.sort(key=lambda d: haversine_distance(
        pickup_lat, pickup_lng, d["latitude"], d["longitude"]
    ))
    return available[0]


# ============================================
# SURGE PRICING
# ============================================

def fare_from_distance(distance_km: float, service_type: str = "standard") -> float:
    """Compatibility helper: compute flat fare from a raw km distance (no legs)."""
    legs = [{"from": "Pickup", "to": "Dropoff", "km": distance_km}]
    return calculate_fare(legs, service_type)["total"]


def get_current_surge_multiplier(bookings_db: dict, drivers_db: dict) -> float:
    """Calculate current surge multiplier based on demand/supply."""
    try:
        from backend.config import get_surge_config
    except ImportError:
        from config import get_surge_config

    cfg = get_surge_config()
    if not cfg.get("enabled", True):
        return 1.0

    pending_count   = sum(1 for b in bookings_db.values() if b.get("status") == "pending")
    available_count = sum(1 for d in drivers_db.values()  if d.get("status") == "available")

    t2_pending  = cfg.get("tier2_pending_min", 5)
    t2_avail    = cfg.get("tier2_available_max", 1)
    t2_mult     = float(cfg.get("tier2_multiplier", 2.0))
    t1_pending  = cfg.get("tier1_pending_min", 3)
    t1_avail    = cfg.get("tier1_available_max", 2)
    t1_mult     = float(cfg.get("tier1_multiplier", 1.5))

    if pending_count >= t2_pending and available_count <= t2_avail:
        return t2_mult
    if pending_count >= t1_pending and available_count <= t1_avail:
        return t1_mult
    return 1.0
