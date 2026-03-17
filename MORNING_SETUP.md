# Morning Setup Guide — Caledonia Taxi v2.0
> Complete these steps to go from mock → live production.

---

## 1. Install New Dependencies

```bash
pip3 install -r requirements.txt
```

This adds `reportlab` for PDF generation. All other deps were already present.

---

## 2. Enable Real SMS (Twilio)

**Cost:** ~$1.15/month for a number + ~$0.0079/SMS

### Steps:
1. Go to [twilio.com](https://www.twilio.com) → sign up / log in
2. Get a Canadian phone number (Hamilton area code: 289 or 905)
3. Copy your credentials from the Twilio Console dashboard

### Update `.env`:
```env
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_PHONE_NUMBER=+12895550000
```

### Update `backend/sms_service.py`:

Replace the `_send_mock()` function body:

```python
def _send_mock(to_phone: str, message: str) -> dict:
    # PRODUCTION: Replace mock with real Twilio call
    from twilio.rest import Client
    import os
    client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
    twilio_msg = client.messages.create(
        body=message,
        from_=os.getenv("TWILIO_PHONE_NUMBER"),
        to=to_phone
    )
    entry = {
        "id": twilio_msg.sid,
        "to": to_phone,
        "message": message,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "status": twilio_msg.status,
        "provider": "Twilio"
    }
    _sms_log.append(entry)
    logger.info(f"[SMS] Sent via Twilio to {to_phone}: SID={twilio_msg.sid}")
    return entry
```

---

## 3. Enable Real Email (Resend)

**Cost:** Free tier = 3,000 emails/month. $20/month for 50k.

### Steps:
1. Go to [resend.com](https://resend.com) → sign up
2. Add your domain (or use their sandbox for testing)
3. Get your API key

### Update `.env`:
```env
RESEND_API_KEY=re_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
FROM_EMAIL=receipts@caledonia.taxi
```

### Update `backend/invoice_service.py`:

Replace the `_send_email_mock()` function body:

```python
def _send_email_mock(to_email, subject, body, attachments=None):
    # PRODUCTION: Replace mock with real Resend call
    import resend, os, base64
    resend.api_key = os.getenv("RESEND_API_KEY")

    params = {
        "from": os.getenv("FROM_EMAIL", "receipts@caledonia.taxi"),
        "to": [to_email],
        "subject": subject,
        "text": body,
    }
    if attachments:
        params["attachments"] = [
            {
                "filename": a["filename"],
                "content": base64.b64encode(a["data"]).decode()
            }
            for a in attachments
        ]

    response = resend.Emails.send(params)
    entry = {
        "id": response.get("id"),
        "to": to_email,
        "subject": subject,
        "body_preview": body[:200],
        "has_attachment": bool(attachments),
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "status": "sent",
        "provider": "Resend"
    }
    _email_log.append(entry)
    return entry
```

Install Resend: `pip3 install resend`

---

## 4. Enable Real Maps / Geocoding (OpenRouteService)

**Cost:** Free tier = 2,000 requests/day

### Steps:
1. Go to [openrouteservice.org](https://openrouteservice.org) → sign up
2. Create a token in the dashboard

### Update `.env`:
```env
ORS_API_KEY=your_ors_key_here
```

No code changes needed — already supported in `services.py`.

---

## 5. Enable Supabase Database

**Cost:** Free tier = plenty for MVP

### Steps:
1. Go to [supabase.com](https://supabase.com) → New Project
2. Run `backend/database_schema.sql` in the SQL editor
3. Get your URL and keys from Project Settings → API

### Update `.env`:
```env
SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

No code changes needed — already supported in `main.py`.

---

## 6. Connect a Voice AI Agent

Your system now has 3 Voice AI endpoints:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/voice-ai/booking` | POST | Agent posts a completed booking |
| `/api/voice-ai/status/{id}` | GET | Agent checks ride status |
| `/api/voice-ai/fare-estimate` | POST | Agent gets fare for readback |

### Recommended Voice AI Platforms:
- **[Vapi.ai](https://vapi.ai)** — best for real-time voice agents
- **[Bland.ai](https://bland.ai)** — simple outbound call automation
- **[Retell AI](https://retellai.com)** — conversational AI calls

### Vapi Example Tool Definition:
```json
{
  "type": "function",
  "function": {
    "name": "create_taxi_booking",
    "description": "Create a taxi booking for the customer",
    "parameters": {
      "type": "object",
      "properties": {
        "customer_name":   { "type": "string" },
        "customer_phone":  { "type": "string" },
        "pickup_address":  { "type": "string" },
        "dropoff_address": { "type": "string" },
        "notes":           { "type": "string" }
      },
      "required": ["customer_name","customer_phone","pickup_address","dropoff_address"]
    }
  },
  "server": {
    "url": "https://your-domain.com/api/voice-ai/booking"
  }
}
```

---

## 7. Add Driver Vehicles to Database

Add these columns to the `drivers` table in Supabase:

```sql
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS vehicle TEXT DEFAULT 'Sedan';
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS plate   TEXT DEFAULT 'N/A';
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS rating  NUMERIC(3,1) DEFAULT 5.0;

-- Update existing drivers
UPDATE drivers SET vehicle='White Honda CR-V',     plate='CTXI-001', rating=4.9 WHERE phone='+12895551001';
UPDATE drivers SET vehicle='Black Toyota Camry',   plate='CTXI-002', rating=4.8 WHERE phone='+12895551002';
UPDATE drivers SET vehicle='Silver Ford Escape',   plate='CTXI-003', rating=4.7 WHERE phone='+12895551003';
UPDATE drivers SET vehicle='Blue Hyundai Sonata',  plate='CTXI-004', rating=4.9 WHERE phone='+12895551004';
```

---

## 8. Deploy to Production

### Option A: Railway (Recommended — free tier)
```bash
npm install -g @railway/cli
railway login
railway init
railway up
```

### Option B: Render
1. Push to GitHub
2. New Web Service → connect repo
3. Build: `pip install -r requirements.txt`
4. Start: `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT`

### Option C: VPS ($4-6/month)
```bash
# On server
git clone https://github.com/you/caledonia-taxi
cd caledonia-taxi
pip3 install -r requirements.txt
# Set up systemd service or screen session
cd backend && uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## Quick Reference — Monthly Costs (Live)

| Service | Free Tier | Paid |
|---------|-----------|------|
| Hosting (Railway) | Free / $5 | $5/mo |
| Supabase | Free | $25/mo |
| OpenRouteService | 2k req/day | Free |
| Twilio SMS | N/A | ~$3/mo |
| Resend Email | 3k emails/mo | Free |
| Voice AI (Vapi) | ~$10 credits | Pay-as-go |
| **Total MVP** | **~$0** | **~$8-15/mo** |

---

*Generated by Claude overnight automation — 2026-03-17*
