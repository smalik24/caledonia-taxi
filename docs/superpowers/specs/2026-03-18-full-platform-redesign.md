# Caledonia Taxi — Full Platform Redesign
**Date:** 2026-03-18
**Status:** Approved for implementation
**Scope:** Complete UI overhaul + business logic upgrade

---

## 1. Design System — Uber Noir

### Palette
| Token | Value | Use |
|-------|-------|-----|
| `--bg` | `#000000` | Page background |
| `--surface-1` | `#0D0D0D` | Cards, panels |
| `--surface-2` | `#111111` | Inputs, rows |
| `--surface-3` | `#1A1A1A` | Hover states |
| `--border` | `#222222` | Borders |
| `--border-subtle` | `#1A1A1A` | Dividers |
| `--text-primary` | `#FFFFFF` | Headlines, values |
| `--text-secondary` | `#888888` | Labels, metadata |
| `--text-muted` | `#444444` | Placeholder text |
| `--accent` | `#FFFFFF` | Primary CTA background |
| `--accent-text` | `#000000` | Text on primary CTA |
| `--green` | `#22C55E` | Available, success |
| `--amber` | `#F59E0B` | Busy, warning |
| `--red` | `#EF4444` | Offline, error, cancel |
| `--blue` | `#3B82F6` | Info, links |

### Typography
- Font stack: `-apple-system, 'SF Pro Display', 'Helvetica Neue', sans-serif`
- Mono: `'SF Mono', 'Menlo', monospace`
- No web fonts loaded (system stack = instant, feels native)
- Heading weight: 700. Body weight: 400. Label weight: 500.
- Letter-spacing: `-0.02em` on headings, `0.08em` on uppercase labels

### Component Rules
- Border-radius: `8px` for cards/panels, `6px` for inputs/buttons, `50px` for pill badges
- No box shadows — borders only
- No gradients — flat fills only
- Transitions: `150ms ease` on hover/focus states only
- Input focus: `border-color: #fff` (no glow ring)
- Buttons: white bg + black text (primary), transparent + white border + white text (secondary)
- All status dots: 8px circle, colour-coded

### Shared CSS File
All three apps load `/static/css/design-system.css`. Templates use CSS custom properties. No per-template colour overrides.

---

## 2. Customer Booking App (`/`)

### Structure
Single-page app, no landing hero. The booking form **is** the entire page. Header shows only logo + "Call Us" link.

### Service Selector (Step 0 — always visible)
Horizontal pill row at top of form:
- **Standard** — regular ride, metered per km
- **Medical** — OASR/non-emergency, same meter, flags ride as medical in system
- **Long Distance** — reveals city picker with flat rates

### Step 1: Route
- Pickup address input (with autocomplete via ORS geocoding)
- "+ Add Stop" button — adds up to 3 intermediate stop inputs
- Each stop has a remove (×) button
- Dropoff address input
- **Long Distance mode:** City selector dropdown replaces dropoff (Hamilton, Burlington, Oakville, Mississauga, Toronto, Pearson Airport, Billy Bishop Airport) + optional specific address within city
- Now / Schedule toggle
- Customer name + phone inputs

### Step 2: Fare Preview
- Route summary card: pickup → [stop 1] → [stop 2] → dropoff
- **Itemised fare breakdown:**
  - Base fare: $X.XX
  - Per leg: `{leg name} ({km} km) — $X.XX` (one row per leg)
  - Stop surcharge × N: $X.XX (if stops)
  - Promo discount: -$X.XX (if applied)
  - Surge: ×1.5 (if active)
  - **Total: $XX.XX**
- Promo code input + Apply button
- Payment method: Cash | Card (Stripe Elements)
- Surge banner (red pill, visible only when surge active)

### Step 3: Confirmed
- Booking ID (monospace, large)
- Full route summary
- Estimated arrival time
- Driver details once dispatched (name, vehicle, plate, ETA)
- "Track your ride →" link to `/track/{id}`

