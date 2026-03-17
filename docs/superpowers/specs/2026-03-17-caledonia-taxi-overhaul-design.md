# Caledonia Taxi — Full Overhaul Design Spec
**Date:** 2026-03-17
**Approach:** Enhance in place (FastAPI + vanilla JS, no rewrite)
**Scope:** Design polish across all 3 screens + 4 new features

---

## 1. Overview

A full overhaul of Caledonia Taxi v2.0 covering design improvements to all three screens (booking, driver, admin) and four new features: admin authentication, real GPS tracking, Stripe payments, and advance booking.

The existing FastAPI backend and vanilla JS frontend are retained. No framework migration. New dependencies: Stripe Python SDK, APScheduler, itsdangerous.

**Required config change:** `main.py` currently sets `allow_origins=["*"]` on CORS. Cookie-based auth requires a locked origin. Before deploying admin auth, `allow_origins` must be set to the actual deployment domain(s) and `allow_credentials=True` confirmed.

---

## 2. Design Changes

### 2.1 Customer Booking Page (`/`)

**Current:** 3-step form (Details → Fare → Confirmed). Dark theme. No map.

**Changes:**
- Add a **route map strip** between the page header and form (Step 1). A Leaflet.js panel ~120px tall renders pickup/dropoff pins connected by a dashed route line once both addresses are geocoded. Falls back gracefully if ORS key is absent.
- **Inline fare estimate** displayed in the map strip once the route is known (e.g. "~$14.50 · 6.2 km").
- **Now / Schedule toggle** added to Step 1 below the address fields. Default is "Now". Selecting "Schedule" reveals a date + time picker (see Feature: Advance Booking).
- Tighter form layout: reduce vertical padding, improve label sizing, consistent input heights.
- Step 2 (fare confirmation) retains its current structure but gains a cleaner breakdown row and a "Pay by card" option (see Feature: Stripe Payments).

### 2.2 Driver App (`/driver`)

**Current:** Login screen + online/offline toggle + countdown ring + earnings bar + ride action cards.

**Changes:**
- Tighten card spacing and padding for better mobile feel.
- Improve the SVG countdown ring: thicker stroke, smoother animation, clearer number rendering.
- Better status colour coding: green (available), amber (dispatching), blue (en route), red (offline).
- Add a **GPS indicator badge** in the driver header showing "📍 GPS Active" / "📍 GPS Off" reflecting whether geolocation is running (see Feature: Real GPS).
- No structural layout changes — same card-based flow.

### 2.3 Admin Panel (`/admin`)

**Current:** Stats grid + 4 tabs (Bookings / Drivers / SMS / Email) + Activity feed. No auth.

