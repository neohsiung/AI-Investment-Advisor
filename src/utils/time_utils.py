import os
from datetime import datetime
import pytz

# Default timezone
DEFAULT_TIMEZONE = "Asia/Taipei"

def get_timezone():
    """
    Get the timezone object based on environment variable or default.
    """
    tz_name = os.getenv("TIMEZONE", DEFAULT_TIMEZONE)
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
