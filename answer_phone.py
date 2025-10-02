import os
import sys
from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse
from datetime import datetime
from dotenv import load_dotenv

# Add the src directory to the path to import modules
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))
from crm import crm_manager

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), 'src', '.env'))

app = Flask(__name__)

@app.route("/", methods=['GET', 'POST'])
def answer_call():
    """Respond to incoming phone calls with a brief message."""
    # Get caller's phone number
    caller_phone = request.values.get('From', 'Unknown')
    
    # Start our TwiML response
    resp = VoiceResponse()

    # Read a message aloud to the caller
    resp.say("Thank you for calling our restaurant! We appreciate your call. Have a great day!", voice='Polly.Amy')

    # Store caller info in CRM as phone call
    try:
        # Use asyncio to run async function
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        loop.run_until_complete(crm_manager.store_customer_info(
            phone=caller_phone,
            interaction_summary="Incoming phone call answered"
        ))
        
        loop.close()
        print(f"Stored phone call from {caller_phone} in CRM")
    except Exception as e:
        print(f"Failed to store phone call in CRM: {str(e)}")

    return str(resp)

if __name__ == "__main__":
    app.run(debug=True)