# Caledonia Taxi Full Platform Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild all three frontend apps (booking, driver, admin) with a consistent Uber Noir design system, add multi-stop fare calculation, long-distance flat rates, OASR medical booking automation, live driver tracking map, and admin settings management.

**Architecture:** FastAPI monolith backend with Jinja2 templates + vanilla JS frontend. Shared CSS design system loaded by all templates. New backend modules for OASR parsing and runtime settings. All fare calculation logic lives in `services.py` (authoritative) with a matching `fare-engine.js` client-side module for display.

**Tech Stack:** FastAPI, Python 3.11+, Jinja2, vanilla JS (no framework), Leaflet.js, Stripe.js, SheetJS, pywebpush, APScheduler. All dependencies already in requirements.txt.

**Spec:** `/Users/saqib/Downloads/caledonia-taxi/docs/superpowers/specs/2026-03-18-full-platform-redesign.md`

---

## File Map

### New Files
| File | Responsibility |
|------|---------------|
| `frontend/static/css/design-system.css` | All CSS variables, base components, shared UI classes |
| `frontend/static/js/fare-engine.js` | Client-side fare calculation (matches services.py formula exactly) |
| `backend/oasr_parser.py` | OASR email text parser — extracts booking fields from raw email |
| `backend/settings.json` | Runtime-editable pricing, flat rates, surge, promo settings (created on first save) |

### Modified Files
| File | What Changes |
|------|-------------|
| `backend/models.py` | Add BookingStatus.needs_review, BookingSource.oasr, service_type/stops/fare_breakdown fields |
| `backend/config.py` | Load settings.json if present; expose flat_rates, stop_surcharge, settings hot-load |
| `backend/services.py` | Multi-leg fare calculation, flat rate lookup, stop surcharge, matches fare-engine.js contract |
| `backend/main.py` | 12 new endpoints: stops, flat-rates, OASR, driver CRUD, driver-locations, settings, updated estimate-fare |
| `frontend/templates/booking.html` | Full rebuild — Uber Noir, service selector, multi-stop, fare preview with breakdown |
| `frontend/templates/driver.html` | Full rebuild — Uber Noir, active ride with stops, add-stop flow |
| `frontend/templates/admin.html` | Full rebuild — 8-tab nav, Tracking tab (Leaflet), OASR tab, Settings tab |
| `backend/database_schema.sql` | Migration addendum for new columns |

---

## Task 1: Design System CSS

**Files:**
- Create: `frontend/static/css/design-system.css`

- [ ] **Step 1: Create the design system CSS file**

Create `/Users/saqib/Downloads/caledonia-taxi/frontend/static/css/design-system.css` with the full Uber Noir token set and all shared component classes:

