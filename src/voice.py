import logging
import os
import re
from dataclasses import dataclass, field
from typing import Annotated, Optional, Any, Any
from datetime import datetime
from livekit import rtc


import yaml
from dotenv import load_dotenv
from pydantic import Field

from livekit.agents import metrics, MetricsCollectedEvent
from livekit.agents import JobContext, WorkerOptions, cli, metrics
from livekit.agents.llm import function_tool
from livekit.agents.voice import Agent, AgentSession, RunContext
from livekit.agents.voice.room_io import RoomInputOptions
from livekit.plugins import cartesia, deepgram, openai, silero, elevenlabs, noise_cancellation

# Import your custom RAG tools
from tools.faq import restaurant_faq
from tools.book_table import book_table
from tools.modify_reservation import modify_reservation
from tools.cancel_reservation import cancel_reservation, view_reservation
from tools.check_availability import check_table_availability
from tools.menu_search import menu_search, menu_recommendations

# Import database for connection testing
from db import supabase

# Import CRM functionality
from crm import crm_manager, store_customer_info, add_interaction_note, get_customer_by_phone

logger = logging.getLogger("restaurant-voice-agent")
logger.setLevel(logging.INFO)

# Load environment variables from the correct path
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

def clean_phone_number(phone: str) -> Optional[str]:
    """Clean and validate phone number format."""
    import re
    
    if not phone:
        return None
    
    # Remove all non-digit characters except + at the beginning
    cleaned = re.sub(r'[^\d+]', '', phone)
    
    # If it's already a properly formatted international number, return as-is
    if cleaned.startswith('+') and len(cleaned) >= 11:  # +X and at least 10 digits
        # Validate that it's a reasonable phone number length (10-15 digits after +)
        digits_after_plus = cleaned[1:]
        if len(digits_after_plus) >= 10 and len(digits_after_plus) <= 15:
            return cleaned
    
    # Handle US numbers specifically
    if cleaned.startswith('+1'):
        # US number with country code +1
        digits = cleaned[2:]
        if len(digits) == 10:
            return cleaned  # Already properly formatted
    elif cleaned.startswith('1') and len(cleaned) == 11:
        # US number starting with 1 but missing +
        return f"+{cleaned}"
    elif len(cleaned) == 10:
        # 10-digit US number without country code
        return f"+1{cleaned}"
    
    # For other cases, if it starts with + and has reasonable length, keep it
    if cleaned.startswith('+') and len(cleaned) >= 10:
        return cleaned
    
    # If it doesn't start with + but has reasonable length, it might be international
    if len(cleaned) >= 10 and len(cleaned) <= 15 and not cleaned.startswith('1'):
        return f"+{cleaned}"
    
    return None

def extract_phone_from_caller_id(caller_id: str) -> Optional[str]:
    """Extract phone number from LiveKit caller ID/room name if available."""
    if not caller_id:
        return None
    
    # Remove common prefixes and clean the string
    cleaned = caller_id.strip()
    
    # Try to extract phone number using regex patterns
    import re
    
    # Pattern 1: Look for phone number patterns in the string
    # Matches: +15551234567, +1-555-123-4567, (555) 123-4567, etc.
    phone_patterns = [
        #r'\+?1?[-.\s]?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})',  # US numbers
        r'\+([0-9]{10,15})',  # International numbers with +
        r'([0-9]{10,11})',    # 10-11 digit numbers
    ]
    
    for pattern in phone_patterns:
        matches = re.findall(pattern, cleaned)
        if matches:
            if isinstance(matches[0], tuple):
                # For grouped matches (area code, exchange, number)
                phone_digits = ''.join(matches[0])
            else:
                # For single group matches
                phone_digits = matches[0]
            
            # Try to clean and validate the extracted digits
            potential_phone = clean_phone_number(phone_digits)
            if potential_phone:
                logger.info(f"📞 Extracted phone from '{caller_id}': {potential_phone}")
                return potential_phone
    
    # Fallback: Check if the entire caller_id looks like a phone number
    if caller_id and caller_id.startswith(('+', '1')) and len(caller_id.replace('+', '').replace('-', '').replace(' ', '')) >= 10:
        return clean_phone_number(caller_id)
    
    # If no phone pattern found, return None
    return None

