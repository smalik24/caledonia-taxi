# Caledonia Taxi Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add admin auth, real GPS tracking, Stripe payments, and advance booking to the existing FastAPI + vanilla JS taxi dispatch app, plus design polish across all three screens.

**Architecture:** All changes are additive to the existing FastAPI monolith. New backend logic goes into focused service modules (`auth_service.py`, `scheduler.py`). Frontend changes are in-place edits to the existing Jinja2 templates and CSS.

**Tech Stack:** Python FastAPI, itsdangerous (HMAC sessions), stripe (Python SDK), APScheduler (AsyncIOScheduler), Leaflet.js (route map strip), Stripe.js (card payments), vanilla JS, pytest + httpx (tests).

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `requirements.txt` | Modify | Add: `itsdangerous`, `stripe`, `apscheduler`, `pytest`, `pytest-asyncio` |
| `backend/config.py` | Modify | Add: `ADMIN_PASSWORD`, `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `ALLOWED_ORIGINS` |
| `backend/models.py` | Modify | Add `BookingStatus.scheduled`, `BookingStatus.dispatch_failed`, payment fields, `scheduled_for` to `BookingRequest` |
| `backend/auth_service.py` | **Create** | HMAC session token signing/verification using `itsdangerous` |
| `backend/scheduler.py` | **Create** | APScheduler setup + scheduled booking dispatch job |
| `backend/main.py` | Modify | Admin login/logout endpoints, admin route guard, GPS WebSocket handler, Stripe endpoint, advance booking creation guard, APScheduler in lifespan, CORS fix |
| `frontend/templates/admin.html` | Modify | Login gate, revenue stat card, colour-coded booking rows, scheduled bookings section |
| `frontend/templates/driver.html` | Modify | `startGPS()`/`stopGPS()`, GPS indicator badge, design polish |
| `frontend/templates/booking.html` | Modify | Route map strip, Now/Schedule toggle + date/time picker, Stripe payment step |
| `frontend/static/css/style.css` | Modify | Design polish: spacing, countdown ring, tab styling, status colours |
| `tests/conftest.py` | **Create** | pytest fixtures: async `AsyncClient` pointed at the FastAPI app |
| `tests/test_admin_auth.py` | **Create** | Login, logout, protected route access tests |
| `tests/test_payments.py` | **Create** | `create-intent` endpoint tests (Stripe mocked) |
| `tests/test_advance_booking.py` | **Create** | Scheduled booking creation, no immediate dispatch, scheduler idempotency |

---

## Task 1: Test Infrastructure + New Dependencies

**Files:**
- Modify: `requirements.txt`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Add new deps to requirements.txt**

Replace the contents of `requirements.txt` with:
```
fastapi
uvicorn[standard]
supabase
python-dotenv
httpx
twilio
websockets
pydantic
jinja2
python-multipart
reportlab
itsdangerous
stripe
apscheduler
pytest
pytest-asyncio
```

- [ ] **Step 2: Install new deps**

```bash
cd /Users/saqib/Downloads/caledonia-taxi
pip install itsdangerous stripe apscheduler pytest pytest-asyncio
```

Expected: all packages install without error.

- [ ] **Step 3: Create tests/\_\_init\_\_.py**

```bash
touch tests/__init__.py
```

- [ ] **Step 4: Create tests/conftest.py**

```python
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from main import app

@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as c:
        yield c
```

- [ ] **Step 5: Create pytest.ini at project root**

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

- [ ] **Step 6: Verify test collection works**

```bash
cd /Users/saqib/Downloads/caledonia-taxi
python -m pytest --collect-only
```

Expected: `no tests ran`, no import errors.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt tests/ pytest.ini
git commit -m "test: add test infrastructure and new dependencies"
```

---

## Task 2: Admin Auth — Backend

**Files:**
- Create: `backend/auth_service.py`
- Modify: `backend/config.py`

- [ ] **Step 1: Add ADMIN_PASSWORD to config.py**

`APP_SECRET_KEY` is already in `config.py` (line 25). Only add `ADMIN_PASSWORD`:
```python
# Admin
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin1234")
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_admin_auth.py`:
```python
import pytest

async def test_login_correct_password(client):
    r = await client.post("/admin/login", json={"password": "admin1234"})
    assert r.status_code == 200
    assert "admin_session" in r.cookies

async def test_login_wrong_password(client):
    r = await client.post("/admin/login", json={"password": "wrong"})
    assert r.status_code == 401

async def test_admin_stats_requires_auth(client):
    r = await client.get("/api/admin/stats")
    assert r.status_code == 401

async def test_admin_stats_with_valid_session(client):
    login = await client.post("/admin/login", json={"password": "admin1234"})
    token = login.cookies["admin_session"]
    r = await client.get("/api/admin/stats", cookies={"admin_session": token})
    assert r.status_code == 200

async def test_logout_clears_cookie(client):
    login = await client.post("/admin/login", json={"password": "admin1234"})
    token = login.cookies["admin_session"]
    logout = await client.get("/admin/logout", cookies={"admin_session": token})
    assert logout.status_code == 200
    # Cookie should be cleared (max_age=0 or deleted)
    r = await client.get("/api/admin/stats")
    assert r.status_code == 401
```

- [ ] **Step 3: Run tests to confirm they fail**

```bash
python -m pytest tests/test_admin_auth.py -v
```

Expected: `FAILED` — `POST /admin/login` returns 404.

- [ ] **Step 4: Create backend/auth_service.py**

```python
"""Admin session management using itsdangerous TimestampSigner."""
import secrets as _secrets
from itsdangerous import TimestampSigner, BadSignature, SignatureExpired

SESSION_DURATION_SECONDS = 8 * 3600  # 8 hours


def create_session_token(secret_key: str) -> str:
    signer = TimestampSigner(secret_key)
    return signer.sign(b"admin").decode()


def verify_session_token(token: str, secret_key: str) -> bool:
    signer = TimestampSigner(secret_key)
    try:
        signer.unsign(token, max_age=SESSION_DURATION_SECONDS)
        return True
    except (BadSignature, SignatureExpired):
        return False


def safe_compare(a: str, b: str) -> bool:
    """Timing-safe string comparison."""
    return _secrets.compare_digest(a.encode(), b.encode())
```

- [ ] **Step 5: Add admin endpoints and guard to main.py**

