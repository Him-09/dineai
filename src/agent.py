import os
import re
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

# Import the custom tools (package-relative)
from .tools.faq import restaurant_faq
from .tools.book_table import book_table
from .tools.modify_reservation import modify_reservation
from .tools.cancel_reservation import cancel_reservation, view_reservation
from .tools.check_availability import check_table_availability
from .tools.menu_search import menu_search

# Load environment variables
load_dotenv()

# Create the LLM with OpenAI API
llm = ChatOpenAI(
    model="gpt-4o-mini",  # Use GPT-4o-mini for better tool calling
    temperature=0.1,  # Lower temperature for more consistent responses
    openai_api_key=os.getenv("OPENAI_API_KEY")
)

# Directly use the custom tools instead of load_tools
tools = [book_table, modify_reservation, cancel_reservation, view_reservation, check_table_availability, restaurant_faq, menu_search]

print(f"Available tools: {[tool.name for tool in tools]}")

# Create memory saver for conversation history
memory = MemorySaver()

# Define system prompt for the agent
system_prompt = """You are a professional restaurant assistant AI helping customers with reservations, menu inquiries, and general questions about our restaurant.

Conversation policy:
- Always review conversation history before asking questions.
- Maintain an internal checklist for bookings: name, date, time, party size, optional phone.
- Ask ONLY for missing items. Do not repeat requests for information already provided earlier.
- When appropriate, confirm what you have (e.g., "I have you down for 4 guests tomorrow at 7 PM") and ask just the missing field in a single compact question.
- Once all required fields are available, proceed to use the book_table tool.

Tone: warm, concise, professional."""

# Create ReAct agent with memory and system prompt  
agent = create_react_agent(
    model=llm,
    tools=tools,
    checkpointer=memory
)

# Keep track of which thread_ids have already received the system prompt
# This is process-local and ensures the system prompt is only injected once per conversation thread
seen_threads = set()

# Lightweight per-thread slot tracker (process-local)
# Stores what booking details we've already extracted from user messages
booking_state: dict[str, dict[str, str]] = {}

NAME_PATTERNS = [
    re.compile(r"(?:my name is|i am|i'm|this is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", re.I),
]
DATE_PATTERNS = [
    re.compile(r"\b(today|tomorrow|tonight)\b", re.I),
    re.compile(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.I),
    re.compile(r"\b(\d{4}-\d{1,2}-\d{1,2})\b"),               # 2025-10-21
    re.compile(r"\b(\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b"),        # 10/21 or 10/21/2025
]
TIME_PATTERNS = [
    re.compile(r"\b(\d{1,2}:\d{2}\s?(?:am|pm)?)\b", re.I),    # 7:30 pm
    re.compile(r"\b(\d{1,2}\s?(?:am|pm))\b", re.I),            # 7 pm
    re.compile(r"\b(at\s+\d{1,2}(?::\d{2})?\s?(?:am|pm)?)\b", re.I),
]
PARTY_PATTERNS = [
    re.compile(r"\bfor\s+(\d+)\b"),
    re.compile(r"\b(\d+)\s+(?:people|guests|persons)\b", re.I),
]
PHONE_PATTERNS = [
    re.compile(r"\b(\+?\d[\d\-\s]{7,}\d)\b"),
]

def extract_booking_info(text: str) -> dict[str, str]:
    info: dict[str, str] = {}
    # name
    for pat in NAME_PATTERNS:
        m = pat.search(text)
        if m:
            info["name"] = m.group(1).strip()
            break
    # date
    for pat in DATE_PATTERNS:
        m = pat.search(text)
        if m:
            info["date"] = m.group(1).strip()
            break
    # time
    for pat in TIME_PATTERNS:
        m = pat.search(text)
        if m:
            # drop leading 'at '
            val = m.group(1).strip()
            info["time"] = re.sub(r"^at\s+", "", val, flags=re.I)
            break
    # party size
    for pat in PARTY_PATTERNS:
        m = pat.search(text)
        if m:
            info["party_size"] = m.group(1).strip()
            break
    # phone
    for pat in PHONE_PATTERNS:
        m = pat.search(text)
        if m:
            info["phone"] = m.group(1).strip()
            break
    return info