def test_database_connection():
    """Test database connection at startup"""
    try:
        result = supabase.table("bookings").select("*").limit(1).execute()
        logger.info("[SUCCESS] Database connection successful")
        return True
    except Exception as e:
        logger.error(f"[ERROR] Database connection failed: {str(e)}")
        return False


# Voice configurations for different agent types
voices = {
    "main": "f786b574-daa5-4673-aa0c-cbe3e8534c02",  # Your current voice
    "booking": "156fb8d2-335b-4950-9cb3-a2d33befec77",
    "menu": "6f84f4b8-58a2-430c-8b37-e00b72059fdd",
    "faq": "39b376fc-488e-4d0c-8b37-e00b72059fdd",
}

@dataclass
class RestaurantUserData:
    """User data for restaurant interactions"""
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    current_reservation_id: Optional[int] = None
    pending_booking: Optional[dict] = None
    conversation_context: Optional[str] = None
    
    # Session tracking
    room_name: Optional[str] = None
    conversation_summary: Optional[str] = None
    
    agents: dict[str, Agent] = field(default_factory=dict)
    prev_agent: Optional[Agent] = None

    def summarize(self) -> str:
        data = {
            "customer_name": self.customer_name or "not provided",
            "customer_phone": self.customer_phone or "not provided", 
            "current_reservation_id": self.current_reservation_id or "none",
            "pending_booking": self.pending_booking or "none",
            "conversation_context": self.conversation_context or "general inquiry"
        }
        return yaml.dump(data)

    def get_contact_info(self) -> dict[str, Optional[str]]:
        """Get complete contact information for the customer."""
        return {
            "name": self.customer_name,
            "phone": self.customer_phone
        }

RunContext_T = RunContext[RestaurantUserData]

# Common utility functions for LiveKit integration
@function_tool()
async def update_customer_name(
    name: Annotated[str, Field(description="The customer's name")],
    context: RunContext_T,
) -> str:
    """Called when the user provides their name for reservations or orders."""
    userdata = context.userdata
    userdata.customer_name = name
    
    # Update CRM with customer name if we have a phone number
    if userdata.customer_phone:
        try:
            await store_customer_info(
                phone=userdata.customer_phone,
                name=name
            )
            logger.info(f"Updated CRM with customer name: {name} (phone: {userdata.customer_phone})")
        except Exception as e:
            logger.error(f"Failed to update CRM with name: {str(e)}")
    
    return f"Great! I've recorded your name as {name}."

@function_tool()
async def update_customer_phone(
    phone: Annotated[str, Field(description="The customer's phone number in any format (e.g., +1-555-123-4567, (555) 123-4567, etc.)")],
    context: RunContext_T,
) -> str:
    """Called when the user provides their phone number for contact or verification."""
    userdata = context.userdata
    
    # Clean and validate phone number
    cleaned_phone = clean_phone_number(phone)
    if not cleaned_phone:
        return "I'm sorry, that doesn't appear to be a valid phone number. Could you please provide it again?"
    
    userdata.customer_phone = cleaned_phone
    
    # Update CRM with phone number as primary key
    try:
        await store_customer_info(
            phone=cleaned_phone,
            name=userdata.customer_name
        )
        logger.info(f"Updated CRM with phone number: {cleaned_phone}")
    except Exception as e:
        logger.error(f"Failed to update CRM with phone: {str(e)}")
    
    return f"Perfect! I've recorded your phone number as {cleaned_phone}. This will help us contact you if needed."

