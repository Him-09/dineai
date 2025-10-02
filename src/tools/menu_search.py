import os
import sys
from langchain.tools import tool
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma

# Add the src directory to the path to import db module
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# Load environment variables
load_dotenv()

# Initialize the menu vectorstore globally
menu_vectorstore = None

def initialize_menu_vectorstore():
    """Initialize the menu vectorstore from PDF"""
    global menu_vectorstore
    
    try:
        # Path to the MENU PDF file from environment or default
        pdf_path = os.getenv('MENU_PDF_PATH')
        if not pdf_path:
            # Fallback to default path
            pdf_path = os.path.join(os.path.dirname(__file__), '..', '..', 'menu.pdf')
        
        # Check if PDF exists
        if not os.path.exists(pdf_path):
            print(f"⚠️ Menu PDF not found at: {pdf_path}")
            return None
        
        # Load PDF documents
        loader = PyPDFLoader(pdf_path)
        documents = loader.load()
        
        # Split documents into chunks
        text_splitter = RecursiveCharacterTextSplitter(
            separators=["\n\n", "\n", " ", ""],
            chunk_size=800, 
            chunk_overlap=50
        )
        menu_chunks = text_splitter.split_documents(documents)
        
        # Create embeddings and vectorstore
        embeddings = OpenAIEmbeddings()
        menu_vectorstore = Chroma.from_documents(
            menu_chunks, 
            embeddings, 
            collection_name="menu"
        )
        
        print(f"[SUCCESS] Menu vectorstore initialized with {len(menu_chunks)} chunks")
        return menu_vectorstore
        
    except Exception as e:
        print(f"[ERROR] Error initializing menu vectorstore: {str(e)}")
        return None

# Initialize vectorstore on module load
menu_vectorstore = initialize_menu_vectorstore()
@tool
def menu_search(query: str) -> str:
    """
    Search the restaurant menu by dish name, ingredients, dietary preferences, or cuisine type.
    Find specific dishes, get recommendations based on dietary restrictions, or explore menu categories.
    
    Args:
        query (str): Search query for menu items (e.g., "vegetarian options", "seafood", "chocolate dessert", "under $30")
        
    Returns:
        str: Menu items matching the search criteria with details
    """
    try:
        global menu_vectorstore
        
        # Check if vectorstore is available
        if menu_vectorstore is None:
            # Try to reinitialize
            menu_vectorstore = initialize_menu_vectorstore()
            if menu_vectorstore is None:
                return get_fallback_menu_response(query)
        
        # Perform semantic search
        try:
            # Search for relevant menu items
            relevant_items = menu_vectorstore.similarity_search(
                query,
                k=4  # Get top 4 most relevant items
            )
            
            if relevant_items:
                # Combine the relevant content
                combined_content = "\n\n".join([doc.page_content for doc in relevant_items])
                
                # Format the response
                response = f"🍽️ **Menu Search Results for: '{query}'**\n\n"
                response += f"📋 **From our Menu:**\n\n{combined_content}"
                
                # Add helpful note
                if len(combined_content) < 100:
                    response += "\n\n💡 For more detailed menu information, please ask your server or call us at (555) 123-4567."
                
                return response
            else:
                return get_fallback_menu_response(query)
                
        except Exception as search_error:
            print(f"Menu search error: {str(search_error)}")
            return get_fallback_menu_response(query)
        
    except Exception as e:
        print(f"Menu tool error: {str(e)}")
        return "I apologize, but I'm having trouble accessing the menu right now. Please ask your server for menu details or call us at (555) 123-4567."

@tool
def menu_recommendations(preferences: str) -> str:
    """
    Get personalized menu recommendations based on dietary preferences, budget, or specific requirements.
    Provides curated suggestions for the best dining experience.
    
    Args:
        preferences (str): Your preferences (e.g., "vegetarian under $25", "seafood lover", "gluten-free desserts", "romantic dinner for two")
        
    Returns:
        str: Personalized menu recommendations with explanations
    """
    try:
        global menu_vectorstore
        
        # Check if vectorstore is available
        if menu_vectorstore is None:
            # Try to reinitialize
            menu_vectorstore = initialize_menu_vectorstore()
            if menu_vectorstore is None:
                return get_fallback_recommendations(preferences)
        
        # Perform semantic search based on preferences
        try:
            # Search for relevant menu items based on preferences
            relevant_items = menu_vectorstore.similarity_search(
                preferences,
                k=5  # Get top 5 most relevant items
            )
            
            if relevant_items:
                # Combine the relevant content
                combined_content = "\n\n".join([doc.page_content for doc in relevant_items])
                
                # Format the response
                response = f"👨‍🍳 **Personalized Recommendations for: '{preferences}'**\n\n"
                response += f"📋 **Based on our Menu:**\n\n{combined_content}"
                
                # Add personalized note
                response += f"\n\n💡 **These recommendations are tailored to your preferences: '{preferences}'**"
                response += "\n🍽️ Would you like more details about any of these dishes or need assistance with dietary requirements?"
                
                return response
            else:
                return get_fallback_recommendations(preferences)
                
        except Exception as search_error:
            print(f"Menu recommendations error: {str(search_error)}")
            return get_fallback_recommendations(preferences)
            
    except Exception as e:
        print(f"Recommendations error: {str(e)}")
        return "I apologize, but I'm having trouble generating recommendations right now. Please ask your server for personalized suggestions."

