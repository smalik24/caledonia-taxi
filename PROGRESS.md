# PROGRESS — Caledonia Taxi v2.0
## Overnight Automation Summary
**Date:** 2026-03-17 | **Status:** All 6 goals COMPLETE ✅

---

## What Was Built Tonight

### GOAL 1 — DESIGN ✅
**Full dark-mode UI overhaul across all 3 apps.**

| Page | Changes |
|------|---------|
| `booking.html` | Premium dark hero, route connector UI, feature pills, clean step indicators, SMS notice on confirmation |
| `driver.html` | Professional login with vehicle info, SVG countdown ring (animated arc instead of plain number), earnings bar, call-link button, session stats |
| `admin.html` | Tab-based layout (Bookings / Drivers / SMS Log / Email Log / Activity), live activity feed, receipt download button, driver fleet with vehicle info |
| `style.css` | Complete rewrite — true dark (#080811 bg), gold accents (#FFD700), glass morphism header, custom scrollbars, animated live-dot, dark Leaflet tiles |

**Design philosophy:** iCabbie-rival. Every screen feels like a premium app — dark, sharp, gold accents. Mobile-first with responsive grid breakpoints at 768px and 480px.

---

### GOAL 2 — DISPATCH ENGINE ✅
**Enhanced nearest-driver algorithm with ETA and vehicle data.**

Changes to `main.py` + `services.py`:
- Dispatch now **calculates ETA in minutes** (haversine distance / 30 km/h)
- ETA is sent with the `new_ride` WebSocket event to drivers
- Driver records now include `vehicle`, `plate`, `rating`, `trips_completed`
- Demo drivers updated: Saqib, Marcus, Priya, James (all with vehicles assigned)
- SMS fires automatically on dispatch success with driver name + vehicle + ETA

**Dispatch flow:**
```
Booking created → geocode → calculate fare → save → SMS "confirmed" → dispatch task
  → find nearest available driver
  → send WebSocket new_ride (with 30s timeout + ETA)
  → wait 30s
  → if accepted: SMS "driver assigned" with vehicle + ETA → done
  → if timeout/decline: try next nearest driver (up to 4 attempts)
  → if all fail: SMS "no drivers available"
```

---

### GOAL 3 — SMS ✅
**Full SMS lifecycle with 6 professional message templates.**

New file: `backend/sms_service.py`

| Trigger | Message Sent |
|---------|-------------|
| Booking created | "Hi [Name]! Your Caledonia Taxi is booked (Ref #XXXXXXXX). Est. fare: $XX.XX CAD…" |
| Driver assigned | "Your driver [Name] is on the way in a [Vehicle]. ETA: ~X min…" |
| Driver arrived | "[Name] has arrived at your pickup in a [Vehicle]. Please come outside." |
| Ride started | "Your ride has started. Heading to [Dropoff]…" |
| Ride completed | "Thanks for riding, [Name]! Final fare: $XX.XX CAD. PDF receipt emailed." |
| Dispatch failed | "Sorry — no drivers available right now. Please call (289) 555-1001…" |
| Booking cancelled | "Your booking #XXXXXXXX has been cancelled. No charge applies." |
| Voice AI booking | "Your phone booking is confirmed! Pickup: … Drop-off: … Est. fare: $XX" |

All messages are **mock** — printed to console, stored in memory, viewable in Admin → SMS Log tab.
**To go live:** 4-line code change in `sms_service.py`. See `MORNING_SETUP.md`.

---

### GOAL 4 — HEATMAP ✅
**Full interactive demand heatmap with Leaflet.js.**

New file: `frontend/templates/heatmap.html`
New endpoint: `GET /api/admin/heatmap-data`

**Features:**
- **CartoDB Dark Matter** tile layer (dark map matches app theme)
- **Leaflet.heat** plugin renders booking pickup locations as heat overlay
- **Driver position markers** — colored dots (green = available, orange = busy)
- **Toggle layers** — Heat / Drivers / Pickups buttons
- **Top Pickup Zones** sidebar — ranked bar chart of hottest areas
- **Driver positions panel** — live list with coordinates + status
- **Mini stats bar** — Total bookings, Active drivers, Hottest zone, Last refresh
- **Auto-refresh** every 15 seconds

**Zone detection:** matches addresses against 30+ Hamilton landmarks (Jackson Square, McMaster, Hamilton GO, Airport, etc.)

---

### GOAL 5 — INVOICING ✅
**PDF receipt generator + mock email trigger on every completed ride.**

New file: `backend/invoice_service.py`
New endpoint: `GET /api/bookings/{id}/receipt`

**PDF receipt includes:**
- Caledonia Taxi header with gold HR divider
- Booking reference, date/time, customer name + phone
- Trip details: Pickup, Drop-off, Distance
- Fare breakdown table: Base fare ($4.50) + Distance charge ($2.10/km) = TOTAL
- Gold-highlighted total row
- Footer: Thank you message + contact info + generation timestamp

**Email trigger:** fires automatically when `completeRide()` is called (driver presses "Complete Ride"). Logged in Admin → Email Log tab.

**Download:** Admin can click "🧾 Receipt" button on any completed booking to download PDF directly.

**To go live:** 15-line code change in `invoice_service.py`. See `MORNING_SETUP.md`.

---

### GOAL 6 — VOICE AI HOOKS ✅
**3 API endpoints purpose-built for Voice AI agent integration.**

| Endpoint | Method | Use Case |
|----------|--------|----------|
| `POST /api/voice-ai/booking` | POST | Agent posts completed booking from call |
| `GET /api/voice-ai/status/{id}` | GET | Agent checks status for verbal readback |
| `POST /api/voice-ai/fare-estimate` | POST | Agent gets fare + TTS-ready string |

**All responses include `tts_message`** — a natural-language string the AI agent can read directly to the caller (e.g. *"Your estimated fare is 14 dollars for approximately 4.8 kilometres. Shall I confirm your booking?"*)

**Source tracking:** Voice AI bookings are tagged `source: "voice_ai"` and show a distinct orange badge in the admin panel.

**Compatible with:** Vapi.ai, Bland.ai, Retell AI, custom Twilio Studio flows. Full Vapi tool definition in `MORNING_SETUP.md`.

---

## New Files Created

```
backend/
  sms_service.py         ← Mock SMS with 8 templates
  invoice_service.py     ← PDF receipt + mock email

frontend/templates/
  heatmap.html           ← Leaflet heatmap page

MORNING_SETUP.md         ← Production activation guide
PROGRESS.md              ← This file
```

## Files Modified

```
backend/
  main.py                ← +200 lines: SMS hooks, invoicing, heatmap API, Voice AI endpoints, /heatmap route
  models.py              ← VoiceAIBookingRequest, VoiceAIStatusRequest, updated BookingSource enum
  requirements.txt       ← Added: reportlab

frontend/
  static/css/style.css   ← Complete dark theme rewrite (~450 lines)
  templates/booking.html ← Full redesign (dark, route UI, SMS notice)
  templates/driver.html  ← Full redesign (SVG ring, earnings bar, vehicle info)
  templates/admin.html   ← Full redesign (tabs, SMS log, email log, activity feed)
```

---

## API Endpoint Summary (v2.0)

### Pages
| Route | Description |
|-------|-------------|
| `GET /` | Customer booking page |
| `GET /driver` | Driver app |
| `GET /admin` | Admin dashboard |
| `GET /heatmap` | Demand heatmap (NEW) |

### Bookings
| Route | Description |
|-------|-------------|
| `POST /api/estimate-fare` | Fare estimate |
| `POST /api/bookings` | Create booking (+ SMS) |
| `GET /api/bookings` | List all |
| `GET /api/bookings/{id}` | Get single |
| `PATCH /api/bookings/{id}/cancel` | Cancel (+ SMS) |
| `GET /api/bookings/{id}/receipt` | Download PDF receipt (NEW) |

### Drivers
| Route | Description |
|-------|-------------|
| `POST /api/drivers/login` | Driver sign-in |
| `GET /api/drivers` | List all |
| `PATCH /api/drivers/{id}/status` | Update status |
| `PATCH /api/drivers/{id}/location` | GPS update |

### Ride Lifecycle
| Route | Description |
|-------|-------------|
| `POST /api/rides/{id}/action/{driver}` | Accept/Decline |
| `POST /api/rides/{id}/start/{driver}` | Pickup confirmed (+ SMS) |
| `POST /api/rides/{id}/complete/{driver}` | Complete (+ SMS + PDF email) |

### Admin
| Route | Description |
|-------|-------------|
| `POST /api/admin/assign` | Manual assignment |
| `GET /api/admin/stats` | Dashboard stats |
| `GET /api/admin/sms-log` | SMS log (NEW) |
| `GET /api/admin/email-log` | Email log (NEW) |
| `GET /api/admin/heatmap-data` | Heatmap data (NEW) |

### Voice AI
| Route | Description |
|-------|-------------|
| `POST /api/voice-ai/booking` | Create booking via AI (NEW) |
| `GET /api/voice-ai/status/{id}` | Status + TTS message (NEW) |
| `POST /api/voice-ai/fare-estimate` | Fare + TTS message (NEW) |

### WebSockets
| Route | Description |
|-------|-------------|
| `WS /ws/{channel}` | Generic broadcast |
| `WS /ws/driver/{id}` | Driver-specific |

### Twilio Phone Agent
| Route | Description |
|-------|-------------|
| `POST /api/twilio/voice` | Inbound call handler |
| `POST /api/twilio/gather-pickup` | Pickup speech |
| `POST /api/twilio/gather-dropoff` | Dropoff speech |
| `POST /api/twilio/confirm` | Confirmation + booking |

---

## How To Start The Server

```bash
cd /Users/saqib/Downloads/caledonia-taxi
pip3 install -r requirements.txt
cd backend
python main.py
```

Then visit:
- **Customer:** http://localhost:8000/
- **Driver:** http://localhost:8000/driver
- **Admin:** http://localhost:8000/admin
- **Heatmap:** http://localhost:8000/heatmap
- **API Docs:** http://localhost:8000/docs

**Demo credentials (driver login):**
| Driver | Phone | PIN | Vehicle |
|--------|-------|-----|---------|
| Saqib | +12895551001 | 1234 | White Honda CR-V |
| Marcus | +12895551002 | 2345 | Black Toyota Camry |

---

## Next Steps (Your Priority List)

1. **[ ] Run `pip3 install -r requirements.txt`** to get ReportLab
2. **[ ] Get ORS API key** (free at openrouteservice.org) → real geocoding
3. **[ ] Get Twilio account** → enable real SMS (see `MORNING_SETUP.md`)
4. **[ ] Get Resend account** → enable real PDF email receipts
5. **[ ] Set up Supabase** → persistent database (not in-memory)
6. **[ ] Connect Vapi.ai** → Voice AI agent with the booking endpoint
7. **[ ] Deploy to Railway** → public URL for live testing

---

*All mock functions are properly labeled and swappable. No money was spent. The system runs 100% on free tiers in demo mode.*

*— Built overnight by Claude (claude-sonnet-4-6)*