# LiveKit-compatible wrapper functions for your existing tools
@function_tool()
async def voice_book_table(
    name: Annotated[str, Field(description="Customer name")],
    date: Annotated[str, Field(description="Date for reservation. Can be natural language like 'tomorrow', 'next Friday', 'August 15', 'Monday', or specific date in YYYY-MM-DD format")],
    time: Annotated[str, Field(description="Reservation time in HH:MM format (24-hour)")],
    party_size: Annotated[int, Field(description="Number of people (1-20)")],
    context: RunContext_T,
) -> str:
    """Book a table at the restaurant using the existing booking system."""
    logger.info(f"🔄 Starting table booking for {name}, {party_size} people on {date} at {time}")
    
    # Provide immediate feedback using the session's say method
    # await context.session.say("okay, I'm processing your booking request...")

    try:
        # Get customer contact info
        userdata = context.userdata
        contact_info = userdata.get_contact_info()
        
        # Use invoke method for LangChain tools with enhanced data
        booking_data = {
            "name": name,
            "date": date, 
            "time": time,
            "party_size": party_size
        }
        
        # Add phone if available (from SIP or user input)
        if userdata.customer_phone:
            booking_data["phone"] = userdata.customer_phone
            logger.info(f"📞 Including phone in booking: {userdata.customer_phone}")
        elif contact_info.get("phone"):
            booking_data["phone"] = contact_info["phone"]
            logger.info(f"📞 Including phone from contact info: {contact_info['phone']}")
        else:
            logger.info("📞 No phone number available for booking")
        
        result = book_table.invoke(booking_data)

        
        logger.info(f"✅ Booking completed: {result[:100]}...")
        
        # Update user data if booking successful
        if "successfully" in result.lower() or "confirmed" in result.lower():
            userdata = context.userdata
            userdata.customer_name = name
            userdata.pending_booking = {
                "date": date,
                "time": time,
                "party_size": party_size,
                "status": "confirmed"
            }
            
            # Add CRM note about successful booking
            if userdata.customer_phone:
                note = f"Booked table for {party_size} people on {date} at {time}"
                await add_interaction_note(userdata.customer_phone, note)
            
        return result
    except Exception as e:
        logger.error(f"❌ Error booking table: {str(e)}")
        return f"I apologize, but I encountered an error while trying to book your table: {str(e)}"

@function_tool()
async def voice_check_availability(
    date: Annotated[str, Field(description="Date to check availability. Can be natural language like 'tomorrow', 'next Friday', 'August 15', 'Monday', or specific date in YYYY-MM-DD format")],
    context: RunContext_T,
    time: Annotated[Optional[str], Field(description="Specific time in HH:MM format")] = None,
    party_size: Annotated[Optional[int], Field(description="Number of people")] = None,
) -> str:
    """Check table availability for specific dates and times."""
    logger.info(f"🔍 Checking availability for {date}" + (f" at {time}" if time else "") + (f" for {party_size} people" if party_size else ""))
    
    # Set conversation context
    userdata = context.userdata
    availability_details = f"{date}"
    if time:
        availability_details += f" at {time}"
    if party_size:
        availability_details += f" for {party_size} people"
    userdata.conversation_context = f"Availability check: {availability_details}"
    
    # Provide immediate feedback using the session's say method
    # await context.session.say("alright, I'm checking availability for you...")

    try:
        # Use invoke method for LangChain tools
        input_data: dict[str, Any] = {"date": date}
        if time is not None:
            input_data["time"] = time
        if party_size is not None:
            input_data["party_size"] = party_size
            
        result = check_table_availability.invoke(input_data)
        logger.info(f"✅ Availability check completed")
        return result
    except Exception as e:
        logger.error(f"Error checking availability: {str(e)}")
        return f"I'm sorry, I couldn't check availability right now: {str(e)}"

@function_tool()
async def voice_menu_search(
    query: Annotated[str, Field(description="What the customer is looking for in the menu")],
    context: RunContext_T,
) -> str:
    """Search the restaurant menu for specific items or dietary preferences."""
    logger.info(f"🔍 Searching menu for: {query}")
    
    # Set conversation context
    userdata = context.userdata
    userdata.conversation_context = f"Menu search: {query}"
    
    # Provide immediate feedback using the session's say method
    await context.session.say("Emmm, I'm looking through our menu...")
    
    try:
        result = menu_search.invoke({"query": query})
        logger.info(f"✅ Menu search completed")
        return result
    except Exception as e:
        logger.error(f"❌ Error searching menu: {str(e)}")
        return f"I apologize, I couldn't search the menu right now: {str(e)}"

