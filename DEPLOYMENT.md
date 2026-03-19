# Caledonia Taxi — Deployment Guide

## Prerequisites
- Python 3.11+
- A Render.com account (or any Docker host)
- Accounts: Supabase, Stripe, Twilio, Resend, Vapi (all optional — app runs in demo mode without them)

---

## 1. Supabase Setup

1. Go to [supabase.com](https://supabase.com) → New Project → name it `caledonia-taxi`
2. Once provisioned, go to **Settings → API** and copy:
   - `Project URL` → `SUPABASE_URL`
   - `anon public` key → `SUPABASE_KEY`
   - `service_role` key → `SUPABASE_SERVICE_KEY`
3. Go to **SQL Editor** → paste the contents of `backend/database_schema.sql` → Run
4. Verify tables created: `bookings`, `drivers`, `driver_locations`, `booking_events`, `sos_events`, `sms_log`, `analytics_cache`, `fare_config`

---

## 2. Stripe Setup

1. Go to [dashboard.stripe.com](https://dashboard.stripe.com) → create account or log in
2. Enable **Test Mode** (toggle top-right)
3. Go to **Developers → API Keys** → copy:
   - `Secret key` (sk_test_...) → `STRIPE_SECRET_KEY`
   - `Publishable key` (pk_test_...) → `STRIPE_PUBLISHABLE_KEY`
4. Go to **Developers → Webhooks** → Add endpoint:
   - URL: `https://your-domain.com/api/stripe/webhook`
   - Events: `payment_intent.succeeded`, `payment_intent.payment_failed`, `charge.refunded`
   - Copy **Signing secret** → `STRIPE_WEBHOOK_SECRET`

---

## 3. Twilio Setup

1. Go to [console.twilio.com](https://console.twilio.com) → create account
2. Get a phone number (Canadian +1289 area code preferred)
3. From **Account Info** copy:
   - Account SID → `TWILIO_ACCOUNT_SID`
   - Auth Token → `TWILIO_AUTH_TOKEN`
   - Phone number → `TWILIO_PHONE_NUMBER` (format: `+12895551000`)
4. Configure inbound SMS webhook:
   - Twilio Console → Phone Numbers → your number → Messaging → Webhook: `https://your-domain.com/sms/inbound`

---

## 4. Resend Setup

1. Go to [resend.com](https://resend.com) → create account
2. **Domains** → Add domain → verify DNS records (SPF, DKIM)
3. **API Keys** → Create key → copy → `RESEND_API_KEY`
4. Update `FROM_EMAIL` in `backend/config.py` to match your verified domain

---

## 5. Vapi Voice AI Setup

1. Go to [vapi.ai](https://vapi.ai) → create account
2. Copy your **API Key** → `VAPI_API_KEY`
3. Run the setup script (creates assistant with all tool functions):
   ```bash
   VAPI_API_KEY=your_key python backend/setup_vapi.py
   ```
4. Copy the returned `assistant_id` → `VAPI_ASSISTANT_ID`
5. In Vapi dashboard, set webhook URL: `https://your-domain.com/vapi/webhook`

---

## 6. Render.com Deployment

1. Push your code to GitHub
2. Go to [render.com](https://render.com) → New → Web Service → Connect GitHub repo
3. Configure:
   - **Name**: `caledonia-taxi`
   - **Root Directory**: leave blank (uses repo root)
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Or use `render.yaml` (already in repo) → Render auto-detects it
5. Add environment variables (Settings → Environment):
   ```
   SUPABASE_URL=https://xxx.supabase.co
   SUPABASE_KEY=eyJ...
   SUPABASE_SERVICE_KEY=eyJ...
   STRIPE_SECRET_KEY=sk_live_...
   STRIPE_PUBLISHABLE_KEY=pk_live_...
   TWILIO_ACCOUNT_SID=AC...
   TWILIO_AUTH_TOKEN=...
   TWILIO_PHONE_NUMBER=+12895551000
   RESEND_API_KEY=re_...
   VAPI_API_KEY=...
   VAPI_ASSISTANT_ID=...
   APP_SECRET_KEY=<random 64-char string>
   ADMIN_PASSWORD=<strong password>
   DEMO_MODE=false
   COOKIE_SECURE=true
   ```
6. Deploy → watch build logs → green = live

---

## 7. Custom Domain

1. Render Dashboard → your service → Settings → Custom Domains → Add
2. Add a CNAME record at your DNS provider pointing to `your-service.onrender.com`
3. Render auto-provisions TLS (Let's Encrypt)
4. Update Twilio + Vapi webhooks to use your custom domain

---

## 8. Go-Live Checklist

### Backend
- [ ] `GET /health` returns `{"status": "ok", "demo_mode": false}`
- [ ] All service statuses green: `database`, `stripe`, `twilio`, `resend`
- [ ] `python -c "import sys; sys.path.insert(0,'backend'); import main"` passes

### Booking Flow
- [ ] Create a test booking at `/booking`
- [ ] SMS confirmation received
- [ ] Driver app at `/driver` shows the booking
- [ ] Driver accepts — customer tracking page updates
- [ ] Trip completed — PDF receipt generated
- [ ] Receipt email sent via Resend

### Payments
- [ ] Create booking with payment → Stripe PaymentIntent created
- [ ] Stripe test card `4242 4242 4242 4242` → payment succeeded
- [ ] Stripe webhook fires → booking payment status updated

### Admin
- [ ] Login at `/admin` with `ADMIN_PASSWORD`
- [ ] Live dispatch map shows driver locations
- [ ] Analytics charts load (revenue, bookings, acceptance rate)
- [ ] Can manually assign driver to booking
- [ ] SOS alerts appear in dispatch board

### Voice AI
- [ ] Call Vapi assistant → ask for fare estimate → correct quote returned
- [ ] Complete booking via voice → appears in admin dashboard

---

## Docker (Alternative)

```bash
docker build -t caledonia-taxi .
docker run -p 8000:8000 \
  -e DEMO_MODE=false \
  -e SUPABASE_URL=... \
  -e ADMIN_PASSWORD=... \
  caledonia-taxi
```

---

## Monitoring

- Render provides free log tailing: Dashboard → Logs
- `/health` endpoint can be monitored with UptimeRobot (free)
- Set up alert: if `/health` returns non-200 → email/SMS alert
