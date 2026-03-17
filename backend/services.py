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

def calculate_fare(distance_km: float) -> float:
    """Base fare + per-km rate, with minimum fare floor."""
    fare = BASE_FARE + (distance_km * PER_KM_RATE)
    return round(max(fare, MINIMUM_FARE), 2)


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