@function_tool()
async def voice_menu_recommendations(
    preferences: Annotated[str, Field(description="Customer's dietary preferences or food interests")],
    context: RunContext_T,
) -> str:
    """Get personalized menu recommendations based on customer preferences."""
    # Set conversation context
    userdata = context.userdata
    userdata.conversation_context = f"Menu recommendations: {preferences}"
    
    # Provide immediate feedback using the session's say method
    await context.session.say("Let me find some recommendations for you...")
    
    try:
        result = menu_recommendations.invoke({"preferences": preferences})
        return result
    except Exception as e:
        logger.error(f"Error getting recommendations: {str(e)}")
        return f"I'm sorry, I couldn't generate recommendations right now: {str(e)}"

@function_tool()
async def voice_restaurant_faq(
    question: Annotated[str, Field(description="Customer's question about the restaurant")],
    context: RunContext_T,
) -> str:
    """Answer frequently asked questions about the restaurant."""
    # Set conversation context
    userdata = context.userdata
    userdata.conversation_context = f"FAQ: {question}"
    
    await context.session.say("Let me find that information for you...")
    try:
        result = restaurant_faq.invoke({"question": question})
        return result
    except Exception as e:
        logger.error(f"Error answering FAQ: {str(e)}")
        return f"I apologize, I couldn't find that information right now: {str(e)}"

@function_tool()
async def voice_view_reservation(
    reservation_id: Annotated[int, Field(description="The reservation ID to look up")],
    context: RunContext_T,
) -> str:
    """View details of an existing reservation."""
    await context.session.say("Let me check the details of your reservation...")
    try:
        result = view_reservation.invoke({"reservation_id": reservation_id})
        userdata = context.userdata
        userdata.current_reservation_id = reservation_id
        return result
    except Exception as e:
        logger.error(f"Error viewing reservation: {str(e)}")
        return f"I couldn't retrieve that reservation: {str(e)}"

@function_tool()
async def voice_modify_reservation(
    reservation_id: Annotated[int, Field(description="The reservation ID to modify")],
    context: RunContext_T,
    name: Annotated[Optional[str], Field(description="New customer name")] = None,
    date: Annotated[Optional[str], Field(description="New date. Can be natural language like 'tomorrow', 'next Friday', 'August 15', or YYYY-MM-DD format")] = None,
    time: Annotated[Optional[str], Field(description="New time in HH:MM format")] = None,
    party_size: Annotated[Optional[int], Field(description="New party size")] = None,
) -> str:
    """Modify an existing reservation."""
    await context.session.say("I'm processing your request...")
    try:
        input_data: dict[str, Any] = {"reservation_id": reservation_id}
        if name is not None:
            input_data["name"] = name
        if date is not None:
            input_data["date"] = date
        if time is not None:
            input_data["time"] = time
        if party_size is not None:
            input_data["party_size"] = party_size
            
        result = modify_reservation.invoke(input_data)
        return result
    except Exception as e:
        logger.error(f"Error modifying reservation: {str(e)}")
        return f"I couldn't modify that reservation: {str(e)}"

@function_tool()
async def voice_cancel_reservation(
    reservation_id: Annotated[int, Field(description="The reservation ID to cancel")],
    context: RunContext_T,
    reason: Annotated[Optional[str], Field(description="Reason for cancellation")] = None,
) -> str:
    """Cancel an existing reservation."""
    await context.session.say("I'm processing your cancellation request...")
    try:
        input_data: dict[str, Any] = {"reservation_id": reservation_id}
        if reason is not None:
            input_data["reason"] = reason
            
        result = cancel_reservation.invoke(input_data)
        
        # Add CRM note about cancellation
        userdata = context.userdata
        if userdata.customer_phone:
            note = f"Cancelled reservation #{reservation_id}"
            if reason:
                note += f" - Reason: {reason}"
            await add_interaction_note(userdata.customer_phone, note)
        
        return result
    except Exception as e:
        logger.error(f"Error canceling reservation: {str(e)}")
        return f"I couldn't cancel that reservation: {str(e)}"