**Changes:**
- Add a **revenue stat card** to the stats grid (today's total completed fare revenue).
- Improve booking row cards: left-border accent colour per status (green = en route, amber = dispatching, blue = arriving, grey = completed).
- Cleaner tab styling: active tab has accent underline, not background fill.
- Add a **login gate** (see Feature: Admin Auth) — renders before the panel content.
- Minor: wider container on desktop (`max-width: 1200px`), activity feed height increased.

---

## 3. New Features

### 3.1 Admin Authentication

**Problem:** `/admin` is publicly accessible with no credentials required.

**Design:**
- A PIN/password login screen is shown at `/admin` when no valid session exists.
- On successful login, the server sets an `HttpOnly` session cookie (`admin_session`) with a signed token (HMAC-SHA256 of a secret + timestamp). Expiry: 8 hours.
- All `/admin` HTML route and all `/api/admin/*` endpoints check for a valid cookie. Invalid → redirect to login or 401.
- Admin password stored as an env var (`ADMIN_PASSWORD`). Default for dev: `admin1234`.
- Password comparison uses `secrets.compare_digest(submitted, ADMIN_PASSWORD)` to prevent timing attacks.
- No multi-user support needed at MVP — single shared password.
- Logout button in admin header clears the cookie.

**Backend changes:** `main.py` — add `POST /admin/login`, `GET /admin/logout`, middleware/dependency to validate `admin_session` cookie on admin routes.

**Frontend changes:** `admin.html` — login card shown when `window.__adminAuthed` is false (set by template); redirects after successful login.

### 3.2 Real GPS Tracking

**Problem:** Driver location on the customer tracking map (`/track/{id}`) uses simulated coordinates. The admin heatmap also uses mock data.

**Design:**
- When a driver goes online, the driver app calls `navigator.geolocation.watchPosition()` with `enableHighAccuracy: true`.
- On each position update, the driver sends a WebSocket message: `{ type: "location_update", lat, lng, accuracy }`.
- The backend updates the in-memory driver record's `lat`/`lng` fields (already present) with the real coordinates.
- The existing `/track/{id}` page already connects via WebSocket and moves the map marker — no structural change needed, just real data flowing through.
- If geolocation is denied or unavailable, driver app shows a dismissable warning banner and falls back gracefully (no location sent).
- GPS indicator badge in driver header reflects current state.

**Backend changes:** `main.py` WebSocket handler — accept and process `location_update` message type (update driver record, broadcast to any tracking subscribers).

**Frontend changes:** `driver.html` — add `startGPS()` / `stopGPS()` called on go-online / go-offline. Send location messages via existing WebSocket connection.

### 3.3 Stripe Payments

**Problem:** No online payment option — cash only.

**Design:**
- Between Step 2 (fare estimate) and the "Confirm & Book" action, a **payment method selector** is shown:
  - "Pay by card" (Stripe) — default option
  - "Pay cash" — always available
- Selecting "Pay by card" renders a **Stripe Elements** card input inline (card number, expiry, CVC).
- On "Confirm & Book":
  - Frontend calls `POST /api/payments/create-intent` with pickup/dropoff addresses. The server calculates the fare server-side and creates the PaymentIntent for that amount. Client-supplied fare values are never trusted.
  - Frontend confirms the payment using `stripe.confirmCardPayment(clientSecret)`.
  - On payment success, the booking is created as normal with `payment_method: "stripe"` and `payment_status: "paid"`.
  - On payment failure, error is shown inline — booking is not created.
- Cash bookings bypass payment entirely — booking created immediately as before with `payment_method: "cash"`, `payment_status: "pending"`.
- Admin panel shows payment method and status on each booking row.
- Stripe keys stored in env: `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`.

**Backend changes:** `main.py` — add `POST /api/payments/create-intent` endpoint. `models.py` — add `payment_method` and `payment_status` fields to `BookingRequest` / booking record.

**Frontend changes:** `booking.html` — add Step 2.5 payment selector, load Stripe.js, handle PaymentIntent confirmation flow.

### 3.4 Advance Booking

**Problem:** Customers can only book "now" — no way to schedule a future pickup.

**Design:**
- A **Now / Schedule** toggle is added to the booking form (Step 1), below the address fields.
- "Now" is the default — behaviour unchanged.
- "Schedule" reveals a date picker + time picker. Allowed range: today up to 7 days ahead. Time in 15-minute increments. Minimum lead time: 30 minutes from now.
- Scheduled bookings are created with `status: "scheduled"` and a `scheduled_for` ISO timestamp (UTC) field. `"scheduled"` is added to the `BookingStatus` enum in `models.py`.
- Booking creation does **not** call `dispatch_booking()` when `scheduled_for` is set. APScheduler is the sole dispatcher for scheduled bookings.
- APScheduler polls every minute for bookings with `status == "scheduled"` whose `scheduled_for` is within 10 minutes. The **first action** of dispatch is atomically setting status to `"dispatching"`, so subsequent polls skip already-dispatched bookings.
- The customer confirmation screen (Step 3) shows the scheduled time instead of "Driver dispatching now".
- Admin panel: scheduled bookings appear in a separate "Scheduled" tab or section with the pickup time shown.
- SMS sent at booking creation: "Your ride is scheduled for [time]. We'll dispatch a driver 10 minutes before your pickup."

**Timezone:** `scheduled_for` is stored as UTC. The frontend converts the user's local time to UTC before submission using `new Date(localDateTimeString).toISOString()`. Lead time validation (30-minute minimum) is performed server-side against UTC now.

**Backend changes:** `main.py` — add APScheduler job, update booking creation to handle `scheduled_for`, guard immediate dispatch. `models.py` — add `scheduled_for: Optional[datetime]` to `BookingRequest`, add `scheduled` to `BookingStatus` enum.

**Frontend changes:** `booking.html` — Now/Schedule toggle, conditional date+time picker, updated Step 3 confirmation copy.

---

## 4. Architecture

No structural changes. All additions fit within the existing FastAPI monolith.

```
FastAPI (main.py)
├── HTML routes: /, /driver, /admin, /heatmap, /track/{id}
├── API routes: /api/bookings, /api/estimate-fare, /api/drivers/*, /api/admin/*
├── NEW: /admin/login, /admin/logout
├── NEW: /api/payments/create-intent
├── WebSocket: /ws/driver/{id}, /ws/track/{id}
├── APScheduler (lifespan): scheduled booking dispatcher (every 60s)
└── Services: geocoding, routing, fare calc, dispatch, SMS, invoice
```

New dependencies:
- `stripe` — Python Stripe SDK
- `apscheduler` — scheduled job runner
- `itsdangerous` — HMAC session token signing (or use PyJWT)

---

## 5. Data Model Changes

| Field | Source | Type | Notes |
|-------|--------|------|-------|
| `payment_method` | Client (`BookingRequest`) | `str` | `"cash"` or `"stripe"` — comes from payment selector |
| `payment_status` | Server only | `str` | `"pending"`, `"paid"`, `"failed"` — never trusted from client |
| `payment_intent_id` | Server only | `Optional[str]` | Set after PaymentIntent created — never trusted from client |
| `scheduled_for` | Client (`BookingRequest`) | `Optional[datetime]` | UTC ISO string from form; `None` = immediate dispatch |
| `BookingStatus.scheduled` | N/A | enum value | New status added to `BookingStatus` enum in `models.py` |

Driver model already has `lat`/`lng` fields — no changes needed.

---

## 6. Error Handling

- **GPS denied:** Driver app shows inline warning, GPS badge shows "Off", app remains fully functional without location.
- **Stripe failure:** Error shown inline in Step 2.5, booking not created, user can retry or switch to cash.
- **APScheduler dispatch failure:** Booking remains `scheduled`, retried on next poll cycle. After 3 failures, status set to `dispatch_failed`, SMS sent to customer.
- **Admin cookie expired:** Redirect to `/admin` login screen, no data leaked.

---

## 7. Out of Scope

- Customer accounts / ride history
- Driver earnings history persistence (beyond session)
- Rating system
- Push notifications
- Multi-admin roles
- Mobile app (PWA enhancements deferred)
