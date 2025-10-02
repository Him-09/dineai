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
    
    Args:
        date_input (str): Natural language date like "tomorrow", "next Friday", "August 15", etc.
        
    Returns:
        str: Date in YYYY-MM-DD format
        
    Raises:
        ValueError: If date cannot be parsed
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
            if days_ahead <= 0:  # Target day already happened this week
                days_ahead += 7
            return (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        elif day_name in date_input and 'next' not in date_input:
            # Handle "this Friday", "Friday", etc.
            days_ahead = day_num - today.weekday()
            if days_ahead < 0:  # If the day already passed this week, get next week's
                days_ahead += 7
            elif days_ahead == 0:  # If it's today, assume they mean next week
                days_ahead = 7
            return (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    
    # Handle month names with day numbers
    months = {
        'january': 1, 'jan': 1, 'february': 2, 'feb': 2, 'march': 3, 'mar': 3,
        'april': 4, 'apr': 4, 'may': 5, 'june': 6, 'jun': 6,
        'july': 7, 'jul': 7, 'august': 8, 'aug': 8, 'september': 9, 'sep': 9,
        'october': 10, 'oct': 10, 'november': 11, 'nov': 11, 'december': 12, 'dec': 12
    }
    
    # Try to match "Month Day" or "Month Day, Year" patterns
    for month_name, month_num in months.items():
        if month_name in date_input:
            # Extract day number
            day_match = re.search(r'\b(\d{1,2})\b', date_input)
            if day_match:
                day = int(day_match.group(1))
                
                # Check if year is mentioned
                year_match = re.search(r'\b(20\d{2})\b', date_input)
                year = int(year_match.group(1)) if year_match else current_year
                
                # If the date would be in the past, assume next year
                try:
                    parsed_date = datetime(year, month_num, day).date()
                    if parsed_date < today:
                        parsed_date = datetime(year + 1, month_num, day).date()
                    return parsed_date.strftime("%Y-%m-%d")
                except ValueError:
                    continue  # Invalid date, try other parsing methods
    
    # Try to parse with dateutil for other formats
    try:
        # Add current year if not specified
        if not re.search(r'\b20\d{2}\b', date_input):
            date_input = f"{date_input} {current_year}"
        
        parsed_date = parser.parse(date_input, default=datetime(current_year, 1, 1)).date()
        
        # If parsed date is in the past, try next year
        if parsed_date < today:
            parsed_date = parser.parse(date_input, default=datetime(current_year + 1, 1, 1)).date()
        
        return parsed_date.strftime("%Y-%m-%d")
    except:
        pass
    
    # Check if it's already in YYYY-MM-DD format
    if re.match(r'^\d{4}-\d{2}-\d{2}$', date_input):
        return date_input
    
    # Check if it's in MM/DD or MM/DD/YYYY format
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

def check_availability(date: str, time: str, party_size: int) -> dict:
    """
    Check if a table is available for the given date, time, and party size.
    
    Args:
        date (str): Date for the reservation in YYYY-MM-DD format.
        time (str): Time for the reservation in HH:MM format.
        party_size (int): Number of people for the reservation.
        
    Returns:
        dict: {"available": bool, "message": str, "suggestions": list}
    """
    try:
        # Normalize time format for comparison (database stores as HH:MM:SS)
        time_patterns = [time, f"{time}:00"]  # Check both HH:MM and HH:MM:SS formats
        
        existing_reservations_data = []
        for time_pattern in time_patterns:
            reservations = supabase.table("bookings").select("*").eq("date", date).eq("time", time_pattern).execute()
            if reservations.data:
                existing_reservations_data.extend(reservations.data)
        
        # Remove duplicates if any
        seen_ids = set()
        unique_reservations = []
        for reservation in existing_reservations_data:
            if reservation['id'] not in seen_ids:
                unique_reservations.append(reservation)
                seen_ids.add(reservation['id'])
        
        # Restaurant capacity settings (you can adjust these)
        # Configuration from environment variables
        MAX_TABLES = int(os.getenv('MAX_TABLES', '10'))  # Total number of tables
        MAX_CAPACITY_PER_TIME_SLOT = int(os.getenv('MAX_CAPACITY_PER_TIME_SLOT', '50'))  # Maximum people that can be served at one time
        
        if unique_reservations:
            # Calculate total guests already booked for this time slot
            total_guests_booked = sum(reservation.get("guests", 0) for reservation in unique_reservations)
            
            # Check if adding this party would exceed capacity
            if total_guests_booked + party_size > MAX_CAPACITY_PER_TIME_SLOT:
                # Suggest alternative times
                suggestions = get_alternative_times(date, time, party_size)
                return {
                    "available": False,
                    "message": f"❌ Sorry, we don't have capacity for {party_size} people at {time} on {date}. "
                             f"We currently have {total_guests_booked} guests booked for that time slot. "
                             f"Our maximum capacity per time slot is {MAX_CAPACITY_PER_TIME_SLOT} guests.\n\n"
                             f"📅 Available alternatives:\n" + "\n".join(suggestions),
                    "suggestions": suggestions
                }
            
            # Check if we have reached maximum number of tables
            if len(unique_reservations) >= MAX_TABLES:
                suggestions = get_alternative_times(date, time, party_size)
                return {
                    "available": False,
                    "message": f"❌ Sorry, all {MAX_TABLES} tables are booked for {time} on {date}. "
                             f"📅 Available alternatives:\n" + "\n".join(suggestions),
                    "suggestions": suggestions
                }
        
        # If we reach here, the time slot is available
        return {
            "available": True,
            "message": f"✅ Table available for {party_size} people at {time} on {date}!",
            "suggestions": []
        }
        
    except Exception as e:
        print(f"DEBUG: Availability check error: {str(e)}")
        # If there's an error checking availability, allow the booking to proceed
        return {
            "available": True,
            "message": "⚠️ Unable to verify availability, but proceeding with booking.",
            "suggestions": []
        }

def get_alternative_times(date: str, requested_time: str, party_size: int) -> list:
    """
    Get alternative available time slots for the same date.
    
    Args:
        date (str): Date for the reservation in YYYY-MM-DD format.
        requested_time (str): Originally requested time in HH:MM format.
        party_size (int): Number of people for the reservation.
        
    Returns:
        list: List of alternative time suggestions
    """
    try:
        suggestions = []
        requested_hour = int(requested_time.split(':')[0])
        
        # Generate time slots (every hour from 10 AM to 10 PM)
        time_slots = [f"{hour:02d}:00" for hour in range(10, 23)]
        
        # Check each time slot for availability
        for time_slot in time_slots:
            if time_slot == requested_time:
                continue  # Skip the originally requested time
                
            # Check both time formats (HH:MM and HH:MM:SS)
            time_patterns = [time_slot, f"{time_slot}:00"]
            existing_reservations_data = []
            
            for time_pattern in time_patterns:
                reservations = supabase.table("bookings").select("*").eq("date", date).eq("time", time_pattern).execute()
                if reservations.data:
                    existing_reservations_data.extend(reservations.data)
            
            # Remove duplicates
            seen_ids = set()
            unique_reservations = []
            for reservation in existing_reservations_data:
                if reservation['id'] not in seen_ids:
                    unique_reservations.append(reservation)
                    seen_ids.add(reservation['id'])
            
            total_guests_booked = sum(reservation.get("guests", 0) for reservation in unique_reservations)
            tables_booked = len(unique_reservations)
            
            # Check if this time slot can accommodate the party
            if (total_guests_booked + party_size <= 50 and tables_booked < 10):
                # Prioritize times closer to the requested time
                hour_diff = abs(int(time_slot.split(':')[0]) - requested_hour)
                suggestions.append((hour_diff, f"• {time_slot} - Available for {party_size} people"))
        
        # Sort by time difference and return top 3 suggestions
        suggestions.sort(key=lambda x: x[0])
        return [suggestion[1] for suggestion in suggestions[:3]]
        
    except Exception as e:
        print(f"DEBUG: Error getting alternative times: {str(e)}")
        return ["• Please call us at (555) 123-4567 for availability"]

@tool
def book_table(name: str, date: str, time: str, party_size: int, phone: str | None = None) -> str:
    """
    Book a table at a restaurant.
    
    Args:
        name (str): Name of the client.
        date (str): Date for the reservation. Accepts natural language like 'tomorrow', 'next Friday', 'August 15', or YYYY-MM-DD format.
        time (str): Time for the reservation in HH:MM format.
        party_size (int): Number of people for the reservation.
        phone (str, optional): Phone number for the reservation.
        
    Returns:
        str: Short confirmation message or error message.
    """
    try:
        # Validate input parameters
        if not name or not name.strip():
            return "Error: Name is required and cannot be empty."
        
        if party_size <= 0:
            return "Error: Party size must be a positive number."
        
        if party_size > 20:
            return "Error: Party size cannot exceed 20 people. Please contact us directly for larger groups."
        
        # Parse natural language date input
        try:
            parsed_date = parse_natural_date(date)
            # Validate the parsed date
            reservation_date = datetime.strptime(parsed_date, "%Y-%m-%d")
            today = datetime.now().date()
            if reservation_date.date() < today:
                return "Error: Cannot book a table for a past date."
        except ValueError as e:
            return f"Error: {str(e)}"
        
        # Validate time format
        try:
            reservation_time = datetime.strptime(time, "%H:%M")
            # Check if time is within restaurant hours (assuming 10:00 AM to 11:00 PM)
            hour = reservation_time.hour
            if hour < 10 or hour >= 23:
                return "Error: Restaurant is open from 10:00 AM to 11:00 PM. Please choose a time within these hours."
        except ValueError:
            return "Error: Invalid time format. Please use HH:MM format (24-hour)."
        
        # Check availability before booking
        availability_check = check_availability(parsed_date, time, party_size)
        if not availability_check["available"]:
            return availability_check["message"]
        
        # Prepare reservation data
        reservation_data = {
            "name": name.strip(),
            "date": parsed_date,
            "time": time,
            "guests": party_size
        }
        
        # Add phone number if provided
        if phone and phone.strip():
            reservation_data["phone"] = phone.strip()
        
        # Insert reservation into database
        result = supabase.table("bookings").insert(reservation_data).execute()
        
        if result.data:
            reservation_id = result.data[0].get("id", "N/A")
            # Format the date nicely for display
            display_date = datetime.strptime(parsed_date, "%Y-%m-%d").strftime("%A, %B %d, %Y")
            
            # Build confirmation message
            confirmation = (f"✅ Table successfully booked!\n"
                           f"Reservation Details:\n"
                           f"• Name: {name}\n"
                           f"• Date: {display_date}\n"
                           f"• Time: {time}\n"
                           f"• Party Size: {party_size} people\n")
            
            if phone and phone.strip():
                confirmation += f"• Phone: {phone.strip()}\n"
            
            confirmation += (f"• Reservation ID: {reservation_id}\n"
                            f"• Status: Confirmed\n\n"
                            f"Please arrive 15 minutes before your reservation time. "
                            f"If you need to cancel or modify your reservation, please contact us with your reservation ID.")
            
            return confirmation
        else:
            return "Error: Failed to create reservation. Please try again."
            
    except Exception as e:
        # Log the error for debugging (you might want to use proper logging)
        error_message = str(e)
        print(f"DEBUG: Exception details: {error_message}")  # Added for debugging
        print(f"DEBUG: Exception type: {type(e)}")  # Added for debugging
        
        if "duplicate" in error_message.lower():
            return "Error: A reservation already exists for this date and time. Please choose a different time slot."
        elif "connection" in error_message.lower():
            return "Error: Unable to connect to the database. Please try again later."
        else:
            return f"Error: An unexpected error occurred while booking your table. Details: {error_message}"
    