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

IMPORTANT: When handling reservations, carefully review the conversation history before asking questions. 
- For booking a table, you need: customer name, date, time, and party size (phone is optional)
- NEVER ask for information the customer has already provided
- Check previous messages to see what information you already have
- Once you have all required information (name, date, time, party_size), call the book_table tool immediately
- If customer says "no" to phone number, proceed with booking using the information you have

Be efficient and avoid repetitive questions."""

# Create ReAct agent with memory
agent = create_react_agent(
    model=llm,
    tools=tools,
    checkpointer=memory
)

# Track which threads have received the system prompt
seen_threads = set()

# Lightweight per-thread slot tracker (process-local)
# Stores what booking details we've already extracted from user messages
booking_state: dict[str, dict[str, str]] = {}

# Regex patterns to extract booking information
NAME_PATTERNS = [
    re.compile(r"(?:my name is|i am|i'm|this is|call me|name'?s?)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", re.I),
    re.compile(r"^([A-Z][a-z]+)(?:\s+for\s+\d+)?$", re.I),  # Just a name like "dan" or "Dan for 5"
]
DATE_PATTERNS = [
    re.compile(r"\b(today|tomorrow|tonight)\b", re.I),
    re.compile(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.I),
    re.compile(r"\b(\d{4}-\d{1,2}-\d{1,2})\b"),               # 2025-10-21
    re.compile(r"\b(\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b"),        # 10/21 or 10/21/2025
    re.compile(r"\b(next\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b", re.I),
]
TIME_PATTERNS = [
    re.compile(r"\b(\d{1,2}:\d{2}\s?(?:am|pm)?)\b", re.I),    # 7:30 pm
    re.compile(r"\b(\d{1,2}\s?(?:am|pm))\b", re.I),            # 7 pm or 8pm
    re.compile(r"\bat\s+(\d{1,2}(?::\d{2})?\s?(?:am|pm)?)\b", re.I),
]
PARTY_PATTERNS = [
    re.compile(r"\bfor\s+(\d+)\s+(?:people|guests|persons|ppl)?\b", re.I),
    re.compile(r"\b(\d+)\s+(?:people|guests|persons|ppl)\b", re.I),
    re.compile(r"\bparty\s+of\s+(\d+)\b", re.I),
]
PHONE_PATTERNS = [
    re.compile(r"\b(\+?\d[\d\-\s]{7,}\d)\b"),
]

def extract_booking_info(text: str) -> dict[str, str]:
    """Extract booking information from user text using regex patterns."""
    info: dict[str, str] = {}
    
    # Extract name
    for pat in NAME_PATTERNS:
        m = pat.search(text)
        if m:
            info["name"] = m.group(1).strip().title()
            break
    
    # Extract date
    for pat in DATE_PATTERNS:
        m = pat.search(text)
        if m:
            info["date"] = m.group(1).strip()
            break
    
    # Extract time
    for pat in TIME_PATTERNS:
        m = pat.search(text)
        if m:
            val = m.group(1).strip()
            # Clean up "at " prefix if present
            info["time"] = re.sub(r"^at\s+", "", val, flags=re.I)
            break
    
    # Extract party size
    for pat in PARTY_PATTERNS:
        m = pat.search(text)
        if m:
            info["party_size"] = m.group(1).strip()
            break
    
    # Extract phone
    for pat in PHONE_PATTERNS:
        m = pat.search(text)
        if m:
            info["phone"] = m.group(1).strip()
            break
    
    return info

def summarize_booking_info(info: dict[str, str]) -> str:
    """Create a dynamic system message summarizing known booking details."""
    def has(k: str) -> bool:
        return bool(info.get(k))
    def val(k: str) -> str:
        return info.get(k, "unknown")

    required = ["name", "date", "time", "party_size"]
    missing = [k for k in required if not has(k)]

    summary = (
        f"BOOKING STATE - name: {val('name')}, date: {val('date')}, "
        f"time: {val('time')}, party_size: {val('party_size')}, phone: {val('phone')}.\n"
    )

    if missing:
        summary += (
            "MISSING: " + ", ".join(missing) + ". "
            "Ask ONLY for these missing fields in ONE concise question. DO NOT ask for fields you already have."
        )
    else:
        summary += (
            "All required fields present. Call book_table tool NOW with the information you have."
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
        
        # Inject system prompt only once per thread
        if thread_id not in seen_threads:
            messages.append(("system", system_prompt))
            seen_threads.add(thread_id)
        
        # Inject dynamic booking context if we have any state
        if state:
            summary_msg = summarize_booking_info(state)
            print(f"[agent] summary for {thread_id}: {summary_msg}")
            messages.append(("system", summary_msg))
        
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
