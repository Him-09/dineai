import os
import sys
from datetime import datetime
from dotenv import load_dotenv
from langchain.tools import tool

# Add the src directory to the path to import db module
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from db import supabase

# Load environment variables
load_dotenv()

@tool
def cancel_reservation(reservation_id: int, reason: str = None) -> str:
    """
    Cancel an existing reservation at the restaurant.
    
    Args:
        reservation_id (int): The ID of the reservation to cancel.
        reason (str, optional): Reason for cancellation (for internal records).
        
    Returns:
        str: Confirmation message or error message.
    """
    try:
        # Validate reservation_id
        if not reservation_id or reservation_id <= 0:
            return "Error: Valid reservation ID is required."
        
        # Check if reservation exists
        existing_reservation = supabase.table("bookings").select("*").eq("id", reservation_id).execute()
        
        if not existing_reservation.data:
            return f"Error: No reservation found with ID {reservation_id}."
        
        current_reservation = existing_reservation.data[0]
        
        # Since we don't have a status column, we'll delete the reservation
        # In a production system, you might want to move it to a "cancelled_bookings" table
        # or add a status column to the bookings table
        
        # Delete the reservation from the database
        result = supabase.table("bookings").delete().eq("id", reservation_id).execute()
        
        if result.data:
            # Format the cancellation confirmation
            return (f"✅ Reservation successfully cancelled!\n\n"
                   f"Cancelled Reservation Details:\n"
                   f"• Reservation ID: {reservation_id}\n"
                   f"• Name: {current_reservation.get('name', 'N/A')}\n"
                   f"• Date: {current_reservation.get('date', 'N/A')}\n"
                   f"• Time: {current_reservation.get('time', 'N/A')}\n"
                   f"• Party Size: {current_reservation.get('guests', 'N/A')} people\n"
                   f"• Status: Cancelled and Removed\n"
                   f"• Cancelled at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                   f"Your reservation has been cancelled and removed from our system. "
                   f"The table is now available for other guests. "
                   f"We're sorry to see you go! If you'd like to make a new reservation in the future, "
                   f"please don't hesitate to contact us.")
        else:
            return "Error: Failed to cancel reservation. Please try again."
            
    except Exception as e:
        # Log the error for debugging
        error_message = str(e)
        print(f"DEBUG: Exception details: {error_message}")
        print(f"DEBUG: Exception type: {type(e)}")
        
        if "connection" in error_message.lower():
            return "Error: Unable to connect to the database. Please try again later."
        else:
            return f"Error: An unexpected error occurred while cancelling your reservation. Details: {error_message}"


@tool
def view_reservation(reservation_id: int) -> str:
    """
    View details of an existing reservation.
    
    Args:
        reservation_id (int): The ID of the reservation to view.
        
    Returns:
        str: Reservation details or error message.
    """
    try:
        # Validate reservation_id
        if not reservation_id or reservation_id <= 0:
            return "Error: Valid reservation ID is required."
        
        # Get reservation details
        reservation_result = supabase.table("bookings").select("*").eq("id", reservation_id).execute()
        
        if not reservation_result.data:
            return f"Error: No reservation found with ID {reservation_id}."
        
        reservation = reservation_result.data[0]
        
        return (f"📋 Reservation Details\n\n"
               f"• Reservation ID: {reservation_id}\n"
               f"• Name: {reservation.get('name', 'N/A')}\n"
               f"• Date: {reservation.get('date', 'N/A')}\n"
               f"• Time: {reservation.get('time', 'N/A')}\n"
               f"• Party Size: {reservation.get('guests', 'N/A')} people\n"
               f"• Status: ✅ Confirmed\n"
               f"• Created: {reservation.get('created_at', 'N/A')}\n\n"
               f"💡 You can modify or cancel this reservation if needed.")
            
    except Exception as e:
        # Log the error for debugging
        error_message = str(e)
        print(f"DEBUG: Exception details: {error_message}")
        print(f"DEBUG: Exception type: {type(e)}")
        
        if "connection" in error_message.lower():
            return "Error: Unable to connect to the database. Please try again later."
        else:
            return f"Error: An unexpected error occurred while retrieving your reservation. Details: {error_message}"
