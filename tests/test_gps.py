import pytest
import json
from starlette.testclient import TestClient
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
from main import app, drivers_db

def test_location_update_via_websocket():
    driver_ids = list(drivers_db.keys())
    assert driver_ids, "drivers_db must have at least one driver"
    driver_id = driver_ids[0]

    client = TestClient(app)
    with client.websocket_connect(f"/ws/driver/{driver_id}") as ws:
        ws.send_json({
            "type": "location_update",
            "lat": 43.2557,
            "lng": -79.8711,
            "accuracy": 10.0
        })
        import time; time.sleep(0.1)

    driver = drivers_db[driver_id]
    # Check whichever field the driver dict actually uses for coordinates
    # (might be "latitude"/"longitude" or "lat"/"lng")
    lat_field = "latitude" if "latitude" in driver else "lat"
    lng_field = "longitude" if "longitude" in driver else "lng"
    assert driver[lat_field] == pytest.approx(43.2557)
    assert driver[lng_field] == pytest.approx(-79.8711)