@function_tool()
async def add_customer_note(
    note: Annotated[str, Field(description="Important note or information about the customer")],
    context: RunContext_T,
) -> str:
    """Add a note to the customer's CRM record for future reference."""
    userdata = context.userdata
    
    if not userdata.customer_phone:
        return "I'm sorry, I couldn't add that note to your record right now."
    
    try:
        result = await add_interaction_note(userdata.customer_phone, note)
        
        if result.get("success"):
            return "I've added that note to your record for future reference."
        else:
            return "I had trouble saving that note, but I'll remember it for this call."
            
    except Exception as e:
        logger.error(f"Error adding customer note: {str(e)}")
        return "I had trouble saving that note, but I'll remember it for this call."

class RestaurantVoiceAgent(Agent):
    """Main restaurant voice agent with integrated RAG capabilities"""
    
    def __init__(self) -> None:
        super().__init__(
            instructions=(
                "You are an assistant for a restaurant. "
                "Always be friendly, professional, and helpful. When taking reservations, "
                "make sure to collect the customer's name, preferred date, time, and party size. "
                "The customer's phone number may already be available from their call - you don't always need to ask for it unless specifically needed for confirmation. "
                "Use the available tools to access real menu information, check actual availability, and manage reservations through our booking system. "
                "Respond quickly and conversationally while tools are being processed. "
                "Try to win time by making small talk to avoid dead air. "
                "When ending calls, simply say goodbye without summarizing the entire conversation."
            ),
            llm=openai.LLM(
                model="gpt-4o-mini",
                parallel_tool_calls=True,  # Enable parallel tool calls for faster processing
            ),
            tts = openai.TTS(
                model="gpt-4o-mini-tts",
                voice="ash",
                instructions="Speak in a friendly and conversational tone.",
            ),
            tools=[
                voice_book_table,
                voice_check_availability, 
                voice_menu_search,
                voice_menu_recommendations,
                voice_restaurant_faq,
                voice_view_reservation,
                voice_modify_reservation,
                voice_cancel_reservation,
                update_customer_name,
                update_customer_phone,
                add_customer_note,
            ],
        )

    async def on_enter(self) -> None:
        """Called when the agent starts or resumes"""
        logger.info("Restaurant voice agent activated")
        
        userdata: RestaurantUserData = self.session.userdata
        
        # Log phone information if available
        if userdata.customer_phone:
            logger.info(f"📞 Agent started with phone number: {userdata.customer_phone}")
        else:
            logger.info("📞 Agent started without phone number")
        
        # Initialize caller tracking
        await self._initialize_caller_tracking(userdata)
        
        chat_ctx = self.chat_ctx.copy()

        # Add context about the current user data
        if userdata:
            context_info = f"Current session context: {userdata.summarize()}"
            chat_ctx.add_message(
                role="system",
                content=context_info
            )
            await self.update_chat_ctx(chat_ctx)

    async def _initialize_caller_tracking(self, userdata: RestaurantUserData):
        """Initialize caller tracking and retrieve existing contact info"""
        try:
            # Check if this customer exists in CRM (only if we have a phone)
            if userdata.customer_phone:
                existing_customer = get_customer_by_phone(userdata.customer_phone)
                if existing_customer:
                    logger.info(f"Found existing customer for phone {userdata.customer_phone}")
                    
                    # Pre-populate known information
                    if existing_customer.get('name') and not userdata.customer_name:
                        userdata.customer_name = existing_customer['name']
                        logger.info(f"Pre-populated customer name: {userdata.customer_name}")
                else:
                    logger.info(f"New customer detected: {userdata.customer_phone}")
            else:
                logger.info(f"No phone number available for CRM lookup")
                
        except Exception as e:
            logger.error(f"Error initializing customer tracking: {str(e)}")

    def _generate_conversation_summary(self, userdata: RestaurantUserData) -> str:
        """Generate a meaningful conversation summary based on user interactions"""
        summary_parts = []
        
        # Add customer name if available
        if userdata.customer_name:
            summary_parts.append(f"Customer: {userdata.customer_name}")
        
        # Add booking information if available
        if userdata.pending_booking:
            booking = userdata.pending_booking
            if booking.get("status") == "confirmed":
                booking_info = f"Booked table for {booking.get('party_size', 'N/A')} people on {booking.get('date', 'N/A')} at {booking.get('time', 'N/A')}"
                summary_parts.append(booking_info)
            else:
                summary_parts.append("Discussed table booking (not confirmed)")
        
        # Add reservation management if applicable
        if userdata.current_reservation_id:
            summary_parts.append(f"Managed reservation #{userdata.current_reservation_id}")
        
        # Add conversation context if available
        if userdata.conversation_context:
            summary_parts.append(f"Topic: {userdata.conversation_context}")
        
        # Default summary if no specific actions
        if not summary_parts:
            summary_parts.append("General inquiry call")
        
        return "; ".join(summary_parts)

    async def on_user_speech_transcript(self, transcript: str) -> None:
        """Called when user speech is transcribed - no longer storing transcripts"""
        # Transcript capturing disabled - no action needed
        pass

    async def on_agent_speech_committed(self, agent_transcript: str) -> None:
        """Called when agent speech is committed - no longer storing transcripts"""
        # Transcript capturing disabled - no action needed
        pass

    async def on_exit(self) -> None:
        """Called when the agent session ends - save basic info to CRM without transcript"""
        try:
            userdata: RestaurantUserData = self.session.userdata
            
            # Store basic customer info without transcript
            phone_to_use = userdata.customer_phone
            if not phone_to_use and userdata.room_name:
                # Try to extract phone from room name one more time
                phone_to_use = extract_phone_from_caller_id(userdata.room_name)
            
            if phone_to_use:
                # Generate meaningful conversation summary
                conversation_summary = self._generate_conversation_summary(userdata)
                
                # Store in CRM using phone as primary key (with conversation summary)
                result = await store_customer_info(
                    phone=phone_to_use,
                    name=userdata.customer_name or "Unknown",
                    interaction_summary=conversation_summary
                )
                
                if result.get("success"):
                    logger.info(f"Successfully stored call data in CRM for {phone_to_use}: {conversation_summary}")
                else:
                    logger.error(f"Failed to store call data in CRM: {result.get('error')}")
            else:
                logger.warning("No phone number available to store customer data in CRM")
                
        except Exception as e:
            logger.error(f"Error saving session to CRM: {str(e)}")