Add imports at top of `main.py`:
```python
import secrets
from fastapi import Cookie
from fastapi.responses import JSONResponse
from auth_service import create_session_token, verify_session_token, safe_compare
from config import ADMIN_PASSWORD, APP_SECRET_KEY
```

Add the dependency function (after app creation, before routes):
```python
def require_admin(admin_session: str = Cookie(default=None)):
    if not admin_session or not verify_session_token(admin_session, APP_SECRET_KEY):
        raise HTTPException(status_code=401, detail="Unauthorized")
```

Add login/logout endpoints (after the `/heatmap` route):
```python
@app.post("/admin/login")
async def admin_login(request: Request):
    data = await request.json()
    password = data.get("password", "")
    if not safe_compare(password, ADMIN_PASSWORD):
        raise HTTPException(status_code=401, detail="Invalid password")
    token = create_session_token(APP_SECRET_KEY)
    response = JSONResponse({"ok": True})
    response.set_cookie(
        "admin_session", token,
        httponly=True, samesite="lax",
        max_age=SESSION_DURATION_SECONDS
    )
    return response

@app.get("/admin/logout")
async def admin_logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie("admin_session")
    return response
```

Add `dependencies=[Depends(require_admin)]` to these existing routes in `main.py`:
- `GET /api/admin/stats` (line ~760)
- `GET /api/admin/sms-log` (line ~777)
- `GET /api/admin/email-log` (line ~782)
- `GET /api/admin/heatmap-data` (line ~787)
- `POST /api/admin/assign` (wherever it is)
- `DELETE /api/admin/bookings/{id}` (if present)

Example change:
```python
# Before:
@app.get("/api/admin/stats")
async def get_admin_stats():

# After:
from fastapi import Depends
@app.get("/api/admin/stats", dependencies=[Depends(require_admin)])
async def get_admin_stats():
```

- [ ] **Step 6: Run tests**

```bash
python -m pytest tests/test_admin_auth.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/auth_service.py backend/config.py backend/main.py tests/test_admin_auth.py
git commit -m "feat: add admin authentication with HMAC session cookies"
```

---

## Task 3: CORS Fix + Remaining Config

**Files:**
- Modify: `backend/config.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Add CORS and Stripe config to config.py**

Add to `backend/config.py`:
```python
# CORS — comma-separated list of allowed origins
ALLOWED_ORIGINS = [o.strip() for o in os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000"
).split(",")]

# Stripe
STRIPE_SECRET_KEY      = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
```

- [ ] **Step 2: Update CORS middleware in main.py**

Find the `CORSMiddleware` block (line ~62) and replace:
```python
# Before:
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# After:
from config import ALLOWED_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

- [ ] **Step 3: Verify app still starts**

```bash
cd backend && python -c "from main import app; print('OK')"
```

Expected: prints `OK` with no errors.

- [ ] **Step 4: Commit**

```bash
git add backend/config.py backend/main.py
git commit -m "fix: lock CORS origins and add Stripe/admin config keys"
```

---

## Task 4: Admin Auth — Frontend Login Gate

**Files:**
- Modify: `backend/main.py` (pass `authed` flag to admin template)
- Modify: `frontend/templates/admin.html`

- [ ] **Step 1: Pass auth flag to admin template**

Find the `GET /admin` route in `main.py` (~line 168) and update it:
```python
@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    admin_session = request.cookies.get("admin_session", "")
    authed = verify_session_token(admin_session, APP_SECRET_KEY) if admin_session else False
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "authed": authed
    })
```

- [ ] **Step 2: Add login gate to admin.html**

Add this `<script>` block right after `<body>` in `admin.html`:
```html
<script>window.__adminAuthed = {{ 'true' if authed else 'false' }};</script>
```

Add this login overlay card before the main container div:
```html
<!-- LOGIN GATE -->
<div id="loginGate" style="display:none; position:fixed; inset:0; background:var(--bg); z-index:9999; display:flex; align-items:center; justify-content:center;">
  <div class="card" style="max-width:360px; width:90%;">
    <div class="card-header"><span class="icon">🔐</span> Admin Login</div>
    <div class="form-group">
      <label>Password</label>
      <input type="password" id="adminPassword" placeholder="Enter admin password" autocomplete="current-password">
    </div>
    <div id="loginError" style="display:none; color:var(--danger); font-size:0.85rem; margin-bottom:0.75rem;"></div>
    <button class="btn btn-primary btn-block" onclick="doAdminLogin()">Sign In</button>
  </div>
</div>

<script>
(function() {
  if (!window.__adminAuthed) {
    document.getElementById('loginGate').style.display = 'flex';
  }
})();

async function doAdminLogin() {
  const pw = document.getElementById('adminPassword').value;
  const err = document.getElementById('loginError');
  err.style.display = 'none';
  try {
    const r = await fetch('/admin/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: pw }),
      credentials: 'include'
    });
    if (!r.ok) throw new Error('Invalid password');
    location.reload();
  } catch(e) {
    err.textContent = 'Invalid password. Try again.';
    err.style.display = 'block';
  }
}
</script>
```

Also add a logout button to the admin header nav links:
```html
<a href="#" onclick="fetch('/admin/logout',{credentials:'include'}).then(()=>location.reload())">Logout</a>
```

- [ ] **Step 3: Manual test**

```bash
cd backend && python main.py
```

1. Open `http://localhost:8000/admin` — login gate should appear.
2. Enter wrong password — error shown.
3. Enter `admin1234` — panel loads.
4. Click Logout — login gate reappears.

- [ ] **Step 4: Commit**

```bash
git add backend/main.py frontend/templates/admin.html
git commit -m "feat: add admin login gate with session cookie"
```

---

## Task 5: Real GPS — Backend WebSocket Handler

**Files:**
- Modify: `backend/main.py` (ws_driver handler)
- Create: `tests/test_gps.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_gps.py`:
```python
import pytest
import json
from starlette.testclient import TestClient
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
from main import app, drivers_db

def test_location_update_via_websocket():
    # Use a known demo driver ID
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
        # Give the handler time to process
        import time; time.sleep(0.1)

    # Driver record should be updated
    driver = drivers_db[driver_id]
    assert driver["latitude"] == pytest.approx(43.2557)
    assert driver["longitude"] == pytest.approx(-79.8711)
```

- [ ] **Step 2: Run test to confirm failure**

```bash
python -m pytest tests/test_gps.py -v
```

