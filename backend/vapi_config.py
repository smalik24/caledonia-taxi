"""Vapi Voice AI assistant configuration."""

VAPI_ASSISTANT_CONFIG = {
    "name": "Caledonia Taxi Booking Assistant",
    "firstMessage": "Thank you for calling Caledonia Taxi in Hamilton. I can help you book a ride right now. What's your pickup address?",
    "model": {
        "provider": "openai",
        "model": "gpt-4o",
        "systemPrompt": """You are a friendly booking agent for Caledonia Taxi in Hamilton, Ontario.
        Your job is to collect: customer name, phone number, pickup address, and drop-off address.
        Always confirm the addresses back to the customer before finalizing.
        When you have all the info, call the create_booking tool.
        If the customer asks for a price estimate, say fares start at $4.50 plus $2.10 per km.
        Business hours: 24/7. Phone: (289) 555-1001."""
    },
    "tools": [{
        "type": "function",
        "function": {
            "name": "create_booking",
            "description": "Create a taxi booking after collecting all required information",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string"},
                    "customer_phone": {"type": "string"},
                    "pickup_address": {"type": "string", "description": "Full street address in Hamilton, ON"},
                    "dropoff_address": {"type": "string", "description": "Full destination address"}
                },
                "required": ["customer_name", "customer_phone", "pickup_address", "dropoff_address"]
            }
        }
    }],
    "voice": {
        "provider": "11labs",
        "voiceId": "rachel"
    },
    "endCallMessage": "Your ride has been booked! You'll receive a text confirmation shortly. Thank you for choosing Caledonia Taxi!"
}
