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

# Initialize the vectorstore globally
vectorstore = None

def initialize_faq_vectorstore():
    """Initialize the FAQ vectorstore from PDF"""
    global vectorstore
    
    try:
        # Path to the FAQ PDF file from environment or default
        pdf_path = os.getenv('FAQ_PDF_PATH')
        if not pdf_path:
            # Fallback to default path
            pdf_path = os.path.join(os.path.dirname(__file__), '..', '..', 'RESTAURANT_FAQ.pdf')
        
        # Check if PDF exists
        if not os.path.exists(pdf_path):
            print(f"⚠️ FAQ PDF not found at: {pdf_path}")
            return None
        
        # Load PDF documents
        loader = PyPDFLoader(pdf_path)
        documents = loader.load()
        
        # Split documents into chunks
        text_splitter = RecursiveCharacterTextSplitter(
            separators=["\n\n", "\n", " ", ""],
            chunk_size=1000, 
            chunk_overlap=100
        )
        faq_chunks = text_splitter.split_documents(documents)
        
        # Create embeddings and vectorstore
        embeddings = OpenAIEmbeddings()
        vectorstore = Chroma.from_documents(
            faq_chunks, 
            embeddings, 
            collection_name="restaurant_faq"
        )
        
        print(f"[SUCCESS] FAQ vectorstore initialized with {len(faq_chunks)} chunks")
        return vectorstore
        
    except Exception as e:
        print(f"[ERROR] Error initializing FAQ vectorstore: {str(e)}")
        return None

# Initialize vectorstore on module load
vectorstore = initialize_faq_vectorstore()

@tool
def restaurant_faq(question: str) -> str:
    """
    Answer frequently asked questions about the restaurant by searching through
    the restaurant FAQ PDF document using semantic search. Covers hours, policies, 
    location, menu, dress code, payment, contact info, and special events.
    
    Args:
        question (str): The customer's question about the restaurant
        
    Returns:
        str: Answer to the question from the FAQ document
    """
    try:
        global vectorstore
        
        # Check if vectorstore is available
        if vectorstore is None:
            # Try to reinitialize
            vectorstore = initialize_faq_vectorstore()
            if vectorstore is None:
                return get_fallback_faq_response(question)
        
        # Perform semantic search
        try:
            # Search for relevant documents
            relevant_docs = vectorstore.similarity_search(
                question, 
                k=3  # Get top 3 most relevant chunks
            )
            
            if relevant_docs:
                # Combine the relevant content
                combined_content = "\n\n".join([doc.page_content for doc in relevant_docs])
                
                # Format the response
                response = f"📋 **From our FAQ:**\n\n{combined_content}"
                
                # Add contact info if response seems incomplete
                if len(combined_content) < 100:
                    response += "\n\n💡 For more detailed information, please call us at (555) 123-4567."
                
                return response
            else:
                return get_fallback_faq_response(question)
                
        except Exception as search_error:
            print(f"Search error: {str(search_error)}")
            return get_fallback_faq_response(question)
        
    except Exception as e:
        print(f"FAQ tool error: {str(e)}")
        return "I apologize, but I'm having trouble accessing the FAQ information right now. Please contact us directly at (555) 123-4567 for immediate assistance."