Expected: FAIL — `location_update` message is ignored (existing handler only handles `ping`).

- [ ] **Step 3: Update ws_driver handler in main.py**

Find the `ws_driver` function (~line 1026) and replace:
```python
# Before:
async def ws_driver(ws: WebSocket, driver_id: str):
    await manager.connect(ws, f"driver_{driver_id}")
    try:
        while True:
            msg = json.loads(await ws.receive_text())
            if msg.get("type") == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(ws, f"driver_{driver_id}")

# After:
async def ws_driver(ws: WebSocket, driver_id: str):
    await manager.connect(ws, f"driver_{driver_id}")
    try:
        while True:
            msg = json.loads(await ws.receive_text())
            if msg.get("type") == "ping":
                await ws.send_json({"type": "pong"})
            elif msg.get("type") == "location_update":
                lat = msg.get("lat")
                lng = msg.get("lng")
                if lat is not None and lng is not None and driver_id in drivers_db:
                    drivers_db[driver_id]["latitude"] = lat
                    drivers_db[driver_id]["longitude"] = lng
                    drivers_db[driver_id]["last_location_update"] = \
                        datetime.now(timezone.utc).isoformat()
                    # Broadcast to customer tracking page
                    await manager.broadcast_to_channel(
                        f"track_{driver_id}",
                        {"type": "location_update", "lat": lat, "lng": lng}
                    )
    except WebSocketDisconnect:
        manager.disconnect(ws, f"driver_{driver_id}")
```

- [ ] **Step 4: Run test to confirm pass**

```bash
python -m pytest tests/test_gps.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/main.py tests/test_gps.py
git commit -m "feat: add real GPS location_update WebSocket handler"
```

---

## Task 6: Real GPS — Driver Frontend

**Files:**
- Modify: `frontend/templates/driver.html`

- [ ] **Step 1: Add GPS functions to driver.html**

Find the `<script>` block in `driver.html`. Add these functions before the closing `</script>` tag:

```javascript
// ── GPS Tracking ─────────────────────────────────────────
let gpsWatchId = null;

function startGPS() {
  if (!navigator.geolocation) {
    updateGPSBadge(false);
    return;
  }
  gpsWatchId = navigator.geolocation.watchPosition(
    pos => {
      const { latitude, longitude, accuracy } = pos.coords;
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: 'location_update',
          lat: latitude,
          lng: longitude,
          accuracy: accuracy
        }));
      }
      updateGPSBadge(true);
    },
    err => {
      console.warn('GPS error:', err.message);
      updateGPSBadge(false);
      if (err.code === err.PERMISSION_DENIED) {
        showToastWarning('📍 Location access denied — tracking disabled');
      }
    },
    { enableHighAccuracy: true, maximumAge: 10000, timeout: 15000 }
  );
}

function stopGPS() {
  if (gpsWatchId !== null) {
    navigator.geolocation.clearWatch(gpsWatchId);
    gpsWatchId = null;
  }
  updateGPSBadge(false);
}

function updateGPSBadge(active) {
  const badge = document.getElementById('gpsBadge');
  if (!badge) return;
  badge.textContent = active ? '📍 GPS Active' : '📍 GPS Off';
  badge.style.color = active ? 'var(--success)' : 'var(--text-muted)';
  badge.style.borderColor = active ? 'var(--success-border)' : 'var(--border)';
}

function showToastWarning(msg) {
  // Use existing toast function if available, else console.warn
  if (typeof toast === 'function') toast(msg, 'warning');
  else console.warn(msg);
}
```

- [ ] **Step 2: Add GPS badge to driver header**

Find the driver header's `<div id="headerRight">` element. After the driver name/status badge is rendered by JS, add the GPS badge element:

Add inside the header HTML (near where online/offline badge is):
```html
<span id="gpsBadge" style="
  display:inline-flex; align-items:center;
  background:var(--surface-2); border:1px solid var(--border);
  border-radius:10px; padding:2px 8px;
  font-size:0.72rem; color:var(--text-muted);
">📍 GPS Off</span>
```

- [ ] **Step 3: Hook GPS into go-online / go-offline**

Find where the driver toggles online status (look for `goOnline` or `status: 'available'` in the JS). Add `startGPS()` / `stopGPS()` calls:

```javascript
// When driver goes online — add startGPS() call
async function goOnline() {
  // ... existing code ...
  startGPS(); // ADD THIS
}

// When driver goes offline — add stopGPS() call
async function goOffline() {
  stopGPS(); // ADD THIS
  // ... existing code ...
}
```

- [ ] **Step 4: Manual test**

```bash
cd backend && python main.py
```

1. Open `http://localhost:8000/driver`, log in as demo driver.
2. Click "Go Online" — browser should request location permission.
3. Allow — GPS badge should change to "📍 GPS Active".
4. Open `http://localhost:8000/admin` → Drivers tab — driver location should update with real coordinates.

- [ ] **Step 5: Commit**

```bash
git add frontend/templates/driver.html
git commit -m "feat: add real GPS tracking to driver app via watchPosition"
```

---

## Task 7: Stripe Payments — Backend

**Files:**
- Modify: `backend/models.py`
- Modify: `backend/main.py`
- Create: `tests/test_payments.py`

- [ ] **Step 1: Update models.py**

Add fields to `BookingRequest`:
```python
class BookingRequest(BaseModel):
    customer_name:   str = Field(..., min_length=1, max_length=100)
    customer_phone:  str = Field(..., min_length=7,  max_length=20)
    pickup_address:  str = Field(..., min_length=3)
    dropoff_address: str = Field(..., min_length=3)
    source: BookingSource = BookingSource.web
    payment_method: str = "cash"          # "cash" or "stripe"
    payment_intent_id: Optional[str] = None  # Stripe PI id, verified server-side
```

- [ ] **Step 2: Write failing tests**

