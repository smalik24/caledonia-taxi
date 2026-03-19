import pytest
from unittest.mock import patch, MagicMock


async def test_create_intent_returns_client_secret(client):
    mock_intent = MagicMock()
    mock_intent.client_secret = "pi_test_secret_123"

    with patch("main.stripe_lib") as mock_stripe:
        mock_stripe.PaymentIntent.create.return_value = mock_intent
        with patch("main.STRIPE_SECRET_KEY", "sk_test_fake"):
            with patch("main.geocode_address") as mock_geo:
                mock_geo.return_value = {"lat": 43.25, "lng": -79.87}
                with patch("main.get_route_distance") as mock_dist:
                    mock_dist.return_value = 6.2
                    r = await client.post("/api/payments/create-intent", json={
                        "pickup_address": "Hamilton GO Station",
                        "dropoff_address": "McMaster University"
                    })
    assert r.status_code == 200
    data = r.json()
    assert "client_secret" in data
    assert "amount" in data
    assert "publishable_key" in data


async def test_create_intent_no_stripe_key(client):
    with patch("main.STRIPE_SECRET_KEY", ""):
        r = await client.post("/api/payments/create-intent", json={
            "pickup_address": "Hamilton GO Station",
            "dropoff_address": "McMaster University"
        })
    assert r.status_code == 503


async def test_cash_booking_has_payment_fields(client):
    r = await client.post("/api/bookings", json={
        "customer_name": "Test User",
        "customer_phone": "+12895550000",
        "pickup_address": "Hamilton GO Station, Hamilton, ON",
        "dropoff_address": "McMaster University, Hamilton, ON",
        "source": "web",
        "payment_method": "cash"
    })
    assert r.status_code == 200
    booking = r.json().get("booking") or r.json()
    assert booking.get("payment_method") == "cash"
    assert booking.get("payment_status") == "unpaid"


def test_payment_state_machine_constants():
    """All required payment states exist."""
    import sys; sys.path.insert(0, "/Users/saqib/Downloads/caledonia-taxi/backend")
    from main import PAYMENT_STATES
    for s in ["unpaid", "payment_initiated", "authorized", "captured", "refunded", "failed"]:
        assert s in PAYMENT_STATES, f"Missing state: {s}"


def test_valid_payment_transitions():
    """Only allowed state transitions return True."""
    import sys; sys.path.insert(0, "/Users/saqib/Downloads/caledonia-taxi/backend")
    from main import is_valid_payment_transition
    assert is_valid_payment_transition("unpaid", "payment_initiated") is True
    assert is_valid_payment_transition("authorized", "captured") is True
    assert is_valid_payment_transition("captured", "refunded") is True
    assert is_valid_payment_transition("failed", "payment_initiated") is True  # retry
    assert is_valid_payment_transition("captured", "unpaid") is False
    assert is_valid_payment_transition("refunded", "captured") is False
    assert is_valid_payment_transition("abandoned", "unpaid") is False


def test_advance_payment_state_success():
    """advance_payment_state returns True and updates booking on valid transition."""
    import sys; sys.path.insert(0, "/Users/saqib/Downloads/caledonia-taxi/backend")
    from main import advance_payment_state
    booking = {"id": "test-1", "payment_status": "unpaid"}
    result = advance_payment_state(booking, "payment_initiated")
    assert result is True
    assert booking["payment_status"] == "payment_initiated"


def test_advance_payment_state_invalid():
    """advance_payment_state returns False and does NOT update on invalid transition."""
    import sys; sys.path.insert(0, "/Users/saqib/Downloads/caledonia-taxi/backend")
    from main import advance_payment_state
    booking = {"id": "test-2", "payment_status": "captured"}
    result = advance_payment_state(booking, "unpaid")  # can't go backwards
    assert result is False
    assert booking["payment_status"] == "captured"  # unchanged