```css
/* ============================================================
   CALEDONIA TAXI — DESIGN SYSTEM
   Uber Noir theme. All three apps load this file.
   ============================================================ */

:root {
  --bg:           #000000;
  --surface-1:    #0D0D0D;
  --surface-2:    #111111;
  --surface-3:    #1A1A1A;
  --border:       #222222;
  --border-sub:   #1A1A1A;
  --text-primary: #FFFFFF;
  --text-secondary:#888888;
  --text-muted:   #444444;
  --accent:       #FFFFFF;
  --accent-text:  #000000;
  --green:        #22C55E;
  --amber:        #F59E0B;
  --red:          #EF4444;
  --blue:         #3B82F6;
  --radius-card:  8px;
  --radius-input: 6px;
  --radius-pill:  50px;
  --transition:   150ms ease;
  font-family: -apple-system, 'SF Pro Display', 'Helvetica Neue', Arial, sans-serif;
}

/* Reset */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { background: var(--bg); color: var(--text-primary); min-height: 100vh; -webkit-font-smoothing: antialiased; }
a { color: inherit; text-decoration: none; }

/* Typography */
h1 { font-size: 2rem; font-weight: 700; letter-spacing: -0.02em; }
h2 { font-size: 1.5rem; font-weight: 700; letter-spacing: -0.02em; }
h3 { font-size: 1.125rem; font-weight: 600; letter-spacing: -0.01em; }
.label { font-size: 0.6875rem; font-weight: 500; letter-spacing: 0.08em; text-transform: uppercase; color: var(--text-secondary); }
.mono { font-family: 'SF Mono', 'Menlo', 'Consolas', monospace; }

/* Layout */
.page-wrap { max-width: 480px; margin: 0 auto; padding: 0 16px 80px; }
.page-wrap--wide { max-width: 1200px; margin: 0 auto; padding: 0 24px 80px; }

/* Header */
.site-header { display: flex; align-items: center; justify-content: space-between; padding: 20px 0 16px; border-bottom: 1px solid var(--border-sub); margin-bottom: 24px; }
.site-logo { font-size: 1rem; font-weight: 800; letter-spacing: 0.1em; text-transform: uppercase; color: var(--text-primary); }
.site-header-action { font-size: 0.875rem; color: var(--text-secondary); }

/* Cards / Surfaces */
.card { background: var(--surface-1); border: 1px solid var(--border); border-radius: var(--radius-card); padding: 16px; }
.card + .card { margin-top: 8px; }
.card--flat { background: var(--surface-2); border-color: var(--border-sub); }

/* Form elements */
.form-group { margin-bottom: 12px; }
.form-label { display: block; font-size: 0.6875rem; font-weight: 500; letter-spacing: 0.08em; text-transform: uppercase; color: var(--text-secondary); margin-bottom: 6px; }
.form-input {
  width: 100%; background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-input);
  color: var(--text-primary); font-size: 0.9375rem; padding: 11px 12px;
  outline: none; transition: border-color var(--transition);
  font-family: inherit;
}
.form-input::placeholder { color: var(--text-muted); }
.form-input:focus { border-color: var(--text-primary); }
.form-input:disabled { opacity: 0.4; cursor: not-allowed; }

/* Buttons */
.btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; font-size: 0.9375rem; font-weight: 600; padding: 12px 20px; border-radius: var(--radius-input); border: none; cursor: pointer; transition: opacity var(--transition); white-space: nowrap; font-family: inherit; }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn:not(:disabled):hover { opacity: 0.85; }
.btn-primary { background: var(--accent); color: var(--accent-text); }
.btn-secondary { background: transparent; color: var(--text-primary); border: 1px solid var(--border); }
.btn-danger { background: transparent; color: var(--red); border: 1px solid var(--red); }
.btn-full { width: 100%; }
.btn-sm { font-size: 0.8125rem; padding: 8px 14px; }

/* Pill / Service selector */
.pill-row { display: flex; gap: 8px; margin-bottom: 20px; flex-wrap: wrap; }
.pill { padding: 7px 16px; border-radius: var(--radius-pill); border: 1px solid var(--border); font-size: 0.875rem; font-weight: 500; cursor: pointer; transition: all var(--transition); background: transparent; color: var(--text-secondary); font-family: inherit; }
.pill.active, .pill:hover { border-color: var(--text-primary); color: var(--text-primary); background: var(--surface-2); }
.pill.active { background: var(--text-primary); color: var(--accent-text); }

/* Status badges */
.badge { display: inline-flex; align-items: center; gap: 5px; font-size: 0.75rem; font-weight: 600; padding: 3px 8px; border-radius: var(--radius-pill); }
.badge::before { content: ''; width: 6px; height: 6px; border-radius: 50%; background: currentColor; flex-shrink: 0; }
.badge-green  { color: var(--green);  background: rgba(34,197,94,.12);  }
.badge-amber  { color: var(--amber);  background: rgba(245,158,11,.12);  }
.badge-red    { color: var(--red);    background: rgba(239,68,68,.12);   }
.badge-blue   { color: var(--blue);   background: rgba(59,130,246,.12);  }
.badge-grey   { color: var(--text-secondary); background: var(--surface-2); }
.badge-white  { color: var(--text-primary); background: var(--surface-2); }

/* Status dot (standalone) */
.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; }
.dot-green  { background: var(--green); box-shadow: 0 0 6px var(--green); }
.dot-amber  { background: var(--amber); }
.dot-red    { background: var(--red); }
.dot-grey   { background: var(--text-muted); }

/* Divider */
.divider { height: 1px; background: var(--border-sub); margin: 16px 0; }

/* Error / Success messages */
.error-msg  { color: var(--red);   font-size: 0.875rem; margin-top: 6px; min-height: 1.2em; }
.success-msg { color: var(--green); font-size: 0.875rem; margin-top: 6px; }

/* Spinner */
.spinner { display: inline-block; width: 18px; height: 18px; border: 2px solid var(--border); border-top-color: var(--text-primary); border-radius: 50%; animation: spin 0.7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* Tabs */
.tab-bar { display: flex; gap: 0; border-bottom: 1px solid var(--border-sub); margin-bottom: 24px; overflow-x: auto; -webkit-overflow-scrolling: touch; }
.tab-bar::-webkit-scrollbar { display: none; }
.tab-btn { padding: 12px 16px; font-size: 0.875rem; font-weight: 500; color: var(--text-secondary); background: none; border: none; border-bottom: 2px solid transparent; cursor: pointer; white-space: nowrap; transition: all var(--transition); font-family: inherit; }
.tab-btn:hover { color: var(--text-primary); }
.tab-btn.active { color: var(--text-primary); border-bottom-color: var(--text-primary); }
.tab-panel { display: none; }
.tab-panel.active { display: block; }

/* Drawer (slide-up overlay) */
.drawer-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.7); z-index: 100; opacity: 0; pointer-events: none; transition: opacity var(--transition); }
.drawer-overlay.open { opacity: 1; pointer-events: all; }
.drawer { position: fixed; bottom: 0; left: 0; right: 0; max-height: 85vh; overflow-y: auto; background: var(--surface-1); border-radius: 12px 12px 0 0; border-top: 1px solid var(--border); z-index: 101; transform: translateY(100%); transition: transform 300ms ease; }
.drawer.open { transform: translateY(0); }
.drawer-handle { width: 36px; height: 4px; background: var(--border); border-radius: 2px; margin: 12px auto 16px; }
.drawer-header { display: flex; align-items: center; justify-content: space-between; padding: 0 16px 16px; }
.drawer-title { font-size: 1rem; font-weight: 700; }
.drawer-close { background: none; border: none; color: var(--text-secondary); font-size: 1.25rem; cursor: pointer; padding: 4px; }
.drawer-body { padding: 0 16px 24px; }

/* Right drawer (admin tracking) */
.right-drawer { position: fixed; top: 0; right: 0; bottom: 0; width: 320px; background: var(--surface-1); border-left: 1px solid var(--border); z-index: 101; transform: translateX(100%); transition: transform 300ms ease; overflow-y: auto; padding: 20px; }
.right-drawer.open { transform: translateX(0); }

/* Table */
.data-table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
.data-table th { text-align: left; padding: 10px 12px; font-size: 0.6875rem; font-weight: 500; letter-spacing: 0.08em; text-transform: uppercase; color: var(--text-secondary); border-bottom: 1px solid var(--border); }
.data-table td { padding: 12px; border-bottom: 1px solid var(--border-sub); color: var(--text-primary); vertical-align: middle; }
.data-table tr:hover td { background: var(--surface-2); }

/* KPI card */
.kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-bottom: 24px; }
.kpi-card { background: var(--surface-1); border: 1px solid var(--border); border-radius: var(--radius-card); padding: 16px; }
.kpi-label { font-size: 0.6875rem; font-weight: 500; letter-spacing: 0.08em; text-transform: uppercase; color: var(--text-secondary); margin-bottom: 8px; }
.kpi-value { font-size: 1.75rem; font-weight: 700; letter-spacing: -0.02em; }
.kpi-sub { font-size: 0.75rem; color: var(--text-secondary); margin-top: 4px; }

/* Filter pills row */
.filter-row { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
.filter-pill { padding: 5px 12px; border-radius: var(--radius-pill); border: 1px solid var(--border); font-size: 0.8125rem; cursor: pointer; background: transparent; color: var(--text-secondary); font-family: inherit; transition: all var(--transition); }
.filter-pill.active { border-color: var(--text-primary); color: var(--text-primary); }

/* Fare breakdown */
.fare-breakdown { background: var(--surface-1); border: 1px solid var(--border); border-radius: var(--radius-card); overflow: hidden; }
.fare-row { display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; border-bottom: 1px solid var(--border-sub); font-size: 0.875rem; }
.fare-row:last-child { border-bottom: none; }
.fare-row.total { font-weight: 700; font-size: 1rem; padding: 12px 14px; background: var(--surface-2); }
.fare-row.discount { color: var(--green); }
.fare-row.surge { color: var(--amber); }

/* Stop list item */
.stop-item { display: flex; align-items: center; gap: 10px; padding: 10px 0; border-bottom: 1px solid var(--border-sub); }
.stop-item:last-child { border-bottom: none; }
.stop-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--text-secondary); flex-shrink: 0; }
.stop-dot.pickup { background: var(--green); }
.stop-dot.dropoff { background: var(--red); }
.stop-dot.stop { background: var(--blue); }
.stop-label { flex: 1; font-size: 0.875rem; }
.stop-remove { background: none; border: none; color: var(--text-muted); font-size: 1.125rem; cursor: pointer; padding: 2px 6px; }
.stop-remove:hover { color: var(--red); }

/* Surge banner */
.surge-banner { background: rgba(239,68,68,.1); border: 1px solid rgba(239,68,68,.3); border-radius: var(--radius-input); padding: 10px 14px; display: flex; align-items: center; gap: 8px; margin-bottom: 12px; font-size: 0.875rem; }
.surge-banner .surge-badge { background: var(--red); color: #fff; font-size: 0.75rem; font-weight: 700; padding: 2px 7px; border-radius: var(--radius-pill); }

/* Step indicator */
.step-indicator { display: flex; align-items: center; gap: 8px; margin-bottom: 24px; }
.step-dot { width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 0.75rem; font-weight: 700; border: 1px solid var(--border); color: var(--text-muted); background: var(--surface-2); flex-shrink: 0; }
.step-dot.active { border-color: var(--text-primary); color: var(--text-primary); background: var(--text-primary); color: var(--accent-text); }
.step-dot.done { border-color: var(--green); background: var(--green); color: #fff; }
.step-line { flex: 1; height: 1px; background: var(--border); }

/* Map container */
.map-container { border-radius: var(--radius-card); overflow: hidden; border: 1px solid var(--border); }

/* Countdown ring */
.countdown-ring { transform: rotate(-90deg); }
.countdown-ring .track { fill: none; stroke: var(--surface-3); stroke-width: 3; }
.countdown-ring .progress { fill: none; stroke: var(--text-primary); stroke-width: 3; stroke-linecap: round; transition: stroke-dashoffset 1s linear; }

/* Modal / overlay (fullscreen) */
.modal { position: fixed; inset: 0; background: var(--bg); z-index: 200; display: flex; flex-direction: column; transform: translateY(100%); transition: transform 300ms ease; }
.modal.open { transform: translateY(0); }

/* Active ride legs */
.leg-item { padding: 12px 0; display: flex; gap: 12px; align-items: flex-start; }
.leg-item + .leg-item { border-top: 1px solid var(--border-sub); }
.leg-status { width: 24px; height: 24px; border-radius: 50%; background: var(--surface-3); border: 1px solid var(--border); display: flex; align-items: center; justify-content: center; font-size: 0.75rem; flex-shrink: 0; margin-top: 1px; }
.leg-status.current { border-color: var(--text-primary); background: var(--text-primary); color: var(--accent-text); }
.leg-status.done { border-color: var(--green); background: var(--green); color: #fff; }
.leg-info { flex: 1; }
.leg-title { font-size: 0.9375rem; font-weight: 600; }
.leg-sub { font-size: 0.8125rem; color: var(--text-secondary); margin-top: 2px; }

/* Login page */
.login-page { min-height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 24px; }
.login-box { width: 100%; max-width: 360px; }
.login-logo { font-size: 1.125rem; font-weight: 800; letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 32px; text-align: center; }
.login-title { font-size: 1.5rem; font-weight: 700; margin-bottom: 4px; }
.login-sub { font-size: 0.875rem; color: var(--text-secondary); margin-bottom: 28px; }

/* Responsive */
@media (max-width: 600px) {
  .right-drawer { width: 100%; }
  .data-table { display: block; overflow-x: auto; }
}
```

