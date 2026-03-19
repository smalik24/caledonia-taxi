# Caledonia Taxi

Caledonia, Ontario's modern taxi dispatch platform.

## Project Structure

```
caledonia-taxi-project/
├── main.py                  # FastAPI app — all routes
├── scheduler.py             # Background job scheduler
├── invoice_service.py       # Invoice generation
├── oasr_parser.py           # OASR file parser
├── database_schema.sql      # Supabase DB schema
├── requirements.txt
├── .env.example             # Copy to .env and fill in
│
├── frontend/
│   ├── templates/           # Jinja2 HTML templates (served by FastAPI)
│   │   ├── index.html       # Public landing page
│   │   ├── booking.html     # Booking flow (3 steps)
│   │   ├── driver.html      # Driver mobile app
│   │   ├── admin.html       # Admin dispatch dashboard
│   │   ├── track.html       # Ride tracking page
│   │   └── heatmap.html     # Demand heatmap
│   └── static/
│       └── css/
│           ├── tokens.css   # Design tokens (colors, spacing, typography)
│           └── base.css     # Base component styles
│
└── site-preview/            # Standalone demo (no backend needed)
    ├── index.html           # All CSS inlined, works without FastAPI
    └── ...
```

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy and fill in environment variables
cp .env.example .env

# 3. Run database schema in Supabase SQL editor
#    (open database_schema.sql and run it)

# 4. Start the server
uvicorn main:app --reload

# 5. Open in browser
open http://localhost:8000
```

## Pages & Routes

| Route | Description |
|-------|-------------|
| `/` | Public landing page |
| `/booking` | Booking flow |
| `/driver` | Driver app (mobile-first) |
| `/admin` | Dispatch dashboard (password: admin1234) |
| `/track/{booking_id}` | Ride tracking |
| `/heatmap` | Demand heatmap |

## Demo Credentials

- **Admin password:** admin1234
- **Driver phone:** +12895551001
- **Driver PIN:** 1234

## Design System

- **Colors:** Off-white #f8f8f6 + Amber gold #F0A500 + Charcoal #111110
- **Dark mode:** Toggle via moon icon — uses `data-theme="dark"` attribute
- **Icons:** Lucide Icons (CDN)
- **Fonts:** Inter / SF Pro (system fonts)

## Handoff Notes for Claude Code

- All 6 HTML templates are Jinja2 — use `{{ variable }}` syntax for dynamic data
- Backend connects to Supabase — tables: `drivers`, `bookings`, `dispatch_log`
- The `site-preview/` folder is a static demo with all CSS inlined (no FastAPI needed)
- main.py has all API routes — extend from there