### Step 4: Rate Driver
- 5-star tap targets
- Optional comment (max 200 chars)
- Submit button

### JavaScript Architecture
- Single `app.js` module pattern, no framework
- `fareEngine` object: `estimate(legs, service, flatRates)` → breakdown object
- `addressAutocomplete` wrapper around ORS geocoding API
- `surgePoller`: checks `/api/surge` on load + every 2 min
- `paymentHandler`: Stripe Elements for card, no-op for cash

### fareEngine Contract
**Input:**
```js
fareEngine.estimate(
  legs,       // Array<{ from: string, to: string, km: number }>
  service,    // "standard" | "medical" | "long_distance"
  options     // { flatRates: {city: price}, surgeMultiplier: 1.0, promoDiscount: 0.0, stopSurcharge: 3.00 }
)
```
**Output:**
```js
{
  legs: [{ label: "Pickup → Stop 1", km: 2.1, subtotal: 8.91 }],
  // Each leg: { label: string, km: number, subtotal: number }
  // leg.subtotal = (service === "standard" || service === "medical")
  //   ? base_fare_for_leg_1_only + leg.km * per_km_rate
  //   : 0  (for long_distance, only the first leg contributes the flat_rate)
  base_fare: 4.50,
  stop_surcharge: 6.00,   // options.stopSurcharge × stop count (intermediate stops only)
  subtotal: 32.41,        // sum(leg.subtotal) + stop_surcharge
  promo_discount: -3.24,  // subtotal × options.promoDiscount (negative, 0 if no promo)
  surge_addition: 4.86,   // subtotal × (options.surgeMultiplier - 1.0) (0 if multiplier = 1.0)
  total: 29.17,           // subtotal + promo_discount + surge_addition, never below minimum_fare
  is_flat_rate: false     // true for long_distance; legs[0].subtotal = flat_rate in that case
}
```
**Parity rule:** `services.py` on the server MUST implement the identical formula. The server-side result is authoritative for Stripe payment amounts. The client-side `fare-engine.js` is for display only. Any discrepancy between them is a bug. The formula in Section 5 ("Fare Engine") is the canonical reference for both.

---

## 3. Driver App (`/driver`)

### Login Screen
- Full-screen black, centered form
- Logo at top
- Phone + PIN inputs
- "Sign In" white CTA button

### Dashboard (post-login)
**Header bar:**
- Driver name + status dot
- Today's earnings (large, right-aligned)

**Status toggle:**
- Three equal-width buttons: Available | Busy | Offline
- Active state: white bg + black text; inactive: transparent + border

**Stats row:**
- Trips today | Avg rating | Acceptance rate

**GPS badge:**
- "📍 GPS Active" (green) / "📍 GPS Off" (grey)
- Tapping it toggles GPS and updates status

### Incoming Ride Request (modal overlay)
- Slides up from bottom (full-width, black)
- Service type badge (Standard / Medical / Long Distance)
- Customer name, phone (tap to call)
- Full route: pickup → all stops → dropoff
- Estimated distance (total km across all legs)
- Estimated fare (full breakdown)
- SVG countdown ring (30 sec)
- **Accept** (white button) | **Decline** (outlined button)

### Active Ride Panel
- Replaces dashboard content
- Current leg highlighted (e.g. "Leg 2 of 3 — En route to Stop 1")
- Full stop list with check marks as each is completed
- **"+ Add Stop"** button — opens bottom sheet with address input, adds to ride and recalculates fare in real time
- **Start Trip** button (only shown when at pickup, before trip starts)
- **Complete Ride** button (only shown at final dropoff)
- Shows live fare accumulating as km ticks up (for standard/metered rides)

### Fare Recalculation on Live Stop
When driver adds a stop during ride:
1. New stop appended to route
2. `POST /api/bookings/{id}/stops` — server adds stop, recalculates total fare
3. Driver sees updated total immediately
4. Customer tracking page also updates

---

## 4. Admin Panel (`/admin`)

