from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class DriverStatus(str, Enum):
    available = "available"
    busy      = "busy"
    offline   = "offline"


class BookingStatus(str, Enum):
    pending    = "pending"
    dispatched = "dispatched"
    accepted   = "accepted"
    in_progress = "in_progress"
    completed  = "completed"
    cancelled  = "cancelled"


class BookingSource(str, Enum):
    web      = "web"
    phone    = "phone"
    admin    = "admin"
    voice_ai = "voice_ai"


# ── Request Models ─────────────────────────────────────────

class BookingRequest(BaseModel):
    customer_name:   str = Field(..., min_length=1, max_length=100)
    customer_phone:  str = Field(..., min_length=7,  max_length=20)
    pickup_address:  str = Field(..., min_length=3)
    dropoff_address: str = Field(..., min_length=3)
    source: BookingSource = BookingSource.web
    payment_method: str = "cash"  # "cash" or "stripe"


class FareEstimateRequest(BaseModel):
    pickup_address:  str = Field(..., min_length=3)
    dropoff_address: str = Field(..., min_length=3)


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
