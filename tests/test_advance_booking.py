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


async def test_scheduler_dispatches_when_within_10_minutes():
    """Scheduler should pick up bookings whose scheduled_for is within 10 min."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
    from main import bookings_db
    from scheduler import dispatch_scheduled_now
    from datetime import datetime, timezone, timedelta

    # Plant a scheduled booking due in 5 minutes
    booking_id = "test-sched-scheduler-001"
    bookings_db[booking_id] = {
        "id": booking_id,
        "status": "scheduled",
        "scheduled_for": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        "customer_phone": "+12895550099",
        "pickup_address": "Test Pickup",
        "dropoff_address": "Test Dropoff",
        "estimated_fare": 15.0,
        "estimated_distance_km": 5.0,
        "assigned_driver_id": None,
        "source": "web",
    }
    dispatched_ids = []

    async def fake_dispatch(booking):
        dispatched_ids.append(booking["id"])

    await dispatch_scheduled_now(bookings_db, fake_dispatch)
    assert booking_id in dispatched_ids
    assert bookings_db[booking_id]["status"] == "dispatching"


async def test_scheduler_skips_non_scheduled_bookings():
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
    from main import bookings_db
    from scheduler import dispatch_scheduled_now
    from datetime import datetime, timezone, timedelta

    booking_id = "test-active-scheduler-001"
    bookings_db[booking_id] = {
        "id": booking_id,
        "status": "in_progress",  # not scheduled — should be skipped
        "scheduled_for": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
    }
    dispatched_ids = []
    async def fake_dispatch(b): dispatched_ids.append(b["id"])

    await dispatch_scheduled_now(bookings_db, fake_dispatch)
    assert booking_id not in dispatched_ids
