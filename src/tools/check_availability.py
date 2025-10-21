import os
import sys
from datetime import datetime, timedelta
import re
from dateutil import parser
from dotenv import load_dotenv
from langchain.tools import tool

# Add the src directory to the path to import db module
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from db import supabase

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
def check_table_availability(date: str, time: str = None, party_size: int = None) -> str:
    """
    Check table availability for a specific date and optionally time and party size.
    
    Args:
        date (str): Date to check availability. Accepts natural language like 'tomorrow', 'next Friday', 'August 15', or YYYY-MM-DD format.
        time (str, optional): Specific time to check in HH:MM format.
        party_size (int, optional): Number of people to accommodate.
        
    Returns:
        str: Availability information and suggestions.
    """
    try:
        # Parse natural language date input
        try:
            parsed_date = parse_natural_date(date)
            check_date = datetime.strptime(parsed_date, "%Y-%m-%d")
            today = datetime.now().date()
            if check_date.date() < today:
                return "Error: Cannot check availability for a past date."
        except ValueError as e:
            return f"Error: {str(e)}"
        
        # If specific time is provided, check that time slot
        if time:
            try:
                datetime.strptime(time, "%H:%M")
                hour = int(time.split(':')[0])
                if hour < 10 or hour >= 23:
                    return "Error: Restaurant is open from 10:00 AM to 11:00 PM. Please choose a time within these hours."
            except ValueError:
                return "Error: Invalid time format. Please use HH:MM format (24-hour)."
            
            return check_specific_time_availability(parsed_date, time, party_size)
        else:
            # Show availability for the entire day
            return show_daily_availability(parsed_date, party_size)
            
    except Exception as e:
        return f"Error: An unexpected error occurred while checking availability. Details: {str(e)}"

def check_specific_time_availability(date: str, time: str, party_size: int = None) -> str:
    """Check availability for a specific date and time."""
    try:
        # Get existing reservations for this time slot
        existing_reservations = supabase.table("bookings").select("*").eq("date", date).eq("time", time).execute()
        
        # Configuration from environment variables
        MAX_TABLES = int(os.getenv('MAX_TABLES', '10'))
        MAX_CAPACITY = int(os.getenv('MAX_CAPACITY_PER_TIME_SLOT', '50'))
        
        total_guests = 0
        tables_booked = 0
        
        if existing_reservations.data:
            total_guests = sum(reservation.get("guests", 0) for reservation in existing_reservations.data)
            tables_booked = len(existing_reservations.data)
        
        available_capacity = MAX_CAPACITY - total_guests
        available_tables = MAX_TABLES - tables_booked
        
        result = f"📅 Availability for {date} at {time}:\n\n"
        
        if party_size:
            if available_capacity >= party_size and available_tables > 0:
                result += f"✅ Available! We can accommodate your party of {party_size} people.\n"
                result += f"📊 Current status: {total_guests}/{MAX_CAPACITY} guests, {tables_booked}/{MAX_TABLES} tables booked\n"
            else:
                result += f"❌ Not available for {party_size} people.\n"
                result += f"📊 Current status: {total_guests}/{MAX_CAPACITY} guests, {tables_booked}/{MAX_TABLES} tables booked\n"
                
                if available_capacity > 0 and available_tables > 0:
                    result += f"💡 We can accommodate up to {min(available_capacity, 20)} people at this time.\n"
                
                # Get alternative suggestions
                alternatives = get_alternative_times_for_availability(date, time, party_size)
                if alternatives:
                    result += f"\n📅 Alternative times available:\n" + "\n".join(alternatives)
        else:
            if available_tables > 0:
                result += f"✅ Available! We have {available_tables} tables free.\n"
                result += f"📊 Current capacity: {available_capacity} people available (max {min(available_capacity, 20)} per table)\n"
            else:
                result += f"❌ Fully booked at this time.\n"
                result += f"📊 All {MAX_TABLES} tables are reserved\n"
        
        return result
        
    except Exception as e:
        return f"Error checking specific time availability: {str(e)}"

def show_daily_availability(date: str, party_size: int = None) -> str:
    """Show availability overview for the entire day."""
    try:
        # Get all reservations for the date
        all_reservations = supabase.table("bookings").select("*").eq("date", date).execute()
        
        # Group reservations by time
        reservations_by_time = {}
        if all_reservations.data:
            for reservation in all_reservations.data:
                time_slot = reservation.get("time", "")
                if time_slot not in reservations_by_time:
                    reservations_by_time[time_slot] = []
                reservations_by_time[time_slot].append(reservation)
        
        result = f"📅 Daily Availability Overview for {date}:\n\n"
        
        # Check each hour from 10 AM to 10 PM
        available_slots = []
        busy_slots = []
        
        for hour in range(10, 23):
            time_slot = f"{hour:02d}:00"
            
            if time_slot in reservations_by_time:
                reservations = reservations_by_time[time_slot]
                total_guests = sum(r.get("guests", 0) for r in reservations)
                tables_booked = len(reservations)
                
                available_capacity = 50 - total_guests
                available_tables = 10 - tables_booked
                
                if party_size:
                    if available_capacity >= party_size and available_tables > 0:
                        available_slots.append(f"✅ {time_slot} - Available for {party_size} people")
                    else:
                        busy_slots.append(f"❌ {time_slot} - Busy ({total_guests}/50 guests, {tables_booked}/10 tables)")
                else:
                    if available_tables > 0:
                        available_slots.append(f"✅ {time_slot} - {available_tables} tables, {available_capacity} people capacity")
                    else:
                        busy_slots.append(f"❌ {time_slot} - Fully booked")
            else:
                # No reservations for this time slot
                if party_size:
                    available_slots.append(f"✅ {time_slot} - Available for {party_size} people")
                else:
                    available_slots.append(f"✅ {time_slot} - Fully available (10 tables, 50 people capacity)")
        
        if available_slots:
            result += "🟢 Available Time Slots:\n" + "\n".join(available_slots)
        else:
            result += "❌ No available time slots"
            
        if busy_slots:
            result += f"\n\n🔴 Busy Time Slots:\n" + "\n".join(busy_slots)
        
        result += f"\n\n💡 To book a table, use: 'book a table for [X] people on {date} at [time] under [name]'"
        
        return result
        
    except Exception as e:
        return f"Error showing daily availability: {str(e)}"

def get_alternative_times_for_availability(date: str, requested_time: str, party_size: int) -> list:
    """Get alternative available time slots."""
    try:
        suggestions = []
        requested_hour = int(requested_time.split(':')[0])
        
        # Generate time slots (every hour from 10 AM to 10 PM)
        time_slots = [f"{hour:02d}:00" for hour in range(10, 23)]
        
        for time_slot in time_slots:
            if time_slot == requested_time:
                continue
                
            existing_reservations = supabase.table("bookings").select("*").eq("date", date).eq("time", time_slot).execute()
            
            total_guests_booked = 0
            tables_booked = 0
            
            if existing_reservations.data:
                total_guests_booked = sum(reservation.get("guests", 0) for reservation in existing_reservations.data)
                tables_booked = len(existing_reservations.data)
            
            if (total_guests_booked + party_size <= 50 and tables_booked < 10):
                hour_diff = abs(int(time_slot.split(':')[0]) - requested_hour)
                suggestions.append((hour_diff, f"✅ {time_slot} - Available for {party_size} people"))
        
        # Sort by time difference and return top 3 suggestions
        suggestions.sort(key=lambda x: x[0])
        return [suggestion[1] for suggestion in suggestions[:3]]
        
    except Exception as e:
        print(f"DEBUG: Error getting alternative times: {str(e)}")
        return []