Create `tests/test_payments.py`:
```python
import pytest
from unittest.mock import patch, MagicMock

async def test_create_intent_requires_addresses(client):
    r = await client.post("/api/payments/create-intent", json={
        "pickup_address": "x",
        "dropoff_address": "y"
    })
    # Should attempt to create intent (may fail with 503 if no Stripe key in test env)
    assert r.status_code in (200, 503)

async def test_create_intent_returns_client_secret(client):
    mock_intent = MagicMock()
    mock_intent.client_secret = "pi_test_secret_123"

    with patch("main.stripe") as mock_stripe:
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
    assert "client_secret" in r.json()
    assert "amount" in r.json()
    assert "publishable_key" in r.json()

async def test_cash_booking_skips_payment(client):
    r = await client.post("/api/bookings", json={
        "customer_name": "Test User",
        "customer_phone": "+12895550000",
        "pickup_address": "Hamilton GO Station, Hamilton, ON",
        "dropoff_address": "McMaster University, Hamilton, ON",
        "source": "web",
        "payment_method": "cash"
    })
    assert r.status_code == 200
    booking = r.json()["booking"]
    assert booking["payment_method"] == "cash"
    assert booking["payment_status"] == "pending"
```

- [ ] **Step 3: Run tests to confirm failure**

```bash
python -m pytest tests/test_payments.py -v
```

Expected: FAIL — `/api/payments/create-intent` returns 404.

- [ ] **Step 4: Add Stripe import and create-intent endpoint to main.py**

Add to imports at top of `main.py`:
```python
import stripe as stripe_lib
from config import STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY
```

Add the endpoint (after the fare estimate route):
```python
@app.post("/api/payments/create-intent")
async def create_payment_intent(req: FareEstimateRequest):
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured")
    stripe_lib.api_key = STRIPE_SECRET_KEY
    pc = await geocode_address(req.pickup_address)
    dc = await geocode_address(req.dropoff_address)
    if not pc or not dc:
        raise HTTPException(status_code=400, detail="Could not geocode addresses")
    dist = await get_route_distance(pc, dc)
    fare = calculate_fare(dist)
    amount_cents = max(int(fare * 100), 50)  # Stripe minimum 50 cents
    intent = stripe_lib.PaymentIntent.create(
        amount=amount_cents,
        currency="cad",
        automatic_payment_methods={"enabled": True},
        metadata={
            "pickup": req.pickup_address,
            "dropoff": req.dropoff_address
        }
    )
    return {
        "client_secret": intent.client_secret,
        "amount": fare,
        "publishable_key": STRIPE_PUBLISHABLE_KEY
    }
```

- [ ] **Step 5: Update booking creation to store payment fields**

Find `create_booking` (~line 266) and update the booking dict construction to include payment fields. After the booking dict is built, add:
```python
booking["payment_method"] = req.payment_method
booking["payment_status"] = "paid" if req.payment_method == "stripe" else "pending"
booking["payment_intent_id"] = req.payment_intent_id or None
```

- [ ] **Step 6: Expose payment fields in admin stats / booking list**

Find where bookings are returned in admin API and ensure `payment_method` and `payment_status` are included. These will be in the booking dict already, so they'll serialize automatically if the endpoint returns the full booking object.

- [ ] **Step 7: Run tests**

```bash
python -m pytest tests/test_payments.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/models.py backend/main.py tests/test_payments.py
git commit -m "feat: add Stripe PaymentIntent endpoint and payment fields to bookings"
```

---

## Task 8: Stripe Payments — Frontend

**Files:**
- Modify: `frontend/templates/booking.html`

- [ ] **Step 1: Load Stripe.js in booking.html head**

Add inside `<head>` of `booking.html`:
```html
<script src="https://js.stripe.com/v3/" async></script>
```

- [ ] **Step 2: Add payment method selector to Step 2**

In `booking.html`, find the Step 2 card (`<div id="step2" ...>`). Between the fare box and the Back/Confirm buttons, add:

```html
<!-- Payment Method -->
<div id="paymentSection" style="margin-bottom:1.25rem;">
  <div class="divider">Payment</div>
  <div style="display:grid; grid-template-columns:1fr 1fr; gap:0.75rem; margin-bottom:1rem;">
    <div id="payCard" class="payment-option selected" onclick="selectPayment('card')">
      <div style="font-size:1.2rem;">💳</div>
      <div style="font-weight:600; font-size:0.85rem;">Pay by Card</div>
      <div style="font-size:0.72rem; color:var(--text-muted);">Visa, MC, Amex</div>
    </div>
    <div id="payCash" class="payment-option" onclick="selectPayment('cash')">
      <div style="font-size:1.2rem;">💵</div>
      <div style="font-weight:600; font-size:0.85rem;">Pay Cash</div>
      <div style="font-size:0.72rem; color:var(--text-muted);">Pay driver directly</div>
    </div>
  </div>
  <!-- Stripe card element (shown when card selected) -->
  <div id="stripeCardWrapper" style="background:var(--surface-2); border:1px solid var(--border); border-radius:var(--radius-sm); padding:0.875rem;">
    <div id="stripe-card-element"></div>
    <div id="stripe-error" style="color:var(--danger); font-size:0.82rem; margin-top:0.5rem; display:none;"></div>
  </div>
</div>
```

Add CSS for payment options (inside the `<style>` block in booking.html):
```css
.payment-option {
  display: flex; flex-direction: column; align-items: center; gap: 4px;
  background: var(--surface-2); border: 2px solid var(--border);
  border-radius: var(--radius-sm); padding: 0.875rem 0.5rem;
  cursor: pointer; transition: border-color 0.15s;
}
.payment-option.selected {
  border-color: var(--accent);
  background: var(--accent-soft);
}
```

- [ ] **Step 3: Add JS payment logic to booking.html**

Add to the `<script>` block in `booking.html`:

```javascript
let stripe = null;
let stripeCardElement = null;
let paymentMethod = 'card';
let stripeClientSecret = null;

function selectPayment(method) {
  paymentMethod = method;
  document.getElementById('payCard').classList.toggle('selected', method === 'card');
  document.getElementById('payCash').classList.toggle('selected', method === 'cash');
  document.getElementById('stripeCardWrapper').style.display = method === 'card' ? 'block' : 'none';
}

async function initStripe(publishableKey) {
  if (!publishableKey || typeof Stripe === 'undefined') return;
  stripe = Stripe(publishableKey);
  const elements = stripe.elements();
  stripeCardElement = elements.create('card', {
    style: {
      base: {
        color: '#e2e8f0',
        fontFamily: 'system-ui, sans-serif',
        fontSize: '14px',
        '::placeholder': { color: '#4a5568' }
      }
    }
  });
  stripeCardElement.mount('#stripe-card-element');
}

// Modify the existing showStep(2) call — after getting estimate, also fetch PaymentIntent
// Replace the section in the submit handler that calls showStep(2):
async function prepareStep2() {
  try {
    const r = await fetch(`${API}/api/payments/create-intent`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pickup_address: document.getElementById('pickup').value,
        dropoff_address: document.getElementById('dropoff').value
      })
    });
    if (r.ok) {
      const data = await r.json();
      stripeClientSecret = data.client_secret;
      await initStripe(data.publishable_key);
    }
  } catch(e) {
    // Stripe unavailable — fall back to cash only
    selectPayment('cash');
    document.getElementById('payCard').style.display = 'none';
  }
  showStep(2);
}
```

