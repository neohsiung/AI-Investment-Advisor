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
    嘗試從資料庫獲取顯示時區。若未找到或發生錯誤則回傳 None。
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
        pass # nosec
    return None

def get_timezone():
    """
    Get the timezone object based on DB setting, environment variable, or default.
    Priority: DB > Env Var > Default
    根據資料庫設定、環境變數或預設值獲取時區物件。
    優先順序：資料庫 > 環境變數 > 預設值
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
    Get the current time in the configured (Display) timezone.
    獲取設定（顯示）時區的目前時間。
    """
    tz = get_timezone()
    return datetime.now(tz)

def get_system_timezone():
    """
    Get the system local timezone.
    獲取系統本地時區。
    """
    system_tz = datetime.now().astimezone().tzinfo
    return system_tz

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
    將使用者時區的時間字串 (HH:MM) 轉換為系統時區 (UTC/Local)。
    
    Used for scheduling jobs to run at the correct user time.
    用於排程工作，確保在正確的使用者時間執行。
    """
    try:
        # Defensive: strip extraneous quotes from DB values
        time_str = time_str.strip().strip('"').strip("'")
        user_tz = get_timezone()
        system_tz = get_system_timezone()
        
        # Create a dummy datetime with today's date and the user's target time
        now = datetime.now(user_tz)
        target_time = datetime.strptime(time_str, "%H:%M").time()
        user_dt = now.replace(hour=target_time.hour, minute=target_time.minute, second=0, microsecond=0)
        
        # Convert to System Local Time (since schedule library uses local time)
        # 轉換為系統本地時間 (因為 schedule 函式庫使用本地時間)
        sys_dt = user_dt.astimezone(system_tz)
        
        # Calculate day offset
        day_offset = (sys_dt.date() - user_dt.date()).days
        
        return sys_dt.strftime("%H:%M"), day_offset
        
    except Exception as e:
        print(f"Time conversion error: {e}")
        return time_str, 0 # Fallback to original

def get_current_utc_time():
    """
    Get current UTC time.
    獲取目前 UTC 時間。
    """
    return datetime.now(pytz.utc)
