"""Run once: python setup_vapi.py — creates or updates the Vapi assistant."""
import os, httpx, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "backend"))
from dotenv import load_dotenv
load_dotenv()
from vapi_config import VAPI_ASSISTANT_CONFIG

API_KEY = os.getenv("VAPI_API_KEY")
ASSISTANT_ID = os.getenv("VAPI_ASSISTANT_ID")

if not API_KEY:
    print("Error: VAPI_API_KEY not set in .env")
    sys.exit(1)

headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

if ASSISTANT_ID:
    r = httpx.patch(f"https://api.vapi.ai/assistant/{ASSISTANT_ID}", headers=headers, json=VAPI_ASSISTANT_CONFIG)
    print(f"Updated assistant {ASSISTANT_ID}: {r.status_code}")
else:
    r = httpx.post("https://api.vapi.ai/assistant", headers=headers, json=VAPI_ASSISTANT_CONFIG)
    data = r.json()
    print(f"Created assistant: {data.get('id')} — add VAPI_ASSISTANT_ID={data.get('id')} to .env")