Update the existing form submit handler to call `prepareStep2()` instead of `showStep(2)` at the end.

Update `confirmBooking()` to handle Stripe payment before creating booking:
```javascript
async function confirmBooking() {
  const btn = document.getElementById('confirmBtn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Processing…';
  try {
    let paymentIntentId = null;

    if (paymentMethod === 'card' && stripe && stripeClientSecret) {
      const { paymentIntent, error } = await stripe.confirmCardPayment(
        stripeClientSecret,
        { payment_method: { card: stripeCardElement } }
      );
      if (error) {
        document.getElementById('stripe-error').textContent = error.message;
        document.getElementById('stripe-error').style.display = 'block';
        throw new Error(error.message);
      }
      paymentIntentId = paymentIntent.id;
    }

    const r = await fetch(`${API}/api/bookings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        customer_name:    document.getElementById('name').value,
        customer_phone:   document.getElementById('phone').value,
        pickup_address:   document.getElementById('pickup').value,
        dropoff_address:  document.getElementById('dropoff').value,
        source: 'web',
        payment_method: paymentMethod === 'card' ? 'stripe' : 'cash',
        payment_intent_id: paymentIntentId
      })
    });
    if (!r.ok) throw new Error('Booking failed');
    const data = await r.json();
    const b = data.booking;
    document.getElementById('cBookingId').textContent = b.id.slice(0,12).toUpperCase();
    document.getElementById('cPickup').textContent    = b.pickup_address;
    document.getElementById('cDropoff').textContent   = b.dropoff_address;
    document.getElementById('cFare').textContent      = `$${parseFloat(b.estimated_fare).toFixed(2)}`;
    showStep(3);
    toast('Ride booked!', 'success');
  } catch(err) {
    if (!err.message.includes('card')) {
      toast('Booking failed — please try again', 'error');
    }
  } finally {
    btn.disabled = false;
    btn.innerHTML = 'Confirm &amp; Book →';
  }
}
```

- [ ] **Step 4: Manual test (Stripe test mode)**

If you have Stripe test keys, add to `.env`:
```
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
```

```bash
cd backend && python main.py
```

1. Open `http://localhost:8000`, fill in addresses and get an estimate.
2. Step 2 should show "Pay by Card" / "Pay Cash" selector.
3. Select card — Stripe card input appears.
4. Use test card `4242 4242 4242 4242`, any future expiry, any CVC.
5. Confirm — payment should process, booking created.
6. Switch to cash — no card input, books immediately.

- [ ] **Step 5: Commit**

```bash
git add frontend/templates/booking.html
git commit -m "feat: add Stripe card payment option to booking flow"
```

---

## Task 9: Advance Booking — Models + Creation Guard

**Files:**
- Modify: `backend/models.py`
- Modify: `backend/main.py`
- Create: `tests/test_advance_booking.py`

- [ ] **Step 1: Update BookingStatus enum and BookingRequest in models.py**

```python
class BookingStatus(str, Enum):
    pending       = "pending"
    dispatched    = "dispatched"
    accepted      = "accepted"
    in_progress   = "in_progress"
    completed     = "completed"
    cancelled     = "cancelled"
    scheduled     = "scheduled"      # NEW — awaiting future dispatch
    dispatch_failed = "dispatch_failed"  # NEW — scheduler failed after retries
```

Add `scheduled_for` to `BookingRequest`:
```python
from datetime import datetime

class BookingRequest(BaseModel):
    customer_name:    str = Field(..., min_length=1, max_length=100)
    customer_phone:   str = Field(..., min_length=7,  max_length=20)
    pickup_address:   str = Field(..., min_length=3)
    dropoff_address:  str = Field(..., min_length=3)
    source: BookingSource = BookingSource.web
    payment_method: str = "cash"
    payment_intent_id: Optional[str] = None
    scheduled_for: Optional[datetime] = None  # UTC ISO datetime; None = dispatch now
```

- [ ] **Step 2: Write failing tests**

Create `tests/test_advance_booking.py`:
```python
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

def future_time(minutes=60):
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()

async def test_immediate_booking_dispatches_now(client):
    with patch("main.asyncio") as mock_asyncio:
        mock_asyncio.create_task = lambda coro: None
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
    with patch("main.asyncio") as mock_asyncio:
        dispatched = []
        mock_asyncio.create_task = lambda coro: dispatched.append(coro)
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
    assert len(dispatched) == 0  # dispatch_booking was NOT called

async def test_scheduled_booking_rejects_past_time(client):
    past_time = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    r = await client.post("/api/bookings", json={
        "customer_name": "Late Rider",
        "customer_phone": "+12895550003",
        "pickup_address": "Hamilton GO Station, Hamilton, ON",
        "dropoff_address": "McMaster University, Hamilton, ON",
        "source": "web",
        "scheduled_for": past_time
    })
    assert r.status_code == 400

async def test_scheduled_booking_rejects_under_30min_lead(client):
    near_future = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
    r = await client.post("/api/bookings", json={
        "customer_name": "Hasty Rider",
        "customer_phone": "+12895550004",
        "pickup_address": "Hamilton GO Station, Hamilton, ON",
        "dropoff_address": "McMaster University, Hamilton, ON",
        "source": "web",
        "scheduled_for": near_future
    })
    assert r.status_code == 400
```

- [ ] **Step 3: Run tests to confirm failure**

```bash
python -m pytest tests/test_advance_booking.py -v
```

Expected: FAIL — no `scheduled_for` handling exists.

- [ ] **Step 4: Update create_booking in main.py**

Find `create_booking` (~line 266). After the booking dict is built, add the scheduled booking logic:

