from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum
from datetime import datetime


class DriverStatus(str, Enum):
    available = "available"
    busy      = "busy"
    offline   = "offline"


class BookingStatus(str, Enum):
    pending         = "pending"
    dispatched      = "dispatched"
    accepted        = "accepted"
    in_progress     = "in_progress"
    completed       = "completed"
    cancelled       = "cancelled"
    scheduled       = "scheduled"        # awaiting future dispatch
    dispatch_failed = "dispatch_failed"  # scheduler failed after retries
    needs_review    = "needs_review"


class BookingSource(str, Enum):
    web      = "web"
    phone    = "phone"
    admin    = "admin"
    voice_ai = "voice_ai"
    oasr     = "oasr"


# ── Request Models ─────────────────────────────────────────

class BookingRequest(BaseModel):
    customer_name:      str = Field(..., min_length=1, max_length=100)
    customer_phone:     str = Field(..., min_length=7,  max_length=20)
    pickup_address:     str = Field(..., min_length=3)
    dropoff_address:    str = Field(..., min_length=3)
    source:             BookingSource = BookingSource.web
    payment_method:     str = "cash"  # "cash" or "stripe"
    scheduled_for:      Optional[datetime] = None  # UTC ISO datetime; None = dispatch now
    service_type:       str = "standard"   # "standard" | "medical" | "long_distance"
    stops:              List[str] = []     # intermediate stop addresses (max 3)
    promo_code:         Optional[str] = None


class FareEstimateRequest(BaseModel):
    pickup_address:  str = Field(..., min_length=3)
    dropoff_address: str = Field(..., min_length=3)
    service_type:    str = "standard"
    stops:           List[str] = []
    promo_code:      Optional[str] = None


class DriverLoginRequest(BaseModel):
    phone: str
    pin:   str


class DriverLocationUpdate(BaseModel):
    latitude:  float
    longitude: float


class DriverStatusUpdate(BaseModel):
    status: DriverStatus


class RideActionRequest(BaseModel):
    action: str = Field(..., pattern="^(accept|decline)$")


class AdminAssignRequest(BaseModel):
    booking_id: str
    driver_id:  str


# ── Voice AI Request Model ──────────────────────────────────

class VoiceAIBookingRequest(BaseModel):
    """
    Posted by Voice AI agents (e.g. Vapi, Bland, Retell) to create a booking.
    The `agent_id` field identifies which AI agent submitted the request.
    """
    customer_name:   str   = Field(..., min_length=1, max_length=100)
    customer_phone:  str   = Field(..., min_length=7,  max_length=20)
    pickup_address:  str   = Field(..., min_length=3)
    dropoff_address: str   = Field(..., min_length=3)
    agent_id:        Optional[str]  = None   # e.g. "vapi_agent_123"
    call_id:         Optional[str]  = None   # for tracing
    notes:           Optional[str]  = None   # any extra notes from the call


class VoiceAIStatusRequest(BaseModel):
    """Used by Voice AI to check the status of a booking."""
    booking_id: str


# ── Response Models ────────────────────────────────────────

class FareEstimate(BaseModel):
    distance_km:    float
    estimated_fare: float
    pickup_coords:  Optional[dict] = None
    dropoff_coords: Optional[dict] = None


class BookingResponse(BaseModel):
    id:                     str
    customer_name:          str
    customer_phone:         str
    pickup_address:         str
    dropoff_address:        str
    estimated_distance_km:  Optional[float]
    estimated_fare:         Optional[float]
    status:                 str
    assigned_driver_id:     Optional[str]
    source:                 str
    created_at:             str


import uuid as _uuid
from datetime import timezone as _tz


# ── WebSocket / Event Models ───────────────────────────────────────────────────

class WebSocketMessage(BaseModel):
    """Standardized WebSocket message envelope."""
    type:       str
    payload:    dict = {}
    timestamp:  str  = Field(default_factory=lambda: datetime.now(_tz.utc).isoformat())
    message_id: str  = Field(default_factory=lambda: str(_uuid.uuid4()))


class DispatchEvent(BaseModel):
    booking_id:  str
    driver_id:   Optional[str] = None
    event_type:  str  # dispatched, accepted, declined, timeout, failed
    attempt:     int  = 1
    timestamp:   str  = Field(default_factory=lambda: datetime.now(_tz.utc).isoformat())


# ── Analytics Models ──────────────────────────────────────────────────────────

class DriverPerformance(BaseModel):
    driver_id:         str
    driver_name:       str
    trips_completed:   int   = 0
    trips_accepted:    int   = 0
    trips_declined:    int   = 0
    acceptance_rate:   float = 0.0
    total_earnings:    float = 0.0
    avg_trip_minutes:  float = 0.0
    cancellation_rate: float = 0.0


class RevenueReport(BaseModel):
    period:        str
    total_revenue: float
    total_trips:   int
    avg_fare:      float
    buckets:       list = []


class AnalyticsSummary(BaseModel):
    today_revenue:        float = 0.0
    today_bookings:       int   = 0
    active_drivers:       int   = 0
    fleet_total:          int   = 0
    avg_trip_minutes:     float = 0.0
    booking_success_rate: float = 0.0
    avg_match_seconds:    float = 0.0
    cancellation_rate:    float = 0.0
    payment_success_rate: float = 0.0
    avg_fare_cad:         float = 0.0


# ── Webhook Models ────────────────────────────────────────────────────────────

class SMSWebhookPayload(BaseModel):
    """Twilio inbound SMS webhook payload (form-encoded fields)."""
    From:       str = ""
    To:         str = ""
    Body:       str = ""
    MessageSid: str = ""
    AccountSid: str = ""
    NumMedia:   str = "0"


class VapiWebhookPayload(BaseModel):
    """Vapi function-call webhook payload."""
    type:         str
    call:         Optional[dict] = None
    transcript:   Optional[str]  = None
    functionCall: Optional[dict] = None
    timestamp:    Optional[str]  = None
