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
    將使用者時區的時間字串 (HH:MM) 轉換為系統時區 (UTC/Local)。
    
    Used for scheduling jobs to run at the correct user time.
    用於排程工作，確保在正確的使用者時間執行。
    """
    try:
        user_tz = get_timezone()
        
        # Create a dummy datetime with today's date and the user's target time
        # 建立一個包含今日日期與使用者目標時間的 datetime 物件
        now = datetime.now(user_tz)
        target_time = datetime.strptime(time_str, "%H:%M").time()
        user_dt = now.replace(hour=target_time.hour, minute=target_time.minute, second=0, microsecond=0)
        
        # Convert to UTC (or system local time effectively)
        # 轉換為 UTC (或有效的系統本地時間)
        # Assuming container runs in UTC. If container has local timezone set, this needs 'datetime.now().astimezone()' logic.
        # 假設容器運行在 UTC 環境。若容器設定了本地時區，則需要調整。
        
        # Best practice: Convert to UTC, then strip tzinfo
        # 最佳實踐：轉換為 UTC，然後移除時區資訊
        utc_dt = user_dt.astimezone(pytz.utc)
        
        # If the system is NOT UTC, we might need system local.
        # Check system offset
        # But for Docker/Cloud, UTC is standard. We assume system is UTC.
        
        # Calculate day offset (e.g., -1 if crossed midnight backwards, +1 if forwards)
        # 計算日期偏移量 (例如：若跨越午夜向前則為 -1，向後則為 +1)
        # simplistic check: comparison of user_dt vs utc_dt isn't enough because of date.
        # 簡單檢查：僅比較 user_dt 與 utc_dt 是不夠的，因為日期可能不同。
        # We check the date difference.
        # 我們檢查日期的差異。
        
        day_offset = (utc_dt.date() - user_dt.date()).days
        
        return utc_dt.strftime("%H:%M"), day_offset
        
    except Exception as e:
        print(f"Time conversion error: {e}")
        return time_str, 0 # Fallback to original

def get_current_utc_time():
    """
    Get current UTC time.
    """
    return datetime.now(pytz.utc)
