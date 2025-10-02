import os
import sys
from datetime import datetime, timedelta
import re
from dateutil import parser
from dotenv import load_dotenv
from langchain.tools import tool

# Add the src directory to the path to import db module
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from ..db import supabase

# Load environment variables
load_dotenv()

def parse_natural_date(date_input: str) -> str:
    """
    Parse natural language date input into YYYY-MM-DD format.
    Same function as in book_table.py for consistency.
    """
    date_input = date_input.strip().lower()
    today = datetime.now().date()
    current_year = today.year
    
    # Handle relative dates
    if date_input in ['today']:
        return today.strftime("%Y-%m-%d")
    elif date_input in ['tomorrow']:
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")
    elif date_input in ['day after tomorrow']:
        return (today + timedelta(days=2)).strftime("%Y-%m-%d")
    elif 'next week' in date_input:
        return (today + timedelta(days=7)).strftime("%Y-%m-%d")
    
    # Handle "next [weekday]"
    weekdays = {
        'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
        'friday': 4, 'saturday': 5, 'sunday': 6
    }
    
    for day_name, day_num in weekdays.items():
        if f'next {day_name}' in date_input:
            days_ahead = day_num - today.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            return (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        elif day_name in date_input and 'next' not in date_input:
            days_ahead = day_num - today.weekday()
            if days_ahead < 0:
                days_ahead += 7
            elif days_ahead == 0:
                days_ahead = 7
            return (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    
    # Handle month names with day numbers
    months = {
        'january': 1, 'jan': 1, 'february': 2, 'feb': 2, 'march': 3, 'mar': 3,
        'april': 4, 'apr': 4, 'may': 5, 'june': 6, 'jun': 6,
        'july': 7, 'jul': 7, 'august': 8, 'aug': 8, 'september': 9, 'sep': 9,
        'october': 10, 'oct': 10, 'november': 11, 'nov': 11, 'december': 12, 'dec': 12
    }
    
    for month_name, month_num in months.items():
        if month_name in date_input:
            day_match = re.search(r'\b(\d{1,2})\b', date_input)
            if day_match:
                day = int(day_match.group(1))
                year_match = re.search(r'\b(20\d{2})\b', date_input)
                year = int(year_match.group(1)) if year_match else current_year
                
                try:
                    parsed_date = datetime(year, month_num, day).date()
                    if parsed_date < today:
                        parsed_date = datetime(year + 1, month_num, day).date()
                    return parsed_date.strftime("%Y-%m-%d")
                except ValueError:
                    continue
    
    # Try dateutil parser
    try:
        if not re.search(r'\b20\d{2}\b', date_input):
            date_input = f"{date_input} {current_year}"
        
        parsed_date = parser.parse(date_input, default=datetime(current_year, 1, 1)).date()
        if parsed_date < today:
            parsed_date = parser.parse(date_input, default=datetime(current_year + 1, 1, 1)).date()
        
        return parsed_date.strftime("%Y-%m-%d")
    except:
        pass
    
    # Check if already in YYYY-MM-DD format
    if re.match(r'^\d{4}-\d{2}-\d{2}$', date_input):
        return date_input
    
    # Check MM/DD format
    date_match = re.match(r'^(\d{1,2})/(\d{1,2})(?:/(\d{4}))?$', date_input)
    if date_match:
        month, day, year = date_match.groups()
        year = int(year) if year else current_year
        try:
            parsed_date = datetime(year, int(month), int(day)).date()
            if parsed_date < today and not year:
                parsed_date = datetime(year + 1, int(month), int(day)).date()
            return parsed_date.strftime("%Y-%m-%d")
        except ValueError:
            pass
    
    raise ValueError(f"Unable to parse date: '{date_input}'. Please try formats like 'tomorrow', 'next Friday', 'August 15', or 'YYYY-MM-DD'.")

@tool
def modify_reservation(reservation_id: int, name: str = None, date: str = None, time: str = None, party_size: int = None) -> str:
    """
    Modify an existing reservation at the restaurant.
    
    Args:
        reservation_id (int): The ID of the reservation to modify.
        name (str, optional): New name for the reservation.
        date (str, optional): New date for the reservation. Accepts natural language like 'tomorrow', 'next Friday', 'August 15', or YYYY-MM-DD format.
        time (str, optional): New time for the reservation in HH:MM format.
        party_size (int, optional): New party size for the reservation.
        
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
        
        # Prepare update data - only include fields that are being changed
        update_data = {}
        changes_made = []
        
        # Validate and process name change
        if name is not None:
            if not name.strip():
                return "Error: Name cannot be empty."
            update_data["name"] = name.strip()
            changes_made.append(f"Name: {current_reservation['name']} → {name.strip()}")
        
        # Validate and process date change
        if date is not None:
            try:
                parsed_date = parse_natural_date(date)
                reservation_date = datetime.strptime(parsed_date, "%Y-%m-%d")
                today = datetime.now().date()
                if reservation_date.date() < today:
                    return "Error: Cannot modify reservation to a past date."
                update_data["date"] = parsed_date
                display_date = reservation_date.strftime("%A, %B %d, %Y")
                current_display_date = datetime.strptime(current_reservation['date'], "%Y-%m-%d").strftime("%A, %B %d, %Y")
                changes_made.append(f"Date: {current_display_date} → {display_date}")
            except ValueError as e:
                return f"Error: {str(e)}"
            changes_made.append(f"Name: {current_reservation['name']} → {name.strip()}")
        
        # Validate and process date change
        if date is not None:
            try:
                reservation_date = datetime.strptime(date, "%Y-%m-%d")
                # Check if the date is not in the past
                today = datetime.now().date()
                if reservation_date.date() < today:
                    return "Error: Cannot modify reservation to a past date."
                update_data["date"] = date
                changes_made.append(f"Date: {current_reservation['date']} → {date}")
            except ValueError:
                return "Error: Invalid date format. Please use YYYY-MM-DD format."
        
        # Validate and process time change
        if time is not None:
            try:
                reservation_time = datetime.strptime(time, "%H:%M")
                # Check if time is within restaurant hours (10:00 AM to 11:00 PM)
                hour = reservation_time.hour
                if hour < 10 or hour >= 23:
                    return "Error: Restaurant is open from 10:00 AM to 11:00 PM. Please choose a time within these hours."
                update_data["time"] = time
                changes_made.append(f"Time: {current_reservation['time']} → {time}")
            except ValueError:
                return "Error: Invalid time format. Please use HH:MM format (24-hour)."
        
        # Validate and process party size change
        if party_size is not None:
            if party_size <= 0:
                return "Error: Party size must be a positive number."
            if party_size > 20:
                return "Error: Party size cannot exceed 20 people. Please contact us directly for larger groups."
            update_data["guests"] = party_size
            changes_made.append(f"Party Size: {current_reservation['guests']} → {party_size} people")
        
        # Check if any changes were provided
        if not update_data:
            return "Error: No changes provided. Please specify what you'd like to modify (name, date, time, or party_size)."
        
        # Update the reservation in database
        result = supabase.table("bookings").update(update_data).eq("id", reservation_id).execute()
        
        if result.data:
            updated_reservation = result.data[0]
            changes_text = "\n".join([f"• {change}" for change in changes_made])
            
            return (f"✅ Reservation successfully modified!\n\n"
                   f"Updated Reservation Details:\n"
                   f"• Reservation ID: {reservation_id}\n"
                   f"• Name: {updated_reservation.get('name', 'N/A')}\n"
                   f"• Date: {updated_reservation.get('date', 'N/A')}\n"
                   f"• Time: {updated_reservation.get('time', 'N/A')}\n"
                   f"• Party Size: {updated_reservation.get('guests', 'N/A')} people\n\n"
                   f"Changes Made:\n{changes_text}\n\n"
                   f"Please arrive 15 minutes before your reservation time. "
                   f"If you need to make further changes, please contact us with your reservation ID.")
        else:
            return "Error: Failed to update reservation. Please try again."
            
    except Exception as e:
        # Log the error for debugging
        error_message = str(e)
        print(f"DEBUG: Exception details: {error_message}")
        print(f"DEBUG: Exception type: {type(e)}")
        
        if "duplicate" in error_message.lower():
            return "Error: A reservation already exists for the new date and time. Please choose a different time slot."
        elif "connection" in error_message.lower():
            return "Error: Unable to connect to the database. Please try again later."
        else:
            return f"Error: An unexpected error occurred while modifying your reservation. Details: {error_message}"