def summarize_booking_info(info: dict[str, str]) -> str:
    def has(k: str) -> bool:
        return bool(info.get(k))
    def val(k: str) -> str:
        return info.get(k, "unknown")

    required = ["name", "date", "time", "party_size"]
    missing = [k for k in required if not has(k)]

    summary = (
        f"Known booking details so far -> name: {val('name')}, date: {val('date')}, "
        f"time: {val('time')}, party_size: {val('party_size')}, phone: {val('phone')}.\n"
    )

    if missing:
        summary += (
            "Missing fields: " + ", ".join(missing) + ". "
            "Ask ONLY for these missing items in a single, concise question. Do not ask for any already-known field."
        )
    else:
        summary += (
            "All required fields are present. Proceed to use the book_table tool now without asking for more details."
        )

    return summary

def run_agent(input_text: str, thread_id: str = "default") -> str:
    """
    Run the agent with the provided input text and maintain conversation memory.
    
    Args:
        input_text (str): The input text to process.
        thread_id (str): Unique identifier for the conversation thread.
        
    Returns:
        str: The agent's response.
    """
    try:
        print(f"Processing query: {input_text}")
        
        # LangGraph agents with checkpointer automatically maintain conversation history
        # Just pass the new user message and the thread_id for memory persistence
        config = {"configurable": {"thread_id": thread_id}}
        
        # Maintain per-thread booking state
        state = booking_state.get(thread_id, {})
        updates = extract_booking_info(input_text)
        if updates:
            state.update({k: v for k, v in updates.items() if v})
            booking_state[thread_id] = state
            print(f"[agent] extracted updates for {thread_id}: {updates}")
        print(f"[agent] booking_state for {thread_id}: {state}")

        # Prepare messages for this turn
        messages = []
        if thread_id not in seen_threads:
            # Inject the base policy prompt once per thread
            messages.append(("system", system_prompt))
            seen_threads.add(thread_id)

        # Inject a lightweight dynamic context with the currently known booking details
        if state:
            summary_msg = summarize_booking_info(state)
            print(f"[agent] summary for {thread_id}: {summary_msg}")
            messages.append(("system", summary_msg))

        # Append the user's message; the checkpointer supplies prior history
        messages.append(("user", input_text))

        response = agent.invoke({"messages": messages}, config=config)
        
        # Extract the final message from the response
        if response and "messages" in response:
            messages = response["messages"]
            if messages:
                final_message = messages[-1]
                # Handle different message formats
                if hasattr(final_message, 'content'):
                    return final_message.content
                elif isinstance(final_message, tuple) and len(final_message) > 1:
                    return final_message[1]
                else:
                    return str(final_message)
        
        return "No response generated."
        
    except Exception as e:
        return f"Error running agent: {str(e)}"

if __name__ == "__main__":
    print("Restaurant AI Agent started! Type 'quit' or 'exit' to end the conversation.")
    print("The agent will remember our conversation throughout this session.")
    print("-" * 60)
    
    # Generate a unique thread ID for this conversation session
    import uuid
    thread_id = str(uuid.uuid4())
    
    while True:
        try:
            user_input = input("\nYou: ").strip()
            
            # Check for exit commands
            if user_input.lower() in ['quit', 'exit', 'bye', 'goodbye']:
                print("Thank you for using the Restaurant AI Agent. Goodbye!")
                break
            
            # Skip empty inputs
            if not user_input:
                continue
                
            print("Agent: ", end="")
            result = run_agent(user_input, thread_id)
            print(result)
            
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except EOFError:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"An error occurred: {str(e)}")
            print("Please try again.")