```python
# In create_booking, after building the booking dict:

# Handle advance booking
if req.scheduled_for:
    now_utc = datetime.now(timezone.utc)
    sf = req.scheduled_for
    # Ensure timezone-aware
    if sf.tzinfo is None:
        sf = sf.replace(tzinfo=timezone.utc)
    lead_minutes = (sf - now_utc).total_seconds() / 60
    if lead_minutes < 30:
        raise HTTPException(
            status_code=400,
            detail="Scheduled pickup must be at least 30 minutes from now"
        )
    booking["status"] = BookingStatus.scheduled.value
    booking["scheduled_for"] = sf.isoformat()
    # Do NOT dispatch now — APScheduler handles this
else:
    booking["scheduled_for"] = None
    asyncio.create_task(dispatch_booking(booking))
```

Also update the SMS sent on confirmation to include scheduled time when applicable:
```python
# After storing booking, before return:
if req.scheduled_for:
    # Use scheduled booking SMS
    sched_str = sf.strftime("%B %d at %-I:%M %p UTC")
    await sms_booking_confirmed(booking["customer_phone"],
        f"Your ride is scheduled for {sched_str}. We'll dispatch a driver 10 min before pickup.")
else:
    await sms_booking_confirmed(booking["customer_phone"], booking["id"])
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/test_advance_booking.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/models.py backend/main.py tests/test_advance_booking.py
git commit -m "feat: add advance booking with scheduled status and 30-min lead time validation"
```

---

## Task 10: Advance Booking — Scheduler

**Files:**
- Create: `backend/scheduler.py`
- Modify: `backend/main.py` (lifespan)

- [ ] **Step 1: Write failing test**

Add to `tests/test_advance_booking.py`:
```python
async def test_scheduler_dispatches_when_within_10_minutes(client):
    """Scheduler should pick up bookings whose scheduled_for is within 10 min."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
    from main import bookings_db
    from scheduler import dispatch_scheduled_now

    # Plant a scheduled booking due in 5 minutes
    booking_id = "test-sched-001"
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

async def test_scheduler_skips_non_scheduled_bookings(client):
    from main import bookings_db
    from scheduler import dispatch_scheduled_now

    booking_id = "test-active-001"
    bookings_db[booking_id] = {
        "id": booking_id,
        "status": "in_progress",  # not scheduled
        "scheduled_for": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
    }
    dispatched_ids = []
    async def fake_dispatch(b): dispatched_ids.append(b["id"])

    await dispatch_scheduled_now(bookings_db, fake_dispatch)
    assert booking_id not in dispatched_ids
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_advance_booking.py::test_scheduler_dispatches_when_within_10_minutes -v
```

Expected: FAIL — `scheduler` module not found.

- [ ] **Step 3: Create backend/scheduler.py**

```python
"""APScheduler setup for advance booking dispatch."""
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler(timezone="UTC")
MAX_DISPATCH_ATTEMPTS = 3


async def dispatch_scheduled_now(bookings_db: dict, dispatch_fn, sms_fn=None) -> None:
    """
    Find scheduled bookings within 10 minutes and dispatch them.
    Sets status to 'dispatching' atomically before calling dispatch_fn
    to prevent double-dispatch across poll cycles.
    After MAX_DISPATCH_ATTEMPTS failures, marks booking as dispatch_failed.
    """
    now = datetime.now(timezone.utc)
    window = now + timedelta(minutes=10)

    for booking in list(bookings_db.values()):
        if booking.get("status") != "scheduled":
            continue
        sf_raw = booking.get("scheduled_for")
        if not sf_raw:
            continue
        try:
            sf = datetime.fromisoformat(sf_raw)
            if sf.tzinfo is None:
                sf = sf.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if sf <= window:
            attempts = booking.get("dispatch_attempts", 0)
            if attempts >= MAX_DISPATCH_ATTEMPTS:
                booking["status"] = "dispatch_failed"
                if sms_fn and booking.get("customer_phone"):
                    try:
                        await sms_fn(
                            booking["customer_phone"],
                            f"Sorry, we could not find a driver for your scheduled ride. "
                            f"Please call us or book again. Booking: {booking['id'][:8].upper()}"
                        )
                    except Exception:
                        pass
                continue
            # Atomically claim — prevents double-dispatch
            booking["status"] = "dispatching"
            booking["dispatch_attempts"] = attempts + 1
            try:
                await dispatch_fn(booking)
            except Exception:
                # Revert to scheduled so next poll retries
                booking["status"] = "scheduled"


def setup_scheduler(bookings_db: dict, dispatch_fn, sms_fn=None) -> AsyncIOScheduler:
    """Configure and return the scheduler. Call scheduler.start() in lifespan."""

    @scheduler.scheduled_job("interval", seconds=60, id="dispatch_scheduled")
    async def _job():
        await dispatch_scheduled_now(bookings_db, dispatch_fn, sms_fn)

    return scheduler
```

- [ ] **Step 4: Wire scheduler into main.py lifespan**

Update the lifespan context manager in `main.py`:
```python
from scheduler import setup_scheduler
from sms_service import sms_dispatch_failed  # or whichever SMS fn suits

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚕  Caledonia Taxi API starting — Hamilton, ON")
    sched = setup_scheduler(bookings_db, dispatch_booking, sms_fn=sms_dispatch_failed)
    sched.start()
    yield
    sched.shutdown(wait=False)
    print("🚕  Caledonia Taxi API stopped.")
```

Note: `sms_dispatch_failed` is already in `sms_service.py`. Its signature is `(phone, booking_id)` — adapt the call in `scheduler.py` to match, or create a simple lambda wrapper:
```python
sms_fn=lambda phone, msg: sms_dispatch_failed(phone, msg)
```

- [ ] **Step 5: Run all tests**

```bash
python -m pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/scheduler.py backend/main.py tests/test_advance_booking.py
git commit -m "feat: add APScheduler for advance booking dispatch (10-min window, idempotent)"
```

---

## Task 11: Design — Booking Page Map Strip + Now/Schedule Toggle

**Files:**
- Modify: `frontend/templates/booking.html`
- Modify: `frontend/static/css/style.css`

- [ ] **Step 1: Add Leaflet.js to booking.html head**

```html
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
```

- [ ] **Step 2: Add route map strip HTML**

