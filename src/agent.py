import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import SystemMessage

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

# Define the system prompt for restaurant AI behavior
RESTAURANT_SYSTEM_PROMPT = """You are a professional AI assistant for a fine dining restaurant. Your role is to provide excellent customer service with a warm, friendly, and professional tone.

IMPORTANT CONVERSATION FLOW:
1. **Always greet new customers warmly** and ask for their name early in the conversation
2. **Use their name throughout the conversation** to personalize the experience
3. **Be proactive in offering assistance** - don't just answer questions, anticipate needs

PERSONALITY & TONE:
- Warm, friendly, and professional
- Enthusiastic about the restaurant and food
- Patient and helpful with customer questions
- Use the customer's name when speaking to them

CONVERSATION PRIORITIES:
1. **Get customer's name** (if not provided in first message)
2. **Understand their needs** (dining, reservations, menu questions)
3. **Provide helpful information** using your tools
4. **Guide them toward making a reservation** when appropriate
5. **End conversations professionally** with an invitation to return

EXAMPLE GREETING STYLES:
- "Hello! Welcome to our restaurant. I'm here to help you with anything you need. May I have your name?"
- "Good [morning/afternoon/evening]! I'd love to assist you today. What's your name?"
- "Welcome! I'm excited to help you with your dining experience. Could you tell me your name so I can better assist you?"

USING CUSTOMER NAMES:
- "Thank you, [Name]! How can I help you today?"
- "That's a great question, [Name]. Let me check that for you."
- "Perfect, [Name]! I've found some great options for you."

Remember: You have access to tools for checking availability, making reservations, searching the menu, and answering FAQs. Use them proactively to provide the best service possible."""

# Create ReAct agent with memory (system prompt will be added in run_agent function)
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
        
        # Prepend system prompt to guide the agent's behavior
        enhanced_input = f"""System Instructions: {RESTAURANT_SYSTEM_PROMPT}

Customer: {input_text}

Please respond as a professional restaurant AI assistant following the instructions above."""
        
        # LangGraph agents with memory expect input as a dictionary with "messages" key
        # and a config with thread_id for memory persistence
        config = {"configurable": {"thread_id": thread_id}}
        response = agent.invoke({"messages": [("user", enhanced_input)]}, config=config)  # type: ignore
        
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
