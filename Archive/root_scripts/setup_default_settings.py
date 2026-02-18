#!/usr/bin/env python3
"""
設定預設系統設定
Setup default system settings for notifications and scheduler
"""

from src.data.database import get_db_connection
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def setup_settings():
    user_id = '90693c07-6177-42df-97d9-915f3ce7c573'
    conn = get_db_connection()
    
    # Default settings to insert/update
    settings = {
        # Scheduler settings (SYSTEM level)
        ('SYSTEM', 'schedule_daily', '09:00'),
        ('SYSTEM', 'schedule_daily_days', 'monday,tuesday,wednesday,thursday,friday'),
        ('SYSTEM', 'schedule_weekly', '09:00'),
        ('SYSTEM', 'schedule_weekly_day', 'saturday'),
        ('SYSTEM', 'scheduler_reload_signal', 'false'),
        
        # Channel settings (User level) - Web only by default
        (user_id, 'channel_web_enabled', 'true'),
        (user_id, 'channel_line_enabled', 'false'),
        (user_id, 'channel_email_enabled', 'false'),
        (user_id, 'channel_telegram_enabled', 'false'),
        (user_id, 'channel_slack_enabled', 'false'),
        
        # Notification preferences
        (user_id, 'notification_sentinel_enabled', 'true'),
        (user_id, 'notification_report_enabled', 'true'),
        (user_id, 'notification_alert_enabled', 'true'),
    }
    
    logger.info("設定預設系統設定...")
    
    for uid, key, value in settings:
        try:
            # Check if exists
            result = conn.execute(text(
                'SELECT value FROM settings WHERE user_id = :uid AND key = :key'
            ), {'uid': uid, 'key': key}).fetchone()
            
            if result:
                # Update
                conn.execute(text(
                    'UPDATE settings SET value = :value WHERE user_id = :uid AND key = :key'
                ), {'uid': uid, 'key': key, 'value': value})
                logger.info(f'  更新: {key} = {value} (User: {uid[:8]}...)')
            else:
                # Insert
                conn.execute(text(
                    'INSERT INTO settings (user_id, key, value) VALUES (:uid, :key, :value)'
                ), {'uid': uid, 'key': key, 'value': value})
                logger.info(f'  新增: {key} = {value} (User: {uid[:8]}...)')
                
        except Exception as e:
            logger.error(f'  錯誤設定 {key}: {e}')
    
    conn.commit()
    conn.close()
    
    logger.info("\n設定完成！")
    logger.info("\n提示:")
    logger.info("1. 通知頻道預設只啟用 Web (Dashboard)")
    logger.info("2. 如需啟用 LINE/Email/Telegram，請在 Dashboard > Settings 中設定")
    logger.info("3. 排程設定: 每日 09:00 (週一至週五)，每週 09:00 (週六)")

if __name__ == "__main__":
    setup_settings()
