# Caledonia Taxi — Booking & Dispatch System (MVP)

## What Was Built

A complete, working MVP of a taxi booking and dispatch system with 4 components:

### 1. Customer Booking Web App (`/`)
- Clean, branded booking page for Caledonia Taxi
- 3-step flow: Enter details → See fare estimate → Confirm booking
- Calculates estimated fare based on distance (base fare $4.50 + $2.10/km, minimum $8.00)
- Mobile-responsive design
- Booking auto-dispatches to the nearest available driver

### 2. Driver Dispatch App (`/driver`)
- Mobile-friendly web page drivers open on their phones
- PIN-based login (phone number + 4-digit PIN)
- Real-time ride requests via WebSocket with 30-second countdown timer
- Accept/Decline rides
- Status toggle: Available / Busy / Offline
- Active ride tracking: "Customer Picked Up" → "Ride Completed" flow
- GPS location updates (every 30 seconds)
- If a driver declines or doesn't respond in 30 seconds, the ride auto-routes to the next nearest driver

### 3. Admin Panel (`/admin`)
- Dashboard with live stats (total bookings, pending, active, completed, driver status)
- View all bookings with filtering (pending, dispatched, accepted, in_progress, completed, cancelled)
- See all driver statuses in real time
- Manually assign a ride to any available driver
- Cancel bookings
- Real-time WebSocket updates — no need to refresh
- Auto-refreshes every 10 seconds

### 4. AI Phone Agent (Twilio)
- Customers call and speak to an automated voice agent
- Collects pickup address, drop-off address via speech recognition
- Calculates and reads back the estimated fare
- Confirms booking on "yes"
- Creates booking and dispatches to nearest driver
- Uses Twilio's built-in Gather/Say (no extra STT/TTS costs)

---

## Tech Stack
| Component | Technology |
|-----------|-----------|
| Backend | Python / FastAPI |
| Frontend | HTML / CSS / JavaScript (no framework — fast & simple) |
| Database | Supabase (or in-memory demo mode) |
| Real-time | WebSockets (built into FastAPI) |
| Maps/Distance | OpenRouteService (free) — falls back to Haversine |
| Phone Agent | Twilio (pay-as-you-go) |
| Fare Calc | Base fare + per-km rate |

---

## How to Run

### Quick Start (Demo Mode — no API keys needed)
```bash
cd caledonia-taxi
pip install -r requirements.txt
./run.sh
```

Then open:
- **Customer booking:** http://localhost:8000
- **Driver app:** http://localhost:8000/driver
- **Admin panel:** http://localhost:8000/admin
- **API docs:** http://localhost:8000/docs

### Demo Driver Logins
| Driver | Phone | PIN |
|--------|-------|-----|
| Saqib (owner) | +12895551001 | 1234 |
| Driver 2 | +12895551002 | 2345 |
| Driver 3 | +12895551003 | 3456 |
| Driver 4 | +12895551004 | 4567 |

---

## API Keys You Need to Set Up

Edit the `.env` file with your keys:

### 1. Supabase (free tier)
- Sign up at https://supabase.com
- Create a new project
- Run `backend/database_schema.sql` in the SQL Editor
- Copy your project URL and anon key to `.env`
```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
```

### 2. OpenRouteService (free — 2000 requests/day)
- Sign up at https://openrouteservice.org/dev/#/signup
- Get your API key
```
ORS_API_KEY=your-key
```

### 3. Twilio (for phone agent — optional)
- Sign up at https://www.twilio.com
- Buy a local number (~$1.15/month)
- Set voice webhook to: `https://your-domain.com/api/twilio/voice`
```
TWILIO_ACCOUNT_SID=ACxxxxxxxxxx
TWILIO_AUTH_TOKEN=your-token
TWILIO_PHONE_NUMBER=+1289xxxxxxx
```

---

## Project Structure
```
caledonia-taxi/
├── .env                    # Environment variables (edit this)
├── .env.example            # Template
├── requirements.txt        # Python dependencies
├── run.sh                  # Start script
├── DONE.md                 # This file
├── backend/
│   ├── main.py             # FastAPI app — all API routes, WebSockets, Twilio webhooks
│   ├── config.py           # Configuration from .env
│   ├── models.py           # Pydantic request/response models
│   ├── services.py         # Geocoding, fare calc, dispatch logic
│   └── database_schema.sql # Supabase SQL schema
├── frontend/
│   ├── templates/
│   │   ├── booking.html    # Customer booking page
│   │   ├── driver.html     # Driver dispatch app
│   │   └── admin.html      # Admin panel
│   └── static/
│       └── css/
│           └── style.css   # Global styles
└── phone-agent/
    └── README.md           # Phone agent setup guide
```

---

## Deployment (Free/Cheap Options)

### Option A: Railway (recommended)
```bash
# Install Railway CLI
npm i -g @railway/cli
railway login
railway init
railway up
```
Cost: Free tier (500 hours/month)

### Option B: Render
- Push to GitHub
- Connect to Render.com
- Set build command: `pip install -r requirements.txt`
- Set start command: `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT`
Cost: Free tier available

### Option C: VPS (DigitalOcean/Linode)
- $4-6/month for a basic droplet
- Full control, run with systemd

---

## Monthly Cost Estimate (MVP)
| Service | Cost |
|---------|------|
| Hosting (Railway free tier) | $0 |
| Supabase (free tier) | $0 |
| OpenRouteService (free tier) | $0 |
| Twilio phone number | ~$1.15/month |
| Twilio calls (~100 calls × 2 min) | ~$1.70/month |
| **Total** | **~$2.85/month** |

---

## Next Steps to Scale
1. Add SMS notifications to customers when driver is dispatched/arriving
2. Add payment integration (Stripe)
3. Add ride history for customers
4. Add earnings tracking for drivers
5. Upgrade phone agent to use OpenAI Whisper for better speech recognition
6. Add surge pricing for peak hours
7. Add driver ratings
8. Native mobile app (React Native)