async def entrypoint(ctx: JobContext):
    """Main entry point for the restaurant voice agent"""
    
    # Test database connection first
    if not test_database_connection():
        logger.error("Failed to connect to database. Please check your environment variables and database setup.")
        raise Exception("Database connection failed")
    
    # Track call start time and initialize usage collector
    call_start = datetime.now()
    caller_info = ctx.room.name if ctx.room else "Unknown"
    usage_collector = metrics.UsageCollector()

    # Initialize user data
    userdata = RestaurantUserData()
    userdata.room_name = caller_info  # Store room name for later use
    
    # Extract phone number from room name (same approach as caller info for calls table)
    if caller_info and caller_info != "Unknown":
        # Try to extract phone number from room name
        extracted_phone = extract_phone_from_caller_id(caller_info)
        if extracted_phone:
            userdata.customer_phone = extracted_phone
            logger.info(f"📞 Phone number extracted from room name: {userdata.customer_phone}")
        else:
            logger.info(f"📞 Room name doesn't contain phone number: {caller_info}")
    else:
        logger.info("� No room name available for phone extraction")
    
    
    # Create the main agent
    main_agent = RestaurantVoiceAgent()
    userdata.agents["main"] = main_agent
    
    # Create agent session with your custom user data
    session = AgentSession[RestaurantUserData](
        userdata=userdata,
        stt = deepgram.STT(
            model="nova-3",
        ),  # Use Deepgram STT provider
        llm=openai.LLM(model="gpt-4o-mini"),
        tts = openai.TTS(
            model="gpt-4o-mini-tts",
            voice="ash",
            instructions="Speak in a friendly and conversational tone.",
        ),
        vad=silero.VAD.load(),
        max_tool_steps=5,  # Reduce tool steps to prevent long silences
    )

    # Set up metrics collection
    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        usage_collector.collect(ev.metrics)

    try:
        # Start the session
        await session.start(
            agent=main_agent,
            room=ctx.room,
            room_input_options=RoomInputOptions(
                # LiveKit Cloud enhanced noise cancellation
                # - If self-hosting, omit this parameter
                # - For telephony applications, use `BVCTelephony` for best results
                noise_cancellation=noise_cancellation.BVCTelephony(),
            ),
        )

        # Greet the caller after picking up
        await session.generate_reply(
            instructions="Greet the user and offer your assistance."
        )

        logger.info("Restaurant voice agent session started successfully")
        
    except Exception as e:
        logger.error(f"Session error: {str(e)}")
        call_status = "canceled"
    else:
        call_status = "answered"
    finally:
        # Track call end time and collect usage metrics
        call_end = datetime.now()
        duration = (call_end - call_start).total_seconds()

        # Extract transcript from session/chat context
        transcript_text = ""  # No longer capturing transcripts

        # Check if a booking was made during the call
        booking_made = (userdata.pending_booking or {}).get("status") == "confirmed"

        # Collect usage summary and calculate costs
        try:
            summary = usage_collector.get_summary()
            
            # Extract usage metrics from UsageSummary object
            llm_in = getattr(summary, 'llm_prompt_tokens', 0)
            llm_cached = getattr(summary, 'llm_prompt_cached_tokens', 0)
            llm_out = getattr(summary, 'llm_completion_tokens', 0)
            tts_chars = getattr(summary, 'tts_characters_count', 0)
            tts_duration = getattr(summary, 'tts_audio_duration', 0)
            stt_duration = getattr(summary, 'stt_audio_duration', 0)
            
            # Estimate session cost (adjust rates for your providers)
            # OpenAI GPT-4o-mini: ~$0.00015 per 1K input, ~$0.0006 per 1K output tokens
            # Deepgram STT: ~$0.0043 per minute
            # OpenAI TTS: estimated rate for calculation
            llm_cost = (llm_in * 0.00015 + llm_out * 0.0006) / 1000
            stt_cost = (stt_duration / 60) * 0.0043
            tts_cost = (tts_chars / 1000) * 0.30
            total_cost = llm_cost + stt_cost + tts_cost
            
        except Exception as e:
            logger.warning(f"Failed to collect usage metrics: {str(e)}")
            # Set default values if metrics collection fails
            llm_in = llm_out = llm_cached = 0
            tts_chars = tts_duration = stt_duration = 0
            total_cost = 0.0

        # Insert call data into Supabase with detailed usage metrics (no transcript)
        try:
            supabase.table("calls").insert({
                "client_id": userdata.customer_phone, # Use phone as client ID if available
                "caller": caller_info,
                "start_time": call_start.isoformat(),
                "end_time": call_end.isoformat(),
                "duration": duration,
                "status": call_status,
                "booking_made": booking_made,
                "transcript": "",  # No longer storing transcripts
                "llm_tokens_input": llm_in,
                "llm_tokens_output": llm_out,
                "stt_seconds": round(stt_duration, 2),  # Match your table field name
                "tts_characters": tts_chars,
                "estimated_cost": round(total_cost, 4)
            }).execute()
            
            logger.info(f"[CALL LOGGED] Call data with usage metrics pushed to Supabase")
            logger.info(f"[USAGE] LLM: {llm_in}in/{llm_out}out tokens (cached: {llm_cached}), STT: {stt_duration:.1f}s, TTS: {tts_chars} chars/{tts_duration:.1f}s, Cost: ${total_cost:.4f}")
        except Exception as e:
            logger.error(f"[ERROR] Failed to log call data: {str(e)}")

if __name__ == "__main__":
    cli.run_app(WorkerOptions(
        entrypoint_fnc=entrypoint,

        agent_name="my-telephony-agent"                    
    ))