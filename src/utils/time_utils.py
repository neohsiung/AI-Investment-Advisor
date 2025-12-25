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