### Login Gate
- Same Uber Noir login screen as driver (different endpoint)
- Rate-limited to 10 attempts / 60s

### Navigation
Horizontal tab bar (no sidebar):
`Dashboard | Orders | Tracking | OASR | Revenue | Drivers | Receipts | Settings`

Active tab: white bottom border, white text. Inactive: `--text-secondary`.

---

### Tab: Dashboard
- 4 KPI cards: Today's Bookings | Today's Revenue | Active Drivers | Pending Dispatches
- Recent activity feed (last 20 events, real-time via WebSocket)
- Quick dispatch: unassigned pending bookings list, "Assign Driver" dropdown per row

---

### Tab: Orders
- Full booking list, newest first
- Filter row: All | Pending | Dispatched | Active | Completed | Cancelled
- Period filter: Today | This Week | This Month | All Time
- Per row: Booking ID, Service type badge, Customer name, Route summary, Status badge, Driver, Fare, Created time
- Row actions: View receipt | Cancel | Reassign driver
- Excel export button (SheetJS)

---

### Tab: Tracking (NEW)
- Full-width Leaflet map (dark CartoDB tiles), fills the tab content area
- Driver pins as coloured circles: green (available), amber (busy/on ride), grey (offline)
- Clicking a pin opens a right-side drawer:
  - Driver name, vehicle, plate
  - Current status
  - Active booking details (if on ride): customer name, route, ETA to next stop
  - Phone number (tap to call link)
- Active ride routes shown as dashed white polylines on map
- Pickup markers (white circle) and dropoff markers (white × ) for active rides
- Legend strip at bottom of map: ● Available ● On Ride ● Offline
- Auto-refreshes every 10 seconds via `GET /api/admin/driver-locations`

---

### Tab: OASR (NEW — Medical Ride Automation)
**Purpose:** Automates the manual process of receiving OASR emails and forwarding to drivers.

**How it works:**
1. Owner receives OASR email, forwards it to a special inbox (e.g. `oasr@caledonia.taxi` or uses SendGrid Inbound Parse webhook)
2. Webhook at `POST /api/oasr/inbound` receives the raw email
3. Parser extracts: patient name, pickup address, dropoff (hospital/clinic name + address), date, time, any notes
4. Creates a `scheduled` booking with `service_type = "medical"`
5. Dispatch fires automatically via APScheduler the day before (evening notification to driver) and again 30 min before pickup

**OASR Tab UI:**
- List of all OASR-sourced bookings
- Columns: Date/Time, Patient (anonymised if needed), Pickup, Dropoff, Driver Assigned, Status
- "Parse incoming email" manual entry form (fallback: paste email text, system parses it)
- Status badges: Parsed | Scheduled | Dispatched | Completed
- Override button: reassign driver or edit details

---

### Tab: Revenue
- Period selector: Today | This Week | This Month | Custom range
- Bar chart: daily revenue (pure CSS bars or Chart.js)
- Breakdown table: bookings count, total revenue, avg fare per day
- Service type split: Standard vs Medical vs Long Distance
- Top routes (pickup city → dropoff city, by frequency)
- Excel export

---

### Tab: Drivers
- Driver cards: photo placeholder, name, vehicle, plate, rating, status
- KPIs per driver: Total trips | Completed | Earnings (all time) | Acceptance rate | Avg rating
- Edit driver button (name, phone, PIN, vehicle, plate)
- Add new driver button
- Deactivate driver button (soft delete — sets status to `inactive`)

---

### Tab: Receipts
- All completed bookings with receipts
- Filter by driver, date range, service type
- Per row: Booking ID, date, customer, driver, route, fare breakdown, payment method
- Download PDF receipt per row
- Excel export (full accounting export with all columns)

---

### Tab: Settings (NEW)
**Pricing:**
- Base fare (editable)
- Per km rate (editable)
- Stop surcharge (editable)
- Minimum fare (editable)

**Long Distance Flat Rates:**
- Table: Destination | Flat Rate
- Add/edit/delete destinations
- Saved to `.env` or a settings file, applied immediately

