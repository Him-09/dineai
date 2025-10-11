import os
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

IMPORTANT BOOKING GUIDELINES:
- When a customer wants to make a reservation, you MUST collect the following information before booking:
  1. Customer's name (REQUIRED - always ask if not provided)
  2. Date of reservation
  3. Time preference
  4. Number of people (party size)
  5. Phone number (optional but recommended)

- If a customer requests a booking but hasn't provided their name, you MUST ask for it before proceeding with the booking.
- Be polite and professional when asking for information.
- Example: "I'd be happy to help you with that reservation! May I have your name please?"

CONVERSATION FLOW FOR BOOKINGS:
1. Acknowledge the booking request
2. Ask for missing required information (especially name)
3. Confirm all details with the customer
4. Only then use the book_table tool

Be friendly, helpful, and ensure all required information is collected before making any reservation."""

# Create ReAct agent with memory and system prompt
agent = create_react_agent(
    model=llm, 
    tools=tools,
    checkpointer=memory
)

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
        
        # LangGraph agents with memory expect input as a dictionary with "messages" key
        # and a config with thread_id for memory persistence
        config = {"configurable": {"thread_id": thread_id}}
        
        # Include system prompt and user message
        messages = [
            ("system", system_prompt),
            ("user", input_text)
        ]
        
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
