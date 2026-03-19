# Caledonia Taxi — Production Launch Checklist

Complete every item before going live. Items are ordered by priority.

---

## 1. Secrets & Credentials (CRITICAL)

- [ ] **APP_SECRET_KEY** — replace the default with a 64-char random hex string
  ```
  python3 -c "import secrets; print(secrets.token_hex(32))"
  ```
- [ ] **ADMIN_PASSWORD** — set a strong password (16+ characters, mixed case + symbols)
- [ ] **COOKIE_SECURE=true** — enables `Secure` flag on session cookie (requires HTTPS)
- [ ] **SUPABASE_URL / SUPABASE_KEY / SUPABASE_SERVICE_KEY** — production project credentials
- [ ] **TWILIO** credentials confirmed active and pointed at a live phone number
- [ ] **STRIPE_SECRET_KEY** — switch from `sk_test_...` to `sk_live_...`
- [ ] **STRIPE_PUBLISHABLE_KEY** — switch from `pk_test_...` to `pk_live_...`
- [ ] **VAPID keys** — generate a fresh pair for production (see `.env.example` command)
- [ ] **.env is in .gitignore** — verify `git status` shows `.env` as untracked/ignored

---

## 2. CORS / Allowed Origins

- [ ] Add your production domain to `ALLOWED_ORIGINS` in `.env`:
  ```
  ALLOWED_ORIGINS=https://caledoniataxihamil.ca,https://www.caledoniataxihamil.ca
  ```
- [ ] Remove `http://localhost:8000` from `ALLOWED_ORIGINS` on the production server

---

## 3. HTTPS / TLS

- [ ] Deploy behind **nginx** or **Caddy** as a reverse proxy with a valid TLS certificate
  - Caddy auto-provisions Let's Encrypt certs (recommended for VPS)
  - Or use Cloudflare proxy in front of your server (free, easy)
- [ ] Confirm `COOKIE_SECURE=true` is set after HTTPS is working
- [ ] HSTS header is automatically added by the app when `COOKIE_SECURE=true`

---

## 4. Database

- [ ] Supabase project is on a paid plan (free tier pauses after 1 week of inactivity)
- [ ] Row-Level Security (RLS) enabled on all tables containing customer data
- [ ] Database backups are configured in Supabase dashboard
- [ ] Run the full schema migration on the production project (not just demo data)

---

## 5. Stripe Payments

- [ ] Stripe account is fully verified (identity, bank account)
- [ ] Live mode keys are active (not test mode)
- [ ] Stripe Radar fraud rules reviewed
- [ ] Test a real card payment end-to-end before launch
- [ ] Set up Stripe webhook (optional but recommended for payment confirmation):
  - Endpoint: `POST /api/stripe/webhook`
  - Events: `payment_intent.succeeded`, `payment_intent.payment_failed`

---

## 6. Web Push (Driver Notifications)

- [ ] VAPID keys in `.env` are the production-generated pair (not the dev defaults)
- [ ] `VAPID_SUBJECT` set to your real admin email (`mailto:admin@yourdomain.com`)
- [ ] Test push notification end-to-end on a real Android/iOS device:
  1. Driver logs in, grants notification permission
  2. Admin dispatches a booking
  3. Driver receives OS notification even with browser minimised

---

## 7. Process Management

- [ ] Run the app with a process manager — do **not** use `uvicorn` directly in production:

  **Option A: systemd (recommended for VPS)**
  ```ini
  # /etc/systemd/system/caledonia-taxi.service
  [Unit]
  Description=Caledonia Taxi API
  After=network.target

  [Service]
  User=www-data
  WorkingDirectory=/opt/caledonia-taxi
  EnvironmentFile=/opt/caledonia-taxi/.env
  ExecStart=/opt/caledonia-taxi/venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 2
  Restart=always
  RestartSec=5

  [Install]
  WantedBy=multi-user.target
  ```
  ```bash
  sudo systemctl enable caledonia-taxi
  sudo systemctl start caledonia-taxi
  ```

  **Option B: Docker**
  ```dockerfile
  FROM python:3.11-slim
  WORKDIR /app
  COPY requirements.txt .
  RUN pip install --no-cache-dir -r requirements.txt
  COPY . .
  CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
  ```

---

## 8. Logging & Monitoring

- [ ] App logs are written to a file or forwarded to a service (e.g., Papertrail, Logtail)
  - uvicorn logs go to stdout — systemd captures them via `journalctl -u caledonia-taxi`
- [ ] Set up uptime monitoring (free options: UptimeRobot, BetterStack)
  - Monitor endpoint: `GET /health` — returns `{"status": "ok"}`
- [ ] Alert on 5xx error rate increase

---

## 9. APScheduler (Advance Bookings)

- [ ] APScheduler runs in-process — confirm it starts cleanly in the systemd logs
- [ ] Test a scheduled booking end-to-end (book 30+ minutes in advance, wait for dispatch)
- [ ] If scaling to multiple workers (Gunicorn), move scheduler to a separate process or use
  `APScheduler` with a database job store (PostgreSQL) to avoid duplicate dispatches

---

## 10. Promo Codes

- [ ] Update `PROMO_CODES` in `.env` to your real launch codes:
  ```
  PROMO_CODES=LAUNCH15:15,VIP30:30
  ```
- [ ] Remove or expire codes after campaign ends (redeploy with updated env var)

---

## 11. Pre-Launch Smoke Test

Run through each flow manually the day before launch:

- [ ] Book a ride (cash payment)
- [ ] Book a ride (Stripe card payment)
- [ ] Book a scheduled ride (30+ min in advance)
- [ ] Apply a promo code during booking
- [ ] Driver accepts a ride
- [ ] Admin dispatches manually
- [ ] Admin exports Orders to Excel
- [ ] Driver push notification received on mobile
- [ ] Admin login rate limiting (attempt 11 logins in 60s — should get 429)
- [ ] `GET /health` returns 200

---

## 12. DNS & Domain

- [ ] DNS A record points to production server IP
- [ ] `www` subdomain redirects to apex (or vice versa) — configure in nginx/Caddy
- [ ] SSL certificate is valid and auto-renewing

---

## Quick Reference — Key URLs

| Path | Description |
|------|-------------|
| `/` | Booking page (customers) |
| `/driver` | Driver app |
| `/admin` | Admin panel |
| `/health` | Health check (uptime monitor target) |
| `/api/surge` | Current surge multiplier |

---

*Last updated: 2026-03-17*
