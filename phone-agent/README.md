# Caledonia Taxi - AI Phone Agent Setup

## How It Works

The phone agent uses **Twilio** for call handling and the built-in Twilio `<Gather>` + `<Say>` TwiML for speech recognition and text-to-speech. This keeps costs minimal — no need for a separate STT/TTS service for the MVP.

### Call Flow:
1. Customer calls your Twilio number
2. AI greets them: "Welcome to Caledonia Taxi!"
3. Asks for pickup address (speech recognition)
4. Asks for drop-off address (speech recognition)
5. Calculates fare and reads it back
6. Asks for confirmation (yes/no)
7. If confirmed → creates booking & dispatches driver
8. If declined → hangs up politely

## Setup Steps

### 1. Get a Twilio Account
- Sign up at https://www.twilio.com (free trial includes $15 credit)
- Buy a local Hamilton phone number (~$1.15/month)

### 2. Configure Webhook
In your Twilio Console:
1. Go to Phone Numbers → Your number
2. Set the **Voice webhook** to: `https://your-domain.com/api/twilio/voice`
3. Method: POST

### 3. Set Environment Variables
```env
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=+1289xxxxxxx
```

### 4. Expose Your Server
For testing, use ngrok:
```bash
ngrok http 8000
```
Then set the Twilio webhook to: `https://your-ngrok-url.ngrok.io/api/twilio/voice`

## Cost Estimate
- Phone number: ~$1.15/month
- Inbound calls: ~$0.0085/min
- Speech recognition (Gather): included in Twilio
- Text-to-speech (Say/Polly): included in Twilio
- **Total for 100 calls/month (~2 min each):** ~$2.85/month

## Upgrading Later
For better speech understanding, you can upgrade to:
- Twilio + OpenAI Whisper (better accuracy, ~$0.006/min)
- Twilio + Deepgram (fast, ~$0.0043/min)
- Twilio + Google Speech-to-Text (good for Canadian accents)

The webhook endpoints in `main.py` are modular — you can swap the STT/TTS without changing the booking logic.