**Promo Codes:**
- Active codes list: Code | Discount % | Uses | Active toggle
- Add new promo code

**Surge Pricing:**
- Enable/disable surge
- Threshold settings (pending bookings ≥ N, available drivers ≤ M)
- Multipliers (1.5× and 2.0× thresholds)

---

## 5. Fare Engine

### Standard Rides
```
fare = base_fare + (total_km × per_km_rate) + (stop_count × stop_surcharge)
fare = max(fare, minimum_fare)
fare = fare × surge_multiplier (if active)
fare = fare × (1 - promo_discount) (if promo applied)
```

### Long Distance Rides
```
fare = flat_rate[destination_city]
stops still add stop_surcharge per intermediate stop
```

### Medical Rides (OASR)
```
fare = same as Standard (metered)
flagged as medical in booking record
OASR bookings may have a predetermined rate in the email — if so, override fare
```

### Live Stop Addition (during ride)
When driver adds a stop mid-ride:
```
new_total_km = sum of all legs including new stop
new_fare = recalculate full fare with updated km + stop count
delta = new_fare - previous_fare
booking.actual_fare += delta  (not estimated_fare)
```

### Receipt Breakdown
Every receipt shows:
```
Leg 1: Pickup → Stop 1 (X.X km)    $XX.XX
Leg 2: Stop 1 → Dropoff (X.X km)   $XX.XX
Stop surcharge × N                  $ X.XX
──────────────────────────────────────────
Subtotal                            $XX.XX
Promo (CODE) -X%                   -$ X.XX
Surge ×1.5                         +$ X.XX
──────────────────────────────────────────
Total                               $XX.XX
Payment: Cash / Card ····1234
```

---

## 6. OASR Email Parser

### Input
Raw email text (from forwarded email or SendGrid Inbound Parse webhook).

### Parser Strategy
Regex + keyword extraction:
- Date: look for patterns like `March 19, 2026` / `2026-03-19` / `19/03/26`
- Time: `HH:MM AM/PM` or `HH:MM`
- Pickup: lines containing "pickup:", "from:", "pick up at:", or address patterns
- Dropoff: lines containing "drop:", "destination:", "to:", hospital/clinic names
- Patient name: line after "patient:", "name:", or first proper noun near scheduling context
- Notes: anything after "notes:", "special instructions:", "comments:"

### Fallback
If parser confidence is low (< 3 fields extracted), flag booking with status `needs_review` and show it prominently in the OASR tab for manual correction. `needs_review` is added to `BookingStatus` enum in `models.py`.

### BookingStatus additions
- `needs_review` — OASR parse incomplete, requires admin edit before dispatch
- (existing values preserved: `pending`, `dispatched`, `accepted`, `in_progress`, `completed`, `cancelled`, `scheduled`, `dispatch_failed`)

### BookingSource additions
- `oasr` — booking originated from OASR email parser
- (existing values preserved: `web`, `phone`, `admin`, `voice_ai`)

OASR Tab status badge set: `Needs Review` (red) | `Parsed` (blue) | `Scheduled` (amber) | `Dispatched` (green) | `Completed` (grey)

### Endpoint
`POST /api/oasr/inbound`
- Accepts: `{ "raw_email": "..." }` (JSON) or raw email via SendGrid Inbound Parse (multipart form)
- Returns: created booking ID or error

### Manual Entry Fallback
Admin can paste raw email text into a textarea in the OASR tab. "Parse & Create" button calls the same endpoint.

---

