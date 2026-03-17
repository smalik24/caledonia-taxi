import pytest
from datetime import datetime, timezone, timedelta


def future_time(minutes=60):
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


async def test_immediate_booking_dispatches_now(client):
    r = await client.post("/api/bookings", json={
        "customer_name": "Test User",
        "customer_phone": "+12895550001",
        "pickup_address": "Hamilton GO Station, Hamilton, ON",
        "dropoff_address": "McMaster University, Hamilton, ON",
        "source": "web"
    })
    assert r.status_code == 200
    assert r.json()["booking"]["status"] == "pending"


async def test_scheduled_booking_does_not_dispatch_immediately(client):
    r = await client.post("/api/bookings", json={
        "customer_name": "Future Rider",
        "customer_phone": "+12895550002",
        "pickup_address": "Hamilton GO Station, Hamilton, ON",
        "dropoff_address": "McMaster University, Hamilton, ON",
        "source": "web",
        "scheduled_for": future_time(minutes=120)
    })
    assert r.status_code == 200
    booking = r.json()["booking"]
    assert booking["status"] == "scheduled"
    assert booking["scheduled_for"] is not None


async def test_scheduled_booking_rejects_under_30min_lead(client):
    near_future = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
    r = await client.post("/api/bookings", json={
        "customer_name": "Hasty Rider",
        "customer_phone": "+12895550003",
        "pickup_address": "Hamilton GO Station, Hamilton, ON",
        "dropoff_address": "McMaster University, Hamilton, ON",
        "source": "web",
        "scheduled_for": near_future
    })
    assert r.status_code == 400


async def test_scheduled_booking_rejects_past_time(client):
    past_time = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    r = await client.post("/api/bookings", json={
        "customer_name": "Late Rider",
        "customer_phone": "+12895550004",
        "pickup_address": "Hamilton GO Station, Hamilton, ON",
        "dropoff_address": "McMaster University, Hamilton, ON",
        "source": "web",
        "scheduled_for": past_time
    })
    assert r.status_code == 400
