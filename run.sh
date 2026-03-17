#!/bin/bash
# Caledonia Taxi - Start Script
# Usage: ./run.sh  OR  bash run.sh

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "🚕  Caledonia Taxi — Booking & Dispatch System"
echo "================================================"
echo ""
echo "📦 Installing/verifying dependencies..."
pip3 install -r "$PROJECT_DIR/requirements.txt" -q

echo "✅ Dependencies ready."
echo ""
echo "🌐 Open these in your browser:"
echo "   Customer Booking  →  http://localhost:8000"
echo "   Driver App        →  http://localhost:8000/driver"
echo "   Admin Panel       →  http://localhost:8000/admin"
echo "   API Docs          →  http://localhost:8000/docs"
echo ""
echo "   Driver logins:"
echo "   Saqib:    phone +12895551001  PIN 1234"
echo "   Driver 2: phone +12895551002  PIN 2345"
echo "   Driver 3: phone +12895551003  PIN 3456"
echo "   Driver 4: phone +12895551004  PIN 4567"
echo ""
echo "Starting server... (Ctrl+C to stop)"
echo "================================================"
echo ""

cd "$PROJECT_DIR/backend"
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