## 7. New Backend Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/bookings/{id}/stops` | Add live stop during ride, recalculate fare |
| `GET` | `/api/flat-rates` | List long distance flat rates |
| `POST` | `/api/flat-rates` | Add/update flat rate (admin) |
| `DELETE` | `/api/flat-rates/{city}` | Remove flat rate (admin) |
| `POST` | `/api/oasr/inbound` | Receive + parse OASR email |
| `GET` | `/api/admin/oasr` | List all OASR bookings (admin) |
| `GET` | `/api/admin/driver-locations` | All driver lat/lng + status for map |
| `GET` | `/api/admin/settings` | Get pricing + promo + surge settings |
| `POST` | `/api/admin/settings` | Update settings |
| `POST` | `/api/drivers` | Create new driver (admin) |
| `PUT` | `/api/drivers/{id}` | Edit driver (name, phone, PIN, vehicle, plate) |
| `PATCH` | `/api/drivers/{id}/deactivate` | Soft-delete driver (sets status to `inactive`) |

#### `POST /api/drivers` request body
```json
{ "name": "James", "phone": "+12895551005", "pin": "5678", "vehicle": "Grey Toyota Camry", "plate": "CTXI-005" }
```
Response: `{ "id": "uuid", ...driver fields }`

#### `PUT /api/drivers/{id}` request body (all fields optional)
```json
{ "name": "James T.", "phone": "+12895551005", "pin": "9999", "vehicle": "Grey Toyota Camry", "plate": "CTXI-005" }
```
Response: updated driver object.

#### `POST /api/estimate-fare` response `legs[]` shape
Each element: `{ "label": "Pickup → Stop 1", "km": 2.1, "subtotal": 8.91 }` — identical to `fareEngine` JS output.

### Updated Existing Endpoints
- `POST /api/estimate-fare` — updated to accept `service_type`, `stops[]` (array of address strings), `promo_code`; returns `{ estimated_fare, fare_breakdown, legs[] }` (see fare contract below)
- `POST /api/payments/create-intent` — updated to accept same fields; uses server-side fare calculation as payment amount authority (client preview is informational only)
- `GET /api/admin/driver-history` — updated to include `acceptance_rate` (accepted / total dispatched from `dispatch_log` table)

### Endpoint Schemas

#### `POST /api/bookings/{id}/stops`
**Request:**
```json
{ "address": "123 Main St, Hamilton ON", "lat": 43.25, "lng": -79.86 }
```
`lat`/`lng` are optional — server geocodes if omitted.
**Response:**
```json
{
  "booking_id": "abc123",
  "actual_fare": 28.50,
  "fare_breakdown": { "legs": [...], "stop_surcharge": 6.00, "total": 28.50 }
}
```

#### `GET /api/admin/driver-locations`
**Response:**
```json
[
  {
    "id": "driver-uuid",
    "name": "Saqib",
    "vehicle": "White Honda CR-V",
    "plate": "CTXI-001",
    "status": "busy",
    "lat": 43.0773,
    "lng": -79.9408,
    "last_update": "2026-03-18T03:10:00Z",
    "active_booking": {
      "id": "booking-uuid",
      "customer_name": "Jane Smith",
      "pickup_address": "12 King St, Caledonia",
      "dropoff_address": "Hamilton General Hospital",
      "stops": ["45 Argyle St, Caledonia"],
      "current_leg": 1,
      "total_legs": 2,
      "waypoints": [[43.075, -79.94], [43.082, -79.93], [43.255, -79.868]],
      "estimated_fare": 32.00
    }
  }
]
```
`active_booking` is `null` when driver is available/offline.

#### `GET /api/admin/settings` response / `POST /api/admin/settings` request body
```json
{
  "pricing": {
    "base_fare": 4.50,
    "per_km_rate": 2.10,
    "minimum_fare": 8.00,
    "stop_surcharge": 3.00
  },
  "flat_rates": {
    "Hamilton": 35.00,
    "Burlington": 55.00,
    "Oakville": 65.00,
    "Mississauga": 85.00,
    "Toronto": 120.00,
    "Pearson Airport": 140.00,
    "Billy Bishop Airport": 130.00
  },
  "surge": {
    "enabled": true,
    "tier1_pending_min": 3,
    "tier1_available_max": 2,
    "tier1_multiplier": 1.5,
    "tier2_pending_min": 5,
    "tier2_available_max": 1,
    "tier2_multiplier": 2.0
  },
  "promo_codes": [
    { "code": "FIRST10", "discount_pct": 10, "active": true },
    { "code": "CALEDONIA20", "discount_pct": 20, "active": true }
  ]
}
```
**Persistence:** Settings are stored in `backend/settings.json` (created on first save, loaded at startup). Hot-loaded on every settings GET — no restart required. `config.py` reads from `settings.json` if it exists, otherwise falls back to env vars.

