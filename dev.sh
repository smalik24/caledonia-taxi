#!/bin/bash
# =====================================================
# Caledonia Taxi — Full Dev Environment Startup
# Starts: API server + ngrok tunnel
# Usage: bash dev.sh
# =====================================================

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "unknown")

# Activate venv
source "$PROJECT_DIR/venv/bin/activate"

echo ""
echo "🚕  Caledonia Taxi — Dev Environment"
echo "══════════════════════════════════════"

# Kill any existing server on port 8000
if lsof -ti:8000 > /dev/null 2>&1; then
    echo "⚠️  Port 8000 in use — stopping existing process..."
    lsof -ti:8000 | xargs kill -9 2>/dev/null
    sleep 1
fi

# Start API server in background
echo "▶  Starting API server..."
cd "$PROJECT_DIR/backend"
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload > /tmp/caledonia-server.log 2>&1 &
SERVER_PID=$!
sleep 2

# Start Cloudflare tunnel (free, no account needed)
echo "▶  Starting Cloudflare tunnel..."
cloudflared tunnel --url http://localhost:8000 --no-autoupdate > /tmp/caledonia-tunnel.log 2>&1 &
NGROK_PID=$!
sleep 8

# Extract public URL from cloudflared log
NGROK_URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /tmp/caledonia-tunnel.log | head -1)

echo ""
echo "══════════════════════════════════════"
echo "✅  EVERYTHING IS RUNNING"
echo "══════════════════════════════════════"
echo ""
echo "📱  MOBILE (same WiFi):"
echo "    http://$LOCAL_IP:8000"
echo "    http://$LOCAL_IP:8000/driver"
echo "    http://$LOCAL_IP:8000/admin"
echo ""

if [ -n "$NGROK_URL" ]; then
    echo "🌐  PUBLIC URL (for Vapi + sharing):"
    echo "    $NGROK_URL"
    echo "    $NGROK_URL/driver"
    echo "    $NGROK_URL/admin"
    echo ""
    echo "🎙️  VAPI WEBHOOK URL:"
    echo "    $NGROK_URL/api/vapi/webhook"
    echo ""
    echo "    → Open vapi_assistant.json"
    echo "    → Replace NGROK_URL with: $NGROK_URL"
    echo ""

    # Auto-patch vapi_assistant.json with the current ngrok URL
    if [ -f "$PROJECT_DIR/vapi_assistant.json" ]; then
        sed -i '' "s|NGROK_URL|$NGROK_URL|g" "$PROJECT_DIR/vapi_assistant.json"
        echo "✅  vapi_assistant.json auto-updated with ngrok URL"
    fi
else
    echo "⚠️  ngrok URL not detected — check http://localhost:4040"
fi

echo ""
echo "🖥️  LOCAL:"
echo "    http://localhost:8000"
echo "    http://localhost:8000/docs  (API docs)"
echo "    http://localhost:4040       (ngrok dashboard)"
echo ""
echo "══════════════════════════════════════"
echo "  Ctrl+C to stop everything"
echo "══════════════════════════════════════"
echo ""

# Trap Ctrl+C and clean up
cleanup() {
    echo ""
    echo "🛑  Shutting down..."
    kill $SERVER_PID $NGROK_PID 2>/dev/null
    lsof -ti:8000 | xargs kill -9 2>/dev/null
    exit 0
}
trap cleanup INT TERM

# Stream server logs
tail -f /tmp/caledonia-server.log