- [ ] **Step 2: Commit**

```bash
cd /Users/saqib/Downloads/caledonia-taxi
git add frontend/static/css/design-system.css
git commit -m "feat: add Uber Noir design system CSS"
```

---

## Task 2: fare-engine.js

**Files:**
- Create: `frontend/static/js/fare-engine.js`

- [ ] **Step 1: Create fare-engine.js**

Create `/Users/saqib/Downloads/caledonia-taxi/frontend/static/js/fare-engine.js`:

```js
/**
 * Caledonia Taxi — Client-Side Fare Engine
 * Must stay in sync with backend/services.py calculate_fare().
 * This is display-only; server is authoritative for payment amounts.
 */
const fareEngine = (() => {
  /**
   * estimate(legs, service, options) → breakdown
   *
   * @param {Array<{from:string, to:string, km:number}>} legs
   * @param {string} service  "standard" | "medical" | "long_distance"
   * @param {object} options
   *   flatRates       {string: number}  city → flat price
   *   surgeMultiplier number            1.0 = no surge
   *   promoDiscount   number            0.0–1.0 fraction
   *   stopSurcharge   number            $ per intermediate stop
   *   baseFare        number
   *   perKmRate       number
   *   minimumFare     number
   */
  function estimate(legs, service, options = {}) {
    const {
      flatRates = {},
      surgeMultiplier = 1.0,
      promoDiscount = 0.0,
      stopSurcharge = 3.00,
      baseFare = 4.50,
      perKmRate = 2.10,
      minimumFare = 8.00,
    } = options;

    const stopCount = Math.max(0, legs.length - 1); // intermediate stops = legs - 1

    let computedLegs = [];
    let isFlat = false;

    if (service === 'long_distance') {
      // Use flat rate for destination city (last leg's to)
      const dest = legs[legs.length - 1]?.to || '';
      const flat = flatRates[dest] ?? 0;
      isFlat = true;
      computedLegs = legs.map((leg, i) => ({
        label: `${leg.from} → ${leg.to}`,
        km: leg.km,
        subtotal: i === 0 ? flat : 0, // entire flat rate on first leg for display
      }));
    } else {
      // Metered: base fare on first leg, per-km on all legs
      computedLegs = legs.map((leg, i) => ({
        label: `${leg.from} → ${leg.to}`,
        km: leg.km,
        subtotal: round2((i === 0 ? baseFare : 0) + leg.km * perKmRate),
      }));
    }

    const legTotal = round2(computedLegs.reduce((s, l) => s + l.subtotal, 0));
    const stopFee = round2(stopCount * stopSurcharge);
    const subtotal = round2(legTotal + stopFee);

    const promoAmt = round2(subtotal * promoDiscount);
    const surgeAmt = round2(subtotal * (surgeMultiplier - 1.0));

    let total = round2(subtotal - promoAmt + surgeAmt);
    total = Math.max(total, minimumFare);

    return {
      legs: computedLegs,
      base_fare: isFlat ? 0 : baseFare,
      stop_surcharge: stopFee,
      subtotal,
      promo_discount: -promoAmt,
      surge_addition: surgeAmt,
      total,
      is_flat_rate: isFlat,
    };
  }

  function round2(n) {
    return Math.round(n * 100) / 100;
  }

  return { estimate };
})();
```

- [ ] **Step 2: Commit**

```bash
git add frontend/static/js/fare-engine.js
git commit -m "feat: add client-side fare engine module"
```

---

## Task 3: Backend Models + Settings

**Files:**
- Modify: `backend/models.py`
- Modify: `backend/config.py`
- Create: `backend/settings.json` (template only; populated by Settings tab)

- [ ] **Step 1: Update models.py — add new enum values and fields**

Open `backend/models.py`. Add `needs_review` to `BookingStatus`, add `oasr` to `BookingSource`, add `service_type`, `stops`, `fare_breakdown` to `BookingRequest`:

Find the `BookingStatus` class and add `needs_review = "needs_review"`.
Find the `BookingSource` class (or enum) and add `oasr = "oasr"`.

In `BookingRequest` Pydantic model, add:
```python
service_type: str = "standard"        # "standard" | "medical" | "long_distance"
stops: List[str] = []                 # intermediate stop addresses
promo_code: Optional[str] = None
```
Make sure `List` and `Optional` are imported from `typing`.

- [ ] **Step 2: Update FareEstimateRequest in models.py**

Find `FareEstimateRequest` (or the Pydantic model used by `/api/estimate-fare`). Add:
```python
service_type: str = "standard"
stops: List[str] = []
promo_code: Optional[str] = None
```

- [ ] **Step 3: Create default backend/settings.json**

Create `/Users/saqib/Downloads/caledonia-taxi/backend/settings.json`:
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
    {"code": "FIRST10",     "discount_pct": 10, "active": true},
    {"code": "CALEDONIA20", "discount_pct": 20, "active": true}
  ]
}
```

- [ ] **Step 4: Update config.py to load settings.json**

In `backend/config.py`, add after existing imports:

```python
import json, pathlib

_SETTINGS_FILE = pathlib.Path(__file__).parent / "settings.json"

def load_settings() -> dict:
    """Hot-load settings from settings.json, fall back to env vars."""
    if _SETTINGS_FILE.exists():
        with open(_SETTINGS_FILE) as f:
            return json.load(f)
    return {}

