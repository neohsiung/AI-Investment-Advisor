import os
from datetime import datetime
import pytz
from src.data.database import get_db_connection
from sqlalchemy import text

# Default timezone
DEFAULT_TIMEZONE = "Asia/Taipei"

def get_db_timezone():
    """
    Attempt to fetch the display timezone from the database.
    Returns None if not found or error.
    """
    try:
        conn = get_db_connection()
        # Assuming 'SYSTEM' user or global setting for display timezone
        # We check for a setting with key 'DISPLAY_TIMEZONE' for user 'SYSTEM' first, then generic
        query = text("SELECT value FROM settings WHERE key='DISPLAY_TIMEZONE' ORDER BY user_id DESC LIMIT 1")
        result = conn.execute(query).fetchone()
        conn.close()
        if result:
            return result[0]
    except Exception:
        # DB might not be ready or reachable
        pass
    return None

def get_timezone():
    """
    Get the timezone object based on DB setting, environment variable, or default.
    Priority: DB > Env Var > Default
    """
    # 1. Try DB
    db_tz = get_db_timezone()
    tz_name = db_tz if db_tz else os.getenv("TIMEZONE", DEFAULT_TIMEZONE)
    
    try:
        return pytz.timezone(tz_name)
    except pytz.UnknownTimeZoneError:
        return pytz.timezone(DEFAULT_TIMEZONE)

def get_current_time():
    """
    Get the current time in the configured timezone.
    """
    tz = get_timezone()
    return datetime.now(tz)

def format_time(dt=None, fmt="%Y-%m-%d %H:%M:%S"):
    """
    Format a datetime object (or current time) as a string.
    """
    if dt is None:
        dt = get_current_time()
    return dt.strftime(fmt)

def get_current_date_str():
    """
    Get current date string YYYY-MM-DD in configured timezone.
    """
    return format_time(fmt="%Y-%m-%d")

def convert_user_time_to_system_time(time_str):
    """
    Convert a time string (HH:MM) from User Timezone to System Timezone (UTC/Local).
    Used for scheduling jobs to run at the correct user time.
    """
    try:
        user_tz = get_timezone()
        
        # Create a dummy datetime with today's date and the user's target time
        now = datetime.now(user_tz)
        target_time = datetime.strptime(time_str, "%H:%M").time()
        user_dt = now.replace(hour=target_time.hour, minute=target_time.minute, second=0, microsecond=0)
        
        # Convert to UTC (or system local time effectively)
        # Assuming container runs in UTC. If container has local timezone set, this needs 'datetime.now().astimezone()' logic.
        # But 'schedule' library uses naive datetime.now().
        
        # Best practice: Convert to UTC, then strip tzinfo
        utc_dt = user_dt.astimezone(pytz.utc)
        
        # If the system is NOT UTC, we might need system local.
        # Check system offset
        # But for Docker/Cloud, UTC is standard. We assume system is UTC.
        
        return utc_dt.strftime("%H:%M")
        
    except Exception as e:
        print(f"Time conversion error: {e}")
        return time_str # Fallback to original