---

## 8. Consistency Rules

- Every HTML template starts with `<link rel="stylesheet" href="/static/css/design-system.css">`
- Zero inline `style` attributes on layout elements (all via CSS classes)
- All status badges use same CSS classes: `.badge-green`, `.badge-amber`, `.badge-red`, `.badge-blue`, `.badge-grey`
- All forms use same CSS classes: `.form-group`, `.form-input`, `.form-label`, `.btn-primary`, `.btn-secondary`
- All modals/drawers use same JS pattern: `openDrawer(id)` / `closeDrawer(id)`
- All tabs use same JS pattern: `switchTab(name)`
- Error messages always appear in `.error-msg` elements with red text
- Loading states always show a `.spinner` element

---

## 9. Files Changed

### New Files
- `frontend/static/css/design-system.css` — shared design system
- `frontend/static/js/fare-engine.js` — client-side fare calculation module

### Modified Files
- `frontend/templates/booking.html` — full rebuild
- `frontend/templates/driver.html` — full rebuild
- `frontend/templates/admin.html` — full rebuild (new tabs)
- `backend/main.py` — new endpoints (stops, flat rates, OASR, driver locations, settings)
- `backend/config.py` — flat rates config, OASR settings
- `backend/services.py` — updated fare calculation (multi-leg, stops)

### Unchanged
- `backend/auth_service.py`
- `backend/scheduler.py`
- `backend/sms_service.py`
- `backend/invoice_service.py`
- All test files (updated as needed to match new endpoints)

### New files
- `backend/settings.json` — runtime-editable settings (created on first save)
- `backend/oasr_parser.py` — OASR email parser module

### models.py additions
- `BookingStatus`: add `needs_review`
- `BookingSource`: add `oasr`
- `BookingRequest`: add `service_type: str = "standard"`, `stops: List[str] = []`, `promo_code: Optional[str] = None`
- `Booking` dict: add `service_type`, `stops`, `fare_breakdown` (JSON), `oasr_source: bool = False`, `needs_review: bool = False`
- `Driver` dict: add `vehicle: str = ""`, `plate: str = ""`, `inactive: bool = False`

### database_schema.sql migration addendum
```sql
-- bookings table additions
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS service_type TEXT DEFAULT 'standard';
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS stops JSONB DEFAULT '[]';
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS fare_breakdown JSONB;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS oasr_source BOOLEAN DEFAULT FALSE;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS needs_review BOOLEAN DEFAULT FALSE;

-- drivers table additions
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS vehicle TEXT DEFAULT '';
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS plate TEXT DEFAULT '';
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS inactive BOOLEAN DEFAULT FALSE;

-- Update BookingStatus CHECK constraint to include new values
ALTER TABLE bookings DROP CONSTRAINT IF EXISTS bookings_status_check;
ALTER TABLE bookings ADD CONSTRAINT bookings_status_check
  CHECK (status IN ('pending','dispatched','accepted','in_progress','completed','cancelled','scheduled','dispatch_failed','needs_review'));

-- Update source CHECK constraint
ALTER TABLE bookings DROP CONSTRAINT IF EXISTS bookings_source_check;
ALTER TABLE bookings ADD CONSTRAINT bookings_source_check
  CHECK (source IN ('web','phone','admin','voice_ai','oasr'));
```

---

## 10. Out of Scope (this iteration)
- Mobile native app (PWA continues to serve mobile)
- Multi-tenant (multiple taxi companies)
- Customer accounts / login
- In-app chat between driver and customer
- Stripe full webhook reconciliation (existing PaymentIntent flow preserved)
