"""Tests for new Pydantic models added in production hardening."""
import sys
sys.path.insert(0, "/Users/saqib/Downloads/caledonia-taxi/backend")


def test_websocket_message_has_auto_fields():
    from models import WebSocketMessage
    msg = WebSocketMessage(type="ping", payload={"test": 1})
    assert msg.type == "ping"
    assert msg.payload == {"test": 1}
    assert msg.message_id  # auto-generated UUID
    assert msg.timestamp   # auto-generated ISO string
    assert "Z" in msg.timestamp or "+" in msg.timestamp or len(msg.timestamp) > 10


def test_dispatch_event_model():
    from models import DispatchEvent
    ev = DispatchEvent(booking_id="b-1", event_type="dispatched")
    assert ev.booking_id == "b-1"
    assert ev.attempt == 1  # default


def test_analytics_summary_model():
    from models import AnalyticsSummary
    summary = AnalyticsSummary(today_revenue=150.50, today_bookings=12)
    assert summary.today_revenue == 150.50
    assert summary.booking_success_rate == 0.0  # default


def test_driver_performance_model():
    from models import DriverPerformance
    perf = DriverPerformance(driver_id="d-1", driver_name="Marcus")
    assert perf.acceptance_rate == 0.0
    assert perf.trips_completed == 0


def test_revenue_report_model():
    from models import RevenueReport
    report = RevenueReport(period="day", total_revenue=500.0, total_trips=30, avg_fare=16.67)
    assert report.period == "day"
    assert report.buckets == []


def test_sms_webhook_payload():
    from models import SMSWebhookPayload
    payload = SMSWebhookPayload(From="+12895550099", To="+12895551001", Body="CANCEL")
    assert payload.Body == "CANCEL"
    assert payload.From == "+12895550099"


def test_vapi_webhook_payload():
    from models import VapiWebhookPayload
    payload = VapiWebhookPayload(type="call-started")
    assert payload.type == "call-started"
    assert payload.call is None