def get_fallback_faq_response(question: str) -> str:
    """Provide fallback responses when vectorstore is not available"""
    
    question_lower = question.lower()
    
    # Simple keyword-based fallback responses
    if any(word in question_lower for word in ['hours', 'open', 'close', 'time']):
        return """🕐 **Restaurant Hours:**
        
Monday - Thursday: 10:00 AM - 11:00 PM
Friday - Saturday: 10:00 AM - 12:00 AM (Midnight)
Sunday: 10:00 AM - 10:00 PM

We accept reservations during all operating hours. Last seating is 30 minutes before closing time."""
    
    elif any(word in question_lower for word in ['policy', 'cancel', 'change', 'modify']):
        return """📋 **Reservation Policy:**

• Reservations can be made up to 30 days in advance
• We accommodate parties of 1-20 people  
• Free changes up to 2 hours before your reservation
• Free cancellation up to 2 hours before your reservation
• No-show fees may apply for parties of 8 or more
• Parties over 20 people require special arrangements"""
    
    elif any(word in question_lower for word in ['location', 'address', 'parking', 'where']):
        return """📍 **Location & Parking:**

• Address: 123 Main Street, Downtown City, State 12345
• Parking: Complimentary valet parking available
• Public Transit: 2 blocks from Central Station
• Nearby Landmarks: Across from City Hall, next to Grand Theater
• Accessibility: Wheelchair accessible entrance and restrooms"""
    
    elif any(word in question_lower for word in ['menu', 'food', 'dietary', 'vegan', 'vegetarian', 'gluten']):
        return """🍽️ **Menu & Dietary Information:**

• Cuisine: Modern American with international influences
• Dietary Options: Vegetarian, vegan, and gluten-free options available
• Allergies: Please inform us of any allergies when booking or upon arrival
• Kids Menu: Children's menu available for ages 12 and under
• Price Range: $25-45 per entree, $8-15 appetizers"""
    
    elif any(word in question_lower for word in ['dress', 'attire', 'clothing', 'wear']):
        return """👔 **Dress Code:**

• Smart Casual is our preferred dress code
• Acceptable: Business casual, nice jeans with dress shirt, dresses, slacks
• Not Recommended: Athletic wear, flip-flops, tank tops, torn clothing
• Special Events: Formal attire may be required for special occasions"""
    
    elif any(word in question_lower for word in ['payment', 'pay', 'credit', 'cash', 'tip']):
        return """💳 **Payment & Gratuity:**

• Payment Methods: We accept all major credit cards, cash, and contactless payments
• Gratuity: 18% gratuity is automatically added to parties of 8 or more
• Split Bills: We can accommodate split payments for up to 4 cards
• Gift Cards: Restaurant gift cards available for purchase"""
    
    elif any(word in question_lower for word in ['contact', 'phone', 'email', 'call']):
        return """📞 **Contact Information:**

• Phone: (555) 123-4567
• Email: reservations@restaurant.com
• Website: www.restaurant.com
• Social Media: @RestaurantName on Instagram, Facebook, Twitter
• Hours for Calls: Monday-Sunday, 9:00 AM - 9:00 PM"""
    
    elif any(word in question_lower for word in ['events', 'party', 'birthday', 'private', 'celebration']):
        return """🎉 **Special Events & Private Dining:**

• Private Dining Room: Available for groups of 15-40 people
• Birthday Celebrations: Complimentary dessert with advance notice
• Anniversary Packages: Special menu and wine pairings available
• Corporate Events: Business lunch and dinner packages
• Catering: Off-site catering available for events"""
    
    else:
        return """❓ **I'd be happy to help!** 

I can provide information about:

🕐 **Restaurant Hours** - Operating times and schedules
📋 **Reservation Policies** - Booking, changes, and cancellation rules  
📍 **Location & Parking** - Address, directions, and parking info
🍽️ **Menu & Dietary Options** - Food, dietary restrictions, and cuisine
👔 **Dress Code** - Appropriate attire guidelines
💳 **Payment & Tipping** - Accepted payment methods and gratuity
📞 **Contact Information** - Phone, email, and social media
🎉 **Special Events** - Private dining, celebrations, and catering

Please ask me about any of these topics, or contact us directly at (555) 123-4567 for immediate assistance."""

def reload_faq_vectorstore():
    """Reload the FAQ vectorstore (useful after PDF updates)"""
    global vectorstore
    vectorstore = initialize_faq_vectorstore()
    return "FAQ vectorstore reloaded successfully!" if vectorstore else "Failed to reload FAQ vectorstore."
    