def get_fallback_menu_response(query: str) -> str:
    """Provide fallback menu responses when vectorstore is not available"""
    
    query_lower = query.lower()
    
    if any(word in query_lower for word in ['vegetarian', 'veggie', 'vegan']):
        return """🌱 **Vegetarian & Vegan Options:**

**Appetizers:**
• Vegan Spring Rolls - $14 (V, GF)
• Truffle Arancini - $16 (Vegetarian)

**Mains:**
• Vegetarian Pasta - $24 (House-made tagliatelle with seasonal vegetables)
• Vegan Buddha Bowl - $22 (V, GF - Quinoa, roasted vegetables, tahini)

**Desserts:**
• Vegan Cheesecake - $10 (Cashew-based with berry compote)

*V = Vegan, GF = Gluten-Free*"""
    
    elif any(word in query_lower for word in ['seafood', 'fish', 'salmon', 'lobster', 'scallop']):
        return """🐟 **Seafood Selections:**

**Appetizers:**
• Seared Scallops - $18 (Pan-seared with cauliflower puree)
• Oysters Rockefeller - $19 (Fresh oysters with spinach and herbs)

**Mains:**
• Pan-Seared Salmon - $32 (Atlantic salmon with quinoa pilaf)
• Lobster Thermidor - $45 (Whole lobster with cream sauce)

All seafood is sourced daily for optimal freshness."""
    
    elif any(word in query_lower for word in ['meat', 'beef', 'steak', 'lamb']):
        return """🥩 **Premium Meats:**

**Mains:**
• Wagyu Ribeye - $65 (12oz premium wagyu with roasted vegetables)
• Osso Buco - $38 (Braised veal shank with saffron risotto)
• Duck Confit - $34 (Slow-cooked duck leg with wild rice)
• Lamb Rack - $42 (Herb-crusted with ratatouille)

All meats are sourced from premium suppliers and prepared to your preference."""
    
    elif any(word in query_lower for word in ['dessert', 'sweet', 'chocolate']):
        return """🍰 **Dessert Menu:**

• Chocolate Lava Cake - $12 (Warm cake with molten center)
• Tiramisu - $11 (Classic Italian with espresso)
• Vegan Cheesecake - $10 (Cashew-based, dairy-free)
• Crème Brûlée - $9 (Vanilla custard, gluten-free)
• Seasonal Fruit Tart - $11 (Fresh seasonal fruits)

Perfect ending to your dining experience!"""
    
    elif any(word in query_lower for word in ['drink', 'wine', 'cocktail', 'beverage']):
        return """🍷 **Beverage Menu:**

• **Wine Selection** ($8-25/glass) - Curated international wines
• **Craft Cocktails** ($12-18) - House-crafted with premium spirits
• **Fresh Juices** ($6-8) - Seasonal fruit juices
• **Coffee & Espresso** ($4-6) - Premium coffee drinks

Our sommelier can help pair wines with your meal."""
    
    else:
        return """🍽️ **Our Menu Categories:**

**🥗 Appetizers** ($14-19)
Start your meal with our signature starters

**🍖 Main Courses** ($22-65)
From pasta to premium steaks and fresh seafood

**🍰 Desserts** ($9-12)
Sweet endings to perfect your dining experience

**🍷 Beverages** ($4-25)
Wine, cocktails, and specialty drinks

Ask me about specific items, dietary options, or recommendations!"""

def get_fallback_recommendations(preferences: str) -> str:
    """Provide fallback recommendations"""
    return f"""👨‍🍳 **Based on '{preferences}', here are some popular choices:**

**🌟 Chef's Recommendations:**
• Pan-Seared Salmon ($32) - Our most popular seafood dish
• Wagyu Ribeye ($65) - Premium beef experience
• Vegetarian Pasta ($24) - Fresh, seasonal ingredients

**💡 Pro Tips:**
• Ask your server about daily specials
• Wine pairings available for all mains
• Dietary modifications available upon request

Would you like specific details about any dish or dietary accommodations?"""

def reload_menu_vectorstore():
    """Reload the menu vectorstore (useful after menu updates)"""
    global menu_vectorstore
    menu_vectorstore = initialize_menu_vectorstore()
    return "Menu vectorstore reloaded successfully!" if menu_vectorstore else "Failed to reload menu vectorstore."