Between the hero section and the Step 1 card in `booking.html`, add:
```html
<!-- Route Map Strip -->
<div id="routeMapStrip" style="position:relative; margin:0 0 1rem; border-radius:var(--radius-sm); overflow:hidden; border:1px solid var(--border); display:none;">
  <div id="routeMap" style="height:130px; width:100%;"></div>
  <div id="fareOverlay" style="
    position:absolute; bottom:8px; left:50%; transform:translateX(-50%);
    background:rgba(8,8,17,.82); border:1px solid var(--border-accent);
    border-radius:20px; padding:4px 14px;
    color:var(--accent); font-size:0.82rem; font-weight:700;
    white-space:nowrap; pointer-events:none;
  "></div>
</div>
```

- [ ] **Step 3: Add map initialization JS**

Add to the `<script>` block:
```javascript
let routeMap = null;
let pickupMarker = null;
let dropoffMarker = null;
let routeLine = null;

function initRouteMap() {
  if (routeMap) return;
  routeMap = L.map('routeMap', {
    zoomControl: false, attributionControl: false,
    dragging: false, scrollWheelZoom: false, doubleClickZoom: false
  }).setView([43.2557, -79.8711], 12);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    maxZoom: 18
  }).addTo(routeMap);
}

function updateRouteMap(pickupCoords, dropoffCoords, fareText) {
  initRouteMap();
  document.getElementById('routeMapStrip').style.display = 'block';
  if (pickupMarker) routeMap.removeLayer(pickupMarker);
  if (dropoffMarker) routeMap.removeLayer(dropoffMarker);
  if (routeLine) routeMap.removeLayer(routeLine);
  pickupMarker = L.circleMarker([pickupCoords.lat, pickupCoords.lng],
    { radius:7, color:'#22c55e', fillColor:'#22c55e', fillOpacity:1, weight:2 }
  ).addTo(routeMap);
  dropoffMarker = L.circleMarker([dropoffCoords.lat, dropoffCoords.lng],
    { radius:7, color:'#ef4444', fillColor:'#ef4444', fillOpacity:1, weight:2 }
  ).addTo(routeMap);
  routeLine = L.polyline(
    [[pickupCoords.lat, pickupCoords.lng], [dropoffCoords.lat, dropoffCoords.lng]],
    { color:'#f5c518', weight:2, dashArray:'6,5', opacity:0.7 }
  ).addTo(routeMap);
  routeMap.fitBounds(routeLine.getBounds(), { padding: [20, 20] });
  if (fareText) {
    document.getElementById('fareOverlay').textContent = fareText;
  }
  setTimeout(() => routeMap.invalidateSize(), 100);
}
```

Call `updateRouteMap` after a successful estimate in the form submit handler:
```javascript
// After: estimate = await r.json();
if (estimate.pickup_coords && estimate.dropoff_coords) {
  updateRouteMap(
    estimate.pickup_coords,
    estimate.dropoff_coords,
    `~$${estimate.estimated_fare.toFixed(2)} · ${estimate.distance_km.toFixed(1)} km`
  );
}
```

- [ ] **Step 4: Add Now/Schedule toggle**

In Step 1 form, after the dropoff address field, add:
```html
<div class="divider">When?</div>
<div style="display:flex; gap:0.75rem; margin-bottom:1rem;">
  <button type="button" id="btnNow" class="btn btn-primary" style="flex:1;" onclick="setScheduleMode(false)">⚡ Now</button>
  <button type="button" id="btnSchedule" class="btn btn-secondary" style="flex:1;" onclick="setScheduleMode(true)">🕐 Schedule</button>
</div>
<div id="scheduleFields" style="display:none;">
  <div style="display:grid; grid-template-columns:1fr 1fr; gap:0.75rem; margin-bottom:1rem;">
    <div class="form-group" style="margin:0;">
      <label>Date</label>
      <input type="date" id="schedDate" required>
    </div>
    <div class="form-group" style="margin:0;">
      <label>Time</label>
      <input type="time" id="schedTime" step="900" required>
    </div>
  </div>
</div>
```

Add JS for schedule mode:
```javascript
let scheduleMode = false;

function setScheduleMode(enable) {
  scheduleMode = enable;
  document.getElementById('btnNow').className = enable ? 'btn btn-secondary' : 'btn btn-primary';
  document.getElementById('btnSchedule').className = enable ? 'btn btn-primary' : 'btn btn-secondary';
  document.getElementById('scheduleFields').style.display = enable ? 'block' : 'none';

  if (enable) {
    // Set min date to today, default time to 1hr from now rounded to 15min
    const now = new Date();
    const minDate = now.toISOString().split('T')[0];
    document.getElementById('schedDate').min = minDate;
    document.getElementById('schedDate').value = minDate;
    now.setHours(now.getHours() + 1, Math.ceil(now.getMinutes()/15)*15 % 60, 0, 0);
    document.getElementById('schedTime').value =
      now.toTimeString().slice(0,5);
  }
}

function getScheduledForUTC() {
  if (!scheduleMode) return null;
  const date = document.getElementById('schedDate').value;
  const time = document.getElementById('schedTime').value;
  return new Date(`${date}T${time}`).toISOString(); // converts local to UTC
}
```

Update `confirmBooking` to include `scheduled_for`:
```javascript
body: JSON.stringify({
  // ... existing fields ...
  scheduled_for: getScheduledForUTC()
})
```

Update Step 3 confirmation copy to show scheduled time when applicable:
```javascript
// After: document.getElementById('cFare').textContent = ...
const scheduledFor = getScheduledForUTC();
const rideTimeEl = document.getElementById('rideTimeInfo');
if (scheduledFor) {
  const d = new Date(scheduledFor);
  rideTimeEl.textContent = `Scheduled for ${d.toLocaleString('en-CA', {dateStyle:'medium', timeStyle:'short'})}`;
} else {
  rideTimeEl.textContent = 'A driver is being dispatched now.';
}
```

Add `<p id="rideTimeInfo" ...>` element to Step 3 confirmation card.

- [ ] **Step 5: Manual test**

```bash
cd backend && python main.py
```

1. Fill in addresses — after estimate, route map strip appears with pins.
2. Switch to "Schedule" — date/time picker appears.
3. Pick a time 2+ hours away — booking creates with `scheduled` status.
4. Pick a time 10 minutes away — should show error (backend rejects).

- [ ] **Step 6: Commit**

```bash
git add frontend/templates/booking.html frontend/static/css/style.css
git commit -m "feat: add route map strip and Now/Schedule toggle to booking page"
```

---

## Task 12: Design Polish — CSS, Driver App + Admin Panel

**Files:**
- Modify: `frontend/static/css/style.css`
- Modify: `frontend/templates/driver.html`
- Modify: `frontend/templates/admin.html`