def save_settings(data: dict) -> None:
    with open(_SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_pricing():
    s = load_settings()
    p = s.get("pricing", {})
    return {
        "base_fare":     float(p.get("base_fare",     BASE_FARE)),
        "per_km_rate":   float(p.get("per_km_rate",   PER_KM_RATE)),
        "minimum_fare":  float(p.get("minimum_fare",  MINIMUM_FARE)),
        "stop_surcharge":float(p.get("stop_surcharge", 3.00)),
    }

def get_flat_rates() -> dict:
    s = load_settings()
    return s.get("flat_rates", {})

def get_surge_config() -> dict:
    s = load_settings()
    return s.get("surge", {
        "enabled": True,
        "tier1_pending_min": 3, "tier1_available_max": 2, "tier1_multiplier": 1.5,
        "tier2_pending_min": 5, "tier2_available_max": 1, "tier2_multiplier": 2.0,
    })

def get_promo_codes() -> list:
    s = load_settings()
    return s.get("promo_codes", [])
```

- [ ] **Step 5: Update database_schema.sql migration addendum**

Append to `backend/database_schema.sql`:
```sql
-- =============================================
-- MIGRATION: 2026-03-18 full platform redesign
-- =============================================
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS service_type TEXT DEFAULT 'standard';
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS stops JSONB DEFAULT '[]';
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS fare_breakdown JSONB;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS oasr_source BOOLEAN DEFAULT FALSE;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS needs_review BOOLEAN DEFAULT FALSE;

ALTER TABLE drivers ADD COLUMN IF NOT EXISTS vehicle TEXT DEFAULT '';
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS plate TEXT DEFAULT '';
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS inactive BOOLEAN DEFAULT FALSE;

ALTER TABLE bookings DROP CONSTRAINT IF EXISTS bookings_status_check;
ALTER TABLE bookings ADD CONSTRAINT bookings_status_check
  CHECK (status IN ('pending','dispatched','accepted','in_progress','completed','cancelled','scheduled','dispatch_failed','needs_review'));

ALTER TABLE bookings DROP CONSTRAINT IF EXISTS bookings_source_check;
ALTER TABLE bookings ADD CONSTRAINT bookings_source_check
  CHECK (source IN ('web','phone','admin','voice_ai','oasr'));
```

- [ ] **Step 6: Commit**

```bash
git add backend/models.py backend/config.py backend/settings.json backend/database_schema.sql
git commit -m "feat: add settings.json hot-load, new booking fields, updated enums"
```

---

## Task 4: Backend Fare Engine (services.py)

**Files:**
- Modify: `backend/services.py`

- [ ] **Step 1: Read the existing fare calculation in services.py**

Open `backend/services.py` and find the `calculate_fare()` function (or equivalent). Understand its current signature and what it returns.

- [ ] **Step 2: Replace/extend calculate_fare with multi-leg support**

The updated function must match the `fareEngine.estimate()` contract in `fare-engine.js`. Add or replace with:

```python
from backend.config import get_pricing, get_flat_rates, get_surge_config

def calculate_fare(
    legs: list[dict],          # [{"from": str, "to": str, "km": float}]
    service_type: str = "standard",
    surge_multiplier: float = 1.0,
    promo_discount: float = 0.0,
) -> dict:
    """
    Multi-leg fare calculation. Authoritative — server result used for Stripe.
    Must stay in sync with frontend/static/js/fare-engine.js.

    Returns:
      legs: [{"label": str, "km": float, "subtotal": float}]
      base_fare, stop_surcharge, subtotal, promo_discount, surge_addition, total, is_flat_rate
    """
    pricing = get_pricing()
    flat_rates = get_flat_rates()
    base_fare = pricing["base_fare"]
    per_km = pricing["per_km_rate"]
    min_fare = pricing["minimum_fare"]
    stop_fee = pricing["stop_surcharge"]

    stop_count = max(0, len(legs) - 1)
    is_flat = service_type == "long_distance"

    computed_legs = []
    if is_flat:
        dest = legs[-1]["to"] if legs else ""
        flat = flat_rates.get(dest, 0.0)
        for i, leg in enumerate(legs):
            computed_legs.append({
                "label": f"{leg['from']} → {leg['to']}",
                "km": leg["km"],
                "subtotal": round(flat if i == 0 else 0, 2),
            })
    else:
        for i, leg in enumerate(legs):
            subtotal = round((base_fare if i == 0 else 0) + leg["km"] * per_km, 2)
            computed_legs.append({
                "label": f"{leg['from']} → {leg['to']}",
                "km": leg["km"],
                "subtotal": subtotal,
            })

    leg_total = round(sum(l["subtotal"] for l in computed_legs), 2)
    stop_total = round(stop_count * stop_fee, 2)
    subtotal = round(leg_total + stop_total, 2)
    promo_amt = round(subtotal * promo_discount, 2)
    surge_amt = round(subtotal * (surge_multiplier - 1.0), 2)
    total = round(max(subtotal - promo_amt + surge_amt, min_fare), 2)

    return {
        "legs": computed_legs,
        "base_fare": base_fare if not is_flat else 0,
        "stop_surcharge": stop_total,
        "subtotal": subtotal,
        "promo_discount": -promo_amt,
        "surge_addition": surge_amt,
        "total": total,
        "is_flat_rate": is_flat,
        "estimated_fare": total,  # convenience alias
    }
```

Also add a helper `get_current_surge_multiplier(bookings_db: dict, drivers_db: dict) -> float` that reads thresholds from `get_surge_config()` instead of hard-coded values. Update existing `/api/surge` to use it.

- [ ] **Step 3: Verify geocode function name and add multi-stop helper**

First, open `backend/services.py` and find the existing single-address geocode function — it may be named `geocode_address`, `geocode`, or `get_coordinates`. Use the actual name in the code below. Then add or update a helper that geocodes a list of address strings and returns them as legs:

```python
async def geocode_route(addresses: list[str]) -> list[dict]:
    """
    Geocode each address and compute Haversine distances between consecutive points.
    Returns list of legs: [{"from": str, "to": str, "km": float, "from_lat":..., "from_lng":..., "to_lat":..., "to_lng":...}]
    """
    coords = []
    for addr in addresses:
        lat, lng = await geocode_address(addr)  # existing geocode function
        coords.append({"address": addr, "lat": lat, "lng": lng})

    legs = []
    for i in range(len(coords) - 1):
        a, b = coords[i], coords[i + 1]
        km = haversine(a["lat"], a["lng"], b["lat"], b["lng"])
        legs.append({
            "from": a["address"], "to": b["address"],
            "km": km,
            "from_lat": a["lat"], "from_lng": a["lng"],
            "to_lat": b["lat"],  "to_lng":  b["lng"],
        })
    return legs
```

- [ ] **Step 4: Commit**

```bash
git add backend/services.py
git commit -m "feat: multi-leg fare engine in services.py, reads settings.json"
```

---

## Task 5: OASR Parser

**Files:**
- Create: `backend/oasr_parser.py`

- [ ] **Step 1: Create the OASR email parser module**

Create `/Users/saqib/Downloads/caledonia-taxi/backend/oasr_parser.py`:

```python
"""
OASR Email Parser
Extracts taxi booking fields from raw Ontario Association of Scheduled Rides emails.
Returns a dict with confidence score. Low confidence → needs_review = True.
"""
import re
from datetime import datetime, date
from typing import Optional

HOSPITAL_KEYWORDS = [
    "hospital", "clinic", "medical", "health centre", "health center",
    "doctors", "dr.", "dialysis", "cancer care", "cancer centre",
    "mcmaster", "henderson", "juravinski", "st. joseph", "st joseph",
    "general hospital", "regional", "centre for", "center for",
]

def parse_oasr_email(raw_text: str) -> dict:
    """
    Parse raw OASR email text into booking fields.

    Returns:
      {
        "patient_name": str | None,
        "pickup_address": str | None,
        "dropoff_address": str | None,
        "ride_date": str | None,   # ISO date "YYYY-MM-DD"
        "ride_time": str | None,   # "HH:MM"
        "notes": str | None,
        "confidence": int,         # 0–5, number of fields extracted
        "needs_review": bool,      # True if confidence < 3
        "raw": str,
      }
    """
    text = raw_text.strip()
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    result = {
        "patient_name": None,
        "pickup_address": None,
        "dropoff_address": None,
        "ride_date": None,
        "ride_time": None,
        "notes": None,
        "raw": text,
    }

    # --- Date ---
    date_patterns = [
        r'\b(\w+ \d{1,2},?\s*\d{4})\b',              # March 19, 2026
        r'\b(\d{4}-\d{2}-\d{2})\b',                   # 2026-03-19
        r'\b(\d{1,2}/\d{1,2}/\d{2,4})\b',             # 19/03/26
        r'\b(\d{1,2}-\d{1,2}-\d{2,4})\b',             # 19-03-26
    ]
    for pat in date_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            result["ride_date"] = _normalise_date(m.group(1))
            if result["ride_date"]:
                break

    # --- Time ---
    time_m = re.search(r'\b(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?)\b', text)
    if time_m:
        result["ride_time"] = _normalise_time(time_m.group(1))

    # --- Patient name ---
    name_m = re.search(r'(?:patient|name|client)[:\s]+([A-Z][a-z]+ [A-Z][a-z]+)', text, re.IGNORECASE)
    if name_m:
        result["patient_name"] = name_m.group(1).strip()

    # --- Pickup address ---
    pickup_m = re.search(
        r'(?:pickup|pick up|pick-up|from|origin)[:\s]+(.+?)(?:\n|dropoff|drop off|destination|to:|$)',
        text, re.IGNORECASE | re.DOTALL
    )
    if pickup_m:
        result["pickup_address"] = pickup_m.group(1).strip().split('\n')[0].strip()

    # --- Dropoff address ---
    dropoff_m = re.search(
        r'(?:dropoff|drop off|drop-off|destination|to|hospital)[:\s]+(.+?)(?:\n|notes|special|$)',
        text, re.IGNORECASE | re.DOTALL
    )
    if dropoff_m:
        result["dropoff_address"] = dropoff_m.group(1).strip().split('\n')[0].strip()

    # --- Hospital name fallback: scan lines for known hospital keywords ---
    if not result["dropoff_address"]:
        for line in lines:
            if any(kw in line.lower() for kw in HOSPITAL_KEYWORDS):
                result["dropoff_address"] = line
                break

    # --- Notes ---
    notes_m = re.search(r'(?:notes?|special instructions?|comments?)[:\s]+(.+)', text, re.IGNORECASE | re.DOTALL)
    if notes_m:
        result["notes"] = notes_m.group(1).strip()[:500]

    # --- Confidence score ---
    fields = ["patient_name", "pickup_address", "dropoff_address", "ride_date", "ride_time"]
    result["confidence"] = sum(1 for f in fields if result[f])
    result["needs_review"] = result["confidence"] < 3

    return result


def _normalise_date(raw: str) -> Optional[str]:
    fmts = ["%B %d, %Y", "%B %d %Y", "%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y"]
    raw = raw.replace(",", "").strip()
    for fmt in fmts:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _normalise_time(raw: str) -> Optional[str]:
    raw = raw.strip().upper()
    for fmt in ["%I:%M %p", "%I:%M%p", "%H:%M"]:
        try:
            return datetime.strptime(raw, fmt).strftime("%H:%M")
        except ValueError:
            continue
    return None
```

- [ ] **Step 2: Commit**

```bash
git add backend/oasr_parser.py
git commit -m "feat: OASR email parser module"
```

---

## Task 6: Backend New Endpoints (main.py)

**Files:**
- Modify: `backend/main.py`

This task adds all new endpoints. Work section by section. The server is already running with `--reload` so changes apply live.

- [ ] **Step 1: Update `/api/estimate-fare` for multi-leg**

Find the existing `estimate_fare` route handler. Replace it to accept the new request fields and call the updated `calculate_fare`:

```python
@app.post("/api/estimate-fare")
async def estimate_fare(request: FareEstimateRequest):
    addresses = [request.pickup_address] + list(request.stops or []) + [request.dropoff_address]
    legs = await geocode_route(addresses)

    surge_mult = get_current_surge_multiplier(bookings_db, drivers_db)
    promo_disc = 0.0
    if request.promo_code:
        for pc in get_promo_codes():
            if pc["code"].upper() == request.promo_code.upper() and pc.get("active", True):
                promo_disc = pc["discount_pct"] / 100.0
                break

    breakdown = calculate_fare(legs, request.service_type or "standard", surge_mult, promo_disc)
    return {**breakdown, "legs_geocoded": legs}
```

- [ ] **Step 2: Add `POST /api/bookings/{id}/stops`**

```python
@app.post("/api/bookings/{booking_id}/stops")
async def add_stop_to_ride(booking_id: str, body: dict = Body(...)):
    booking = bookings_db.get(booking_id)
    if not booking:
        raise HTTPException(404, "Booking not found")
    if booking["status"] != "in_progress":
        raise HTTPException(400, "Can only add stops to in-progress rides")

    new_addr = body.get("address", "")
    lat = body.get("lat")
    lng = body.get("lng")

    if not lat or not lng:
        lat, lng = await geocode_address(new_addr)

    stops = list(booking.get("stops", []))
    stops.append(new_addr)
    booking["stops"] = stops

    # Recalculate fare with full route
    all_addresses = [booking["pickup_address"]] + stops + [booking["dropoff_address"]]
    legs = await geocode_route(all_addresses)
    breakdown = calculate_fare(legs, booking.get("service_type", "standard"))
    booking["actual_fare"] = breakdown["total"]
    booking["fare_breakdown"] = breakdown

    await broadcast({"type": "fare_updated", "booking_id": booking_id, "fare": breakdown["total"], "breakdown": breakdown})

    return {"booking_id": booking_id, "actual_fare": breakdown["total"], "fare_breakdown": breakdown}
```

- [ ] **Step 3: Add flat rate CRUD endpoints**

```python
@app.get("/api/flat-rates")
async def get_flat_rates_endpoint():
    return get_flat_rates()

@app.post("/api/flat-rates", dependencies=[Depends(require_admin)])
async def set_flat_rate(body: dict = Body(...)):
    # body: {"city": "Hamilton", "price": 35.00}
    s = load_settings()
    s.setdefault("flat_rates", {})[body["city"]] = float(body["price"])
    save_settings(s)
    return {"ok": True}

@app.delete("/api/flat-rates/{city}", dependencies=[Depends(require_admin)])
async def delete_flat_rate(city: str):
    s = load_settings()
    s.get("flat_rates", {}).pop(city, None)
    save_settings(s)
    return {"ok": True}
```

- [ ] **Step 4: Add OASR endpoints**

```python
from backend.oasr_parser import parse_oasr_email
from datetime import datetime, timezone

@app.post("/api/oasr/inbound")
async def oasr_inbound(request: Request):
    # Accept JSON body {"raw_email": "..."} or SendGrid Inbound Parse form
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        data = await request.json()
        raw = data.get("raw_email", "")
    else:
        form = await request.form()
        raw = form.get("text", "") or form.get("html", "") or ""

    parsed = parse_oasr_email(raw)

    # Build scheduled datetime
    scheduled_for = None
    if parsed["ride_date"] and parsed["ride_time"]:
        try:
            scheduled_for = f"{parsed['ride_date']}T{parsed['ride_time']}:00+00:00"
        except Exception:
            pass

    booking_id = str(uuid.uuid4())[:8].upper()
    booking = {
        "id": booking_id,
        "customer_name": parsed["patient_name"] or "OASR Patient",
        "customer_phone": "",
        "pickup_address": parsed["pickup_address"] or "",
        "dropoff_address": parsed["dropoff_address"] or "",
        "stops": [],
        "service_type": "medical",
        "estimated_fare": 0,
        "actual_fare": 0,
        "status": "needs_review" if parsed["needs_review"] else "scheduled",
        "source": "oasr",
        "oasr_source": True,
        "needs_review": parsed["needs_review"],
        "scheduled_for": scheduled_for,
        "notes": parsed["notes"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "assigned_driver_id": None,
        "payment_method": "cash",
        "dispatch_attempts": 0,
    }
    bookings_db[booking_id] = booking
    logger.info(f"[OASR] Created booking {booking_id} confidence={parsed['confidence']} needs_review={parsed['needs_review']}")
    return {"booking_id": booking_id, "parsed": parsed, "needs_review": parsed["needs_review"]}

@app.get("/api/admin/oasr", dependencies=[Depends(require_admin)])
async def admin_oasr():
    oasr_bookings = [b for b in bookings_db.values() if b.get("source") == "oasr"]
    oasr_bookings.sort(key=lambda b: b.get("created_at", ""), reverse=True)
    return oasr_bookings
```

- [ ] **Step 5: Add driver CRUD endpoints**

```python
@app.post("/api/drivers", dependencies=[Depends(require_admin)])
async def create_driver(body: dict = Body(...)):
    driver_id = str(uuid.uuid4())
    driver = {
        "id": driver_id,
        "name": body["name"],
        "phone": body["phone"],
        "pin": body["pin"],
        "vehicle": body.get("vehicle", ""),
        "plate": body.get("plate", ""),
        "status": "offline",
        "latitude": 43.0773,
        "longitude": -79.9408,
        "last_location_update": None,
        "inactive": False,
        "push_subscriptions": [],
        "ratings": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    drivers_db[driver_id] = driver
    return driver

@app.put("/api/drivers/{driver_id}", dependencies=[Depends(require_admin)])
async def update_driver(driver_id: str, body: dict = Body(...)):
    driver = drivers_db.get(driver_id)
    if not driver:
        raise HTTPException(404, "Driver not found")
    for field in ["name", "phone", "pin", "vehicle", "plate"]:
        if field in body:
            driver[field] = body[field]
    driver["updated_at"] = datetime.now(timezone.utc).isoformat()
    return driver

@app.patch("/api/drivers/{driver_id}/deactivate", dependencies=[Depends(require_admin)])
async def deactivate_driver(driver_id: str):
    driver = drivers_db.get(driver_id)
    if not driver:
        raise HTTPException(404, "Driver not found")
    driver["inactive"] = True
    driver["status"] = "offline"
    return {"ok": True}
```

- [ ] **Step 6: Add `GET /api/admin/driver-locations`**

```python
@app.get("/api/admin/driver-locations", dependencies=[Depends(require_admin)])
async def admin_driver_locations():
    result = []
    for d in drivers_db.values():
        if d.get("inactive"):
            continue
        active_booking = None
        for b in bookings_db.values():
            if b.get("assigned_driver_id") == d["id"] and b["status"] in ("accepted", "in_progress"):
                all_stops = [b["pickup_address"]] + list(b.get("stops", [])) + [b["dropoff_address"]]
                active_booking = {
                    "id": b["id"],
                    "customer_name": b["customer_name"],
                    "pickup_address": b["pickup_address"],
                    "dropoff_address": b["dropoff_address"],
                    "stops": list(b.get("stops", [])),
                    "current_leg": b.get("current_leg", 0),
                    "total_legs": max(1, len(all_stops) - 1),
                    "estimated_fare": b.get("estimated_fare", 0),
                    "waypoints": b.get("waypoints", []),
                }
                break
        result.append({
            "id": d["id"],
            "name": d["name"],
            "phone": d.get("phone", ""),   # included for tel: links in admin UI
            "vehicle": d.get("vehicle", ""),
            "plate": d.get("plate", ""),
            "status": d["status"],
            "lat": d.get("latitude"),
            "lng": d.get("longitude"),
            "last_update": d.get("last_location_update"),
            "active_booking": active_booking,
        })
    return result
```

- [ ] **Step 7: Add settings CRUD endpoints**

```python
@app.get("/api/admin/settings", dependencies=[Depends(require_admin)])
async def admin_get_settings():
    return load_settings()

@app.post("/api/admin/settings", dependencies=[Depends(require_admin)])
async def admin_save_settings(body: dict = Body(...)):
    save_settings(body)
    return {"ok": True}
```

- [ ] **Step 8: Update driver-history to include acceptance_rate**

Find the `GET /api/admin/driver-history` handler. Add acceptance rate calculation:

```python
# After computing total_rides and completed:
dispatched = [e for e in dispatch_log if e.get("driver_id") == d["id"]]
accepted   = [e for e in dispatched if e.get("action") == "accept"]
acceptance_rate = round(len(accepted) / len(dispatched) * 100) if dispatched else 100
# Add to the response dict: "acceptance_rate": acceptance_rate
```

- [ ] **Step 9: Verify server starts cleanly**

```bash
cd /Users/saqib/Downloads/caledonia-taxi && curl -s http://localhost:8000/health
```
Expected: `{"status":"ok","version":"2.0.0",...}`

- [ ] **Step 10: Commit**

```bash
git add backend/main.py
git commit -m "feat: multi-stop, OASR, driver CRUD, flat rates, tracking, settings endpoints"
```

---

## Task 7: Rebuild booking.html

**Files:**
- Modify: `frontend/templates/booking.html` (full rebuild)

- [ ] **Step 1: Write the new booking.html**

Completely replace `frontend/templates/booking.html` with the new Uber Noir design. The file must include all of the following:

**Structure:**
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>Caledonia Taxi — Book a Ride</title>
  <link rel="stylesheet" href="/static/css/design-system.css">
  <link rel="manifest" href="/static/manifest.json">
  <!-- Leaflet, Stripe -->
</head>
<body>
  <div class="page-wrap">
    <!-- Header: logo + Call Us -->
    <header class="site-header">...</header>

    <!-- Service selector pills: Standard | Medical | Long Distance -->
    <div class="pill-row" id="serviceSelector">...</div>

    <!-- Step indicator: 1 · 2 · 3 · 4 -->
    <div class="step-indicator" id="stepIndicator">...</div>

    <!-- Step 1: Route + Customer -->
    <div id="step1" class="tab-panel active">
      <!-- Stop list: pickup, 0-3 stops, dropoff -->
      <!-- Long Distance city selector (hidden by default) -->
      <!-- Now/Schedule toggle -->
      <!-- Schedule datetime picker (hidden by default) -->
      <!-- Name + phone inputs -->
      <!-- Get Estimate CTA -->
    </div>

    <!-- Step 2: Fare Preview -->
    <div id="step2" class="tab-panel">
      <!-- Fare breakdown card (.fare-breakdown) -->
      <!-- Promo code input -->
      <!-- Surge banner (hidden by default) -->
      <!-- Payment method selector: Cash | Card -->
      <!-- Stripe card element (if card selected) -->
      <!-- Confirm Booking CTA -->
    </div>

    <!-- Step 3: Confirmed -->
    <div id="step3" class="tab-panel">
      <!-- Booking ID (mono) -->
      <!-- Route summary -->
      <!-- Status: awaiting driver / driver assigned -->
      <!-- Track ride link -->
      <!-- Rate driver CTA -->
    </div>

    <!-- Step 4: Rate Driver -->
    <div id="step4" class="tab-panel">
      <!-- 5-star selector -->
      <!-- Comment textarea -->
      <!-- Submit button -->
    </div>
  </div>

  <script src="https://js.stripe.com/v3/"></script>
  <script src="/static/js/fare-engine.js"></script>
  <script>
    // All inline JS — see detailed requirements below
  </script>
</body>
</html>
```

**JavaScript requirements for booking.html:**
- `let currentService = 'standard'` — updated when service pills clicked
- `let currentStep = 1` — `showStep(n)` updates step indicator and shows correct panel
- `let stops = []` — array of intermediate stop input values
- `addStop()` — appends a stop input row, max 3
- `removeStop(i)` — removes stop at index i
- `getLongDistanceCity()` — returns selected city from dropdown (long distance mode)
- `async function getEstimate()` — calls `POST /api/estimate-fare`, stores result in `currentBreakdown`, calls `renderFareBreakdown(breakdown)`
- `renderFareBreakdown(breakdown)` — renders `.fare-breakdown` div with one `.fare-row` per leg, then stop surcharge, then promo, then surge, then total in bold
- `async function applyPromo()` — re-calls `getEstimate()` with promo code
- `async function confirmBooking()` — calls `POST /api/bookings` with full payload; on success shows step 3
- `pollBookingStatus(id)` — polls `GET /api/bookings/{id}` every 5s, updates step 3 with driver info once dispatched
- `selectStar(n)` — updates star display
- `async function submitRating()` — calls `POST /api/bookings/{id}/rate`
- Surge banner: shown when `GET /api/surge` returns `multiplier > 1`, show amber badge with `{multiplier}x`
- Long distance: when service = 'long_distance', hide dropoff address input, show city picker dropdown populated from `GET /api/flat-rates`

- [ ] **Step 2: Test manually in browser**

Open http://localhost:8000 and verify:
- [ ] Service pills switch service type
- [ ] "+ Add Stop" adds an address input row
- [ ] "Get Estimate" calls the API and renders fare breakdown
- [ ] Promo code field applies discount to breakdown
- [ ] Long distance shows city picker, not address input
- [ ] "Confirm Booking" submits and shows step 3
- [ ] Step 3 shows booking ID in monospace font
- [ ] Star rating UI clickable in step 4

- [ ] **Step 3: Commit**

```bash
git add frontend/templates/booking.html
git commit -m "feat: rebuild booking.html with Uber Noir, multi-stop, service types, itemised fare"
```

---

## Task 8: Rebuild driver.html

**Files:**
- Modify: `frontend/templates/driver.html` (full rebuild)

- [ ] **Step 1: Write the new driver.html**

Completely replace `frontend/templates/driver.html`. Key sections:

**Login screen** (shown by default, hidden after login):
- `.login-page` centered layout
- Logo, "Driver Portal" subtitle
- Phone + PIN form-inputs
- White "Sign In" btn-primary
- Error message div

**Dashboard** (hidden until login):
- Header bar: driver name + status dot + earnings
- Status toggle: three equal `.btn` buttons — Available / Busy / Offline
- Stats row: trips today | avg rating | acceptance rate
- GPS badge button — toggles GPS on/off

**Incoming ride modal** (`.modal` overlay, slides up on dispatch):
- Service badge (badge-blue for medical, badge-white for standard, badge-amber for long distance)
- Customer name (h2) + phone (tap-to-call link)
- Stop list (.stop-item rows for pickup → stops → dropoff)
- Total distance + estimated fare
- Fare breakdown toggle (show/hide)
- SVG countdown ring (30 sec)
- Accept (btn-primary full) + Decline (btn-secondary full)

**Active ride panel** (shown after accept):
- Leg list (.leg-item rows) — current leg has `.leg-status.current`
- "+ Add Stop" button opens a bottom drawer with address input
- Live fare display (updates when stop added)
- "Start Trip" button (shows only when status = accepted, before in_progress)
- "Complete Ride" button (shows only when on last leg, status = in_progress)

**JavaScript requirements:**
- WebSocket connection to `/ws/driver/{id}` on login success
- On `new_booking_request` WS message: populate modal, start countdown, play ringtone
- `acceptRide(bookingId)` → `POST /api/rides/{id}/action/{driverId}` with action=accept; show active ride panel
- `declineRide()` → POST with action=decline; hide modal, restart countdown to 0
- `startTrip()` → `POST /api/rides/{id}/start/{driverId}`; update leg status
- `completeRide()` → `POST /api/rides/{id}/complete/{driverId}`; hide active panel, return to dashboard, update earnings
- `addLiveStop(address)` → `POST /api/bookings/{id}/stops`; update leg list + fare display
- GPS: `navigator.geolocation.watchPosition()` sends `{type:"location_update", lat, lng}` via WS
- Push notification: same VAPID logic as existing code — keep it
- Ringtone: same Web Audio API as existing code — keep it

- [ ] **Step 2: Test manually in browser**

Open http://localhost:8000/driver, log in as +12895551001 / 1234. Verify:
- [ ] Login shows dashboard after success
- [ ] Status toggle changes between Available/Busy/Offline
- [ ] GPS badge shows active/inactive state
- [ ] When a booking is dispatched from http://localhost:8000, the ride request modal appears
- [ ] Accept button transitions to active ride panel

- [ ] **Step 3: Commit**

```bash
git add frontend/templates/driver.html
git commit -m "feat: rebuild driver.html with Uber Noir, multi-leg active ride, add-stop flow"
```

---

## Task 9: Rebuild admin.html

**Files:**
- Modify: `frontend/templates/admin.html` (full rebuild)

This is the largest template. Build tab by tab.

- [ ] **Step 1: Write the admin shell + login + nav**

The admin.html shell:
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Caledonia Taxi — Admin</title>
  <link rel="stylesheet" href="/static/css/design-system.css">
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
</head>
<body>

<!-- LOGIN GATE (shown if not authenticated) -->
<div id="loginGate" class="login-page">
  <div class="login-box">
    <div class="login-logo">Caledonia Taxi</div>
    <h1 class="login-title">Admin</h1>
    <p class="login-sub">Sign in to the operations dashboard</p>
    <div class="form-group">
      <label class="form-label">Password</label>
      <input type="password" id="adminPassword" class="form-input" placeholder="Enter admin password">
    </div>
    <div id="loginError" class="error-msg"></div>
    <button onclick="adminLogin()" class="btn btn-primary btn-full" style="margin-top:16px">Sign In</button>
  </div>
</div>

<!-- ADMIN PANEL (hidden until authenticated) -->
<div id="adminPanel" style="display:none">
  <div class="page-wrap--wide">
    <header class="site-header">
      <span class="site-logo">Caledonia Taxi — Admin</span>
      <a href="/admin/logout" class="site-header-action">Sign out</a>
    </header>

    <!-- Tab bar -->
    <div class="tab-bar">
      <button class="tab-btn active" onclick="switchTab('dashboard')">Dashboard</button>
      <button class="tab-btn" onclick="switchTab('orders')">Orders</button>
      <button class="tab-btn" onclick="switchTab('tracking')">Tracking</button>
      <button class="tab-btn" onclick="switchTab('oasr')">OASR</button>
      <button class="tab-btn" onclick="switchTab('revenue')">Revenue</button>
      <button class="tab-btn" onclick="switchTab('drivers')">Drivers</button>
      <button class="tab-btn" onclick="switchTab('receipts')">Receipts</button>
      <button class="tab-btn" onclick="switchTab('settings')">Settings</button>
    </div>

    <!-- Tab panels: dashboard, orders, tracking, oasr, revenue, drivers, receipts, settings -->
    ...
  </div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://cdn.sheetjs.com/xlsx-0.20.2/package/dist/xlsx.full.min.js"></script>
<script>/* all JS inline */</script>
</body>
</html>
```

- [ ] **Step 2: Dashboard tab**

KPI grid (`.kpi-grid`) with 4 cards: Today's Bookings, Today's Revenue, Active Drivers, Pending.
Activity feed: `<div id="activityFeed">` updated via WebSocket `admin` channel.
Quick dispatch: table of pending bookings with driver dropdown + "Assign" button per row.
Data loaded from `GET /api/admin/stats` on tab open.

- [ ] **Step 3: Orders tab**

Filter row: All | Pending | Dispatched | Active | Completed | Cancelled
Period row: Today | Week | Month | All Time
Data table with columns: ID | Type | Customer | Route | Status | Driver | Fare | Time
Row actions: receipt icon, cancel button
Excel export via SheetJS: `exportOrdersExcel()`
Data: `GET /api/bookings` with status filter as query param

- [ ] **Step 4: Tracking tab (Leaflet map)**

```html
<div id="trackingTab" class="tab-panel">
  <div id="trackingMap" style="height: calc(100vh - 200px);" class="map-container"></div>
  <div id="driverDrawer" class="right-drawer">
    <button onclick="closeDriverDrawer()" class="drawer-close">×</button>
    <div id="driverDrawerContent"></div>
  </div>
</div>
```

JavaScript for the Tracking tab:
```js
let trackingMap = null;
let driverMarkers = {};

function initTrackingMap() {
  if (trackingMap) return;
  trackingMap = L.map('trackingMap').setView([43.0773, -79.9408], 11);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '© CartoDB', maxZoom: 19
  }).addTo(trackingMap);
}

async function refreshDriverLocations() {
  const drivers = await fetch('/api/admin/driver-locations').then(r => r.json());
  drivers.forEach(d => {
    const color = d.status === 'available' ? '#22C55E' : d.status === 'busy' ? '#F59E0B' : '#444';
    const icon = L.divIcon({
      className: '',
      html: `<div style="width:14px;height:14px;border-radius:50%;background:${color};border:2px solid #000;box-shadow:0 0 6px ${color}44"></div>`,
      iconSize: [14, 14], iconAnchor: [7, 7]
    });
    if (driverMarkers[d.id]) {
      driverMarkers[d.id].setLatLng([d.lat, d.lng]).setIcon(icon);
    } else {
      driverMarkers[d.id] = L.marker([d.lat, d.lng], { icon })
        .addTo(trackingMap)
        .on('click', () => showDriverDrawer(d));
    }
  });
}

function showDriverDrawer(d) {
  const el = document.getElementById('driverDrawerContent');
  el.innerHTML = `
    <h3>${d.name}</h3>
    <p style="color:var(--text-secondary);margin:4px 0 16px">${d.vehicle} · ${d.plate}</p>
    <span class="badge badge-${d.status === 'available' ? 'green' : d.status === 'busy' ? 'amber' : 'grey'}">${d.status}</span>
    ${d.active_booking ? `
      <div class="divider"></div>
      <div class="label">Active Ride</div>
      <p style="margin-top:8px">${d.active_booking.customer_name}</p>
      <p style="color:var(--text-secondary);font-size:.8rem;margin-top:4px">${d.active_booking.pickup_address} → ${d.active_booking.dropoff_address}</p>
      <p style="margin-top:8px">Fare: $${d.active_booking.estimated_fare}</p>
    ` : '<p style="color:var(--text-secondary);margin-top:12px">No active ride</p>'}
    <div class="divider"></div>
    <a href="tel:${d.phone}" class="btn btn-secondary btn-full btn-sm">📞 Call Driver</a>
  `;
  document.getElementById('driverDrawer').classList.add('open');
}
```

Auto-refresh: `setInterval(refreshDriverLocations, 10000)` when tracking tab is active.

- [ ] **Step 5: OASR tab**

```html
<div id="oasrTab" class="tab-panel">
  <!-- Manual parse form -->
  <div class="card" style="margin-bottom:20px">
    <h3 style="margin-bottom:12px">Parse Incoming Email</h3>
    <div class="form-group">
      <label class="form-label">Paste OASR email text</label>
      <textarea id="oasrEmailText" class="form-input" rows="6" placeholder="Paste the full email text here..."></textarea>
    </div>
    <button onclick="parseOasrEmail()" class="btn btn-primary">Parse & Create Booking</button>
    <div id="oasrParseResult" class="success-msg" style="margin-top:8px"></div>
  </div>

  <!-- OASR bookings list -->
  <div id="oasrList"></div>
</div>
```

JS: `parseOasrEmail()` posts to `/api/oasr/inbound`, shows result. `loadOasrBookings()` loads from `/api/admin/oasr`, renders table with status badges (needs_review = red, scheduled = amber, etc).

- [ ] **Step 6: Revenue tab**

Period selector buttons. Chart as CSS bars (pure CSS `.bar-chart`). Daily breakdown table. Service split row. Excel export. Data from `GET /api/admin/revenue`.

- [ ] **Step 7: Drivers tab**

Driver cards grid. Each card: name, vehicle, plate, status badge, KPIs (total trips, earnings, acceptance rate, avg rating). "Edit" opens a bottom drawer with form. "Add Driver" button opens drawer with blank form. "Deactivate" calls PATCH endpoint after confirm dialog. Load from `GET /api/drivers`.

- [ ] **Step 8: Receipts tab**

Filter controls (driver, date range, service type). Table of completed bookings. PDF download per row calls `GET /api/bookings/{id}/receipt`. Excel export via SheetJS.

- [ ] **Step 9: Settings tab**

Four sections as cards:
1. **Pricing** — editable inputs for base_fare, per_km_rate, minimum_fare, stop_surcharge. Save button.
2. **Long Distance Flat Rates** — table with destination + price + delete button. "Add Destination" form row.
3. **Promo Codes** — list of active promos, toggle active/inactive, add new.
4. **Surge Pricing** — toggle enabled, threshold inputs, multiplier inputs. Save button.

All sections call `POST /api/admin/settings` with the full settings object. Load on tab open from `GET /api/admin/settings`.

- [ ] **Step 10: Test admin panel**

Open http://localhost:8000/admin, log in with `admin1234`. Verify:
- [ ] All 8 tabs switch correctly
- [ ] Dashboard shows KPI cards
- [ ] Tracking tab shows Leaflet map, driver pins
- [ ] OASR tab: paste sample email text, click Parse
- [ ] Settings tab loads flat rates, can save
- [ ] Drivers tab shows driver cards, Edit drawer opens
- [ ] Orders table shows bookings with status badges

- [ ] **Step 11: Commit**

```bash
git add frontend/templates/admin.html
git commit -m "feat: rebuild admin.html — 8 tabs, Tracking map, OASR, Settings, Drivers CRUD"
```

---

## Task 10: Integration, Final Tests & Deployment Verification

**Files:**
- Check: all templates, backend

- [ ] **Step 1: End-to-end booking flow test**

1. Open http://localhost:8000 (or https://interface-sticker-debian-vacation.trycloudflare.com)
2. Select "Long Distance" service — verify city picker appears, fare shows flat rate
3. Add a stop — verify stop list updates, Get Estimate recalculates with stop surcharge
4. Get Estimate — verify itemised fare breakdown renders correctly
5. Apply promo code FIRST10 — verify 10% discount line appears
6. Confirm booking (cash) — verify step 3 shows booking ID

- [ ] **Step 2: Driver flow test**

1. Open http://localhost:8000/driver in a second tab
2. Log in as +12895551001 / 1234
3. Set status to Available
4. Go back to booking tab, complete a booking
5. Verify driver tab receives the incoming ride request modal
6. Accept ride — verify active ride panel appears with leg list
7. Click "+ Add Stop" — enter an address — verify fare updates

- [ ] **Step 3: Admin tracking test**

1. Open http://localhost:8000/admin
2. Click Tracking tab
3. Verify map loads with CartoDB dark tiles
4. Verify driver pin appears at Caledonia coords
5. Click driver pin — verify right drawer opens with driver info

- [ ] **Step 4: OASR parse test**

Go to Admin → OASR tab. Paste this sample text:
```
Patient: John Smith
Pickup: 123 Argyle St North, Caledonia ON
Destination: McMaster University Medical Centre, 1280 Main St W, Hamilton ON
Date: March 25, 2026
Time: 9:30 AM
Notes: Wheelchair accessible vehicle required
```
Click "Parse & Create Booking". Verify confidence = 5, booking created.

- [ ] **Step 5: Verify Cloudflare tunnel still live**

```bash
curl -s https://interface-sticker-debian-vacation.trycloudflare.com/health
```
Expected: `{"status":"ok",...}`

- [ ] **Step 6: Final commit + tag**

```bash
git add -A
git status  # review — no .env or secrets
git commit -m "feat: full platform redesign — Uber Noir UI, multi-stop fares, OASR automation, live tracking"
git tag v3.0.0
```