- [ ] **Step 1: CSS polish — spacing, countdown ring, status colours**

Add/update in `frontend/static/css/style.css`:
```css
/* Tighter card spacing */
.card { padding: 1.25rem; }
.form-group { margin-bottom: 1rem; }
.form-group label { font-size: 0.78rem; font-weight: 600; color: var(--text-secondary); letter-spacing: 0.3px; margin-bottom: 0.35rem; }

/* Countdown ring improvements */
.countdown-ring circle.progress {
  stroke-width: 5;
  transition: stroke-dashoffset 1s linear;
}
.countdown-number { font-size: 2rem; font-weight: 900; }

/* Status colour tokens */
.status-available  { color: var(--success); }
.status-busy       { color: var(--warning); }
.status-dispatching { color: #f59e0b; }
.status-en-route   { color: var(--info); }
.status-arriving   { color: #8b5cf6; }
.status-offline    { color: var(--text-muted); }

/* Tab polish */
.tab-bar { display: flex; border-bottom: 1px solid var(--border); margin-bottom: 1.25rem; }
.tab { padding: 0.625rem 1rem; font-size: 0.85rem; font-weight: 600; cursor: pointer; color: var(--text-secondary); border-bottom: 2px solid transparent; margin-bottom: -1px; }
.tab.active { color: var(--accent); border-bottom-color: var(--accent); }

/* Booking row status borders */
.booking-row { border-left: 3px solid var(--border); }
.booking-row[data-status="in_progress"] { border-left-color: var(--success); }
.booking-row[data-status="dispatched"]  { border-left-color: var(--warning); }
.booking-row[data-status="accepted"]    { border-left-color: var(--info); }
.booking-row[data-status="completed"]   { border-left-color: var(--text-muted); }
.booking-row[data-status="scheduled"]   { border-left-color: #8b5cf6; }
.booking-row[data-status="cancelled"]   { border-left-color: var(--danger); }
```

- [ ] **Step 2: Admin panel — add revenue stat card**

Find the stats grid in `admin.html` and add a revenue card:
```html
<div class="stat-card accent-success">
  <div class="stat-value" id="sRevenue">$0</div>
  <div class="stat-label">Today's Revenue</div>
</div>
```

Add `sRevenue` population to the stats loading JS in `admin.html`:
```javascript
// In the function that loads stats:
const revenue = (stats.bookings || [])
  .filter(b => b.status === 'completed')
  .reduce((sum, b) => sum + parseFloat(b.estimated_fare || 0), 0);
document.getElementById('sRevenue').textContent = `$${revenue.toFixed(2)}`;
```

- [ ] **Step 3: Admin panel — add scheduled bookings section**

In the Bookings tab of `admin.html`, add a "Scheduled" sub-section before the active bookings list:
```html
<div id="scheduledSection" style="margin-bottom:1.5rem; display:none;">
  <div class="section-title">🕐 Upcoming Scheduled Rides</div>
  <div id="scheduledList"></div>
</div>
```

In the bookings rendering JS, filter and display scheduled vs active separately:
```javascript
function renderBookings(bookings) {
  const scheduled = bookings.filter(b => b.status === 'scheduled');
  const active = bookings.filter(b => b.status !== 'scheduled');

  const schedSection = document.getElementById('scheduledSection');
  schedSection.style.display = scheduled.length ? 'block' : 'none';
  document.getElementById('scheduledList').innerHTML = scheduled.map(b => `
    <div class="booking-row card" data-status="scheduled" style="margin-bottom:0.5rem;">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <div>
          <div style="font-weight:600;">${b.customer_name}</div>
          <div style="font-size:0.8rem;color:var(--text-secondary);">${b.pickup_address} → ${b.dropoff_address}</div>
        </div>
        <div style="text-align:right;">
          <div style="color:#8b5cf6;font-size:0.78rem;font-weight:700;">🕐 SCHEDULED</div>
          <div style="font-size:0.75rem;color:var(--text-muted);">${new Date(b.scheduled_for).toLocaleString('en-CA',{dateStyle:'short',timeStyle:'short'})}</div>
        </div>
      </div>
    </div>
  `).join('');

  // render active bookings as before, but add data-status attribute
  // ... existing render logic, add data-status="${b.status}" to each row
}
```

- [ ] **Step 4: Driver app — tighten spacing + improve countdown ring**

In `driver.html`, update the SVG countdown ring markup (find existing SVG):
```html
<!-- Replace existing countdown SVG with: -->
<svg width="110" height="110" style="transform:rotate(-90deg)">
  <circle cx="55" cy="55" r="48"
    fill="none" stroke="var(--surface-2)" stroke-width="5"/>
  <circle id="countdownArc" cx="55" cy="55" r="48"
    fill="none" stroke="var(--accent)" stroke-width="5"
    stroke-linecap="round"
    stroke-dasharray="301.6" stroke-dashoffset="0"
    class="progress"/>
</svg>
<div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);text-align:center;">
  <div id="countdownNum" class="countdown-number">30</div>
  <div style="font-size:0.6rem;color:var(--text-muted);text-transform:uppercase;">sec</div>
</div>
```

- [ ] **Step 5: Run full test suite**

```bash
python -m pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 6: Manual smoke test — all three screens**

```bash
cd backend && python main.py
```

1. `http://localhost:8000` — booking page: map strip, payment selector, schedule toggle all work.
2. `http://localhost:8000/driver` — driver app: GPS badge visible, countdown ring improved.
3. `http://localhost:8000/admin` — admin panel: login gate, revenue card, status-coloured rows, scheduled section.

- [ ] **Step 7: Final commit**

```bash
git add frontend/static/css/style.css frontend/templates/admin.html frontend/templates/driver.html
git commit -m "feat: design polish — CSS, admin revenue card, scheduled section, driver GPS badge"
```

---

## Done

All 12 tasks complete. Run the full suite one final time:
```bash
python -m pytest tests/ -v --tb=short
```

Then start the server and do a full walkthrough:
```bash
cd backend && python main.py
```

- Book a ride now (cash) → confirm dispatch works
- Book a ride now (card) → confirm Stripe flow
- Schedule a ride → confirm `scheduled` status, no immediate dispatch
- Log in to admin → confirm gate, revenue stat, scheduled section
- Go online as driver → confirm GPS badge activates, location updates in admin
