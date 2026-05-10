"""
PAD 通知系統 - 用戶設置驅動 (Settings-Driven Notification System)

設計原則:
1. 通知渠道由用戶設置決定 (DB settings)
2. 報告項目由用戶設置決定 (DB settings)
3. UI 提供配置介面供用戶選擇
4. 無硬編碼通知規則 — 完全數據驅動
"""

from typing import List, Dict, Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class NotificationChannel(str, Enum):
    """支援的通知渠道"""
    EMAIL = "email"
    WEB = "web"
    TELEGRAM = "telegram"
    SMS = "sms"
    WEBHOOK = "webhook"


class ReportType(str, Enum):
    """支援的報告類型"""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    PERFORMANCE = "performance"
    RISK = "risk"
    PORTFOLIO = "portfolio"


class NotificationSettingsManager:
    """
    管理用戶通知和報告偏好設置
    
    DB Settings Keys:
    - notification_channels: 逗號分隔的渠道列表 (e.g., "email,telegram,web")
    - enabled_report_types: 逗號分隔的報告類型 (e.g., "daily,weekly,portfolio")
    - report_schedule_daily: 每日報告時間 (e.g., "09:00 UTC")
    - report_schedule_weekly: 每週報告日期 (e.g., "Monday 09:00 UTC")
    - notification_email: 通知郵箱 (if different from account email)
    - telegram_chat_id: Telegram 聊天 ID (optional, for direct push)
    """
    
    # 預設設置
    DEFAULT_CHANNELS = [NotificationChannel.EMAIL.value]
    DEFAULT_REPORT_TYPES = [ReportType.DAILY.value]
    DEFAULT_DAILY_SCHEDULE = "09:00 UTC"
    DEFAULT_WEEKLY_SCHEDULE = "Monday 09:00 UTC"
    
    def __init__(self, settings_repo, user_id: str):
        """
        初始化通知設置管理器
        
        Args:
            settings_repo: 設置存儲庫 (通常是 SettingsRepository)
            user_id: 用戶 ID
        """
        self.settings_repo = settings_repo
        self.user_id = user_id
        self.logger = logging.getLogger(__name__)
    
    # ============================================================================
    # 通知渠道管理
    # ============================================================================
    
    def get_notification_channels(self) -> List[str]:
        """
        獲取用戶啟用的通知渠道
        
        Returns:
            已啟用的渠道列表 (e.g., ["email", "telegram", "web"])
        """
        try:
            channels_str = self.settings_repo.get(
                self.user_id,
                "notification_channels",
                default=",".join(self.DEFAULT_CHANNELS)
            )
            
            # 解析逗號分隔的渠道列表
            channels = [ch.strip() for ch in channels_str.split(",") if ch.strip()]
            
            # 驗證渠道有效性
            valid_channels = [
                ch for ch in channels 
                if ch in [e.value for e in NotificationChannel]
            ]
            
            if not valid_channels:
                self.logger.warning(
                    f"User {self.user_id} has no valid notification channels. "
                    f"Defaulting to {self.DEFAULT_CHANNELS}"
                )
                return self.DEFAULT_CHANNELS
            
            self.logger.info(
                f"User {self.user_id} notification channels: {valid_channels}"
            )
            return valid_channels
            
        except Exception as e:
            self.logger.error(f"Failed to fetch notification channels: {e}")
            return self.DEFAULT_CHANNELS
    
    def set_notification_channels(self, channels: List[str]) -> bool:
        """
        設置用戶啟用的通知渠道
        
        Args:
            channels: 要啟用的渠道列表
        
        Returns:
            設置是否成功
        """
        try:
            # 驗證渠道有效性
            valid_channels = [
                ch for ch in channels 
                if ch in [e.value for e in NotificationChannel]
            ]
            
            if not valid_channels:
                self.logger.warning(
                    f"No valid channels provided for user {self.user_id}. "
                    f"Using default: {self.DEFAULT_CHANNELS}"
                )
                valid_channels = self.DEFAULT_CHANNELS
            
            channels_str = ",".join(valid_channels)
            self.settings_repo.set(
                self.user_id,
                "notification_channels",
                channels_str
            )
            
            self.logger.info(
                f"Updated notification channels for {self.user_id}: {channels_str}"
            )
            return True
            
        except Exception as e:
            self.logger.error(
                f"Failed to set notification channels for {self.user_id}: {e}"
            )
            return False
    
    # ============================================================================
    # 報告類型管理
    # ============================================================================
    
    def get_enabled_report_types(self) -> List[str]:
        """
        獲取用戶啟用的報告類型
        
        Returns:
            已啟用的報告類型 (e.g., ["daily", "weekly", "portfolio"])
        """
        try:
            reports_str = self.settings_repo.get(
                self.user_id,
                "enabled_report_types",
                default=",".join(self.DEFAULT_REPORT_TYPES)
            )
            
            # 解析逗號分隔的報告類型
            reports = [r.strip() for r in reports_str.split(",") if r.strip()]
            
            # 驗證報告類型有效性
            valid_reports = [
                r for r in reports 
                if r in [e.value for e in ReportType]
            ]
            
            if not valid_reports:
                self.logger.warning(
                    f"User {self.user_id} has no valid report types. "
                    f"Defaulting to {self.DEFAULT_REPORT_TYPES}"
                )
                return self.DEFAULT_REPORT_TYPES
            
            self.logger.info(
                f"User {self.user_id} enabled report types: {valid_reports}"
            )
            return valid_reports
            
        except Exception as e:
            self.logger.error(f"Failed to fetch enabled report types: {e}")
            return self.DEFAULT_REPORT_TYPES
    
    def set_enabled_report_types(self, report_types: List[str]) -> bool:
        """
        設置用戶啟用的報告類型
        
        Args:
            report_types: 要啟用的報告類型列表
        
        Returns:
            設置是否成功
        """
        try:
            # 驗證報告類型有效性
            valid_reports = [
                r for r in report_types 
                if r in [e.value for e in ReportType]
            ]
            
            if not valid_reports:
                self.logger.warning(
                    f"No valid report types provided for user {self.user_id}. "
                    f"Using default: {self.DEFAULT_REPORT_TYPES}"
                )
                valid_reports = self.DEFAULT_REPORT_TYPES
            
            reports_str = ",".join(valid_reports)
            self.settings_repo.set(
                self.user_id,
                "enabled_report_types",
                reports_str
            )
            
            self.logger.info(
                f"Updated report types for {self.user_id}: {reports_str}"
            )
            return True
            
        except Exception as e:
            self.logger.error(
                f"Failed to set report types for {self.user_id}: {e}"
            )
            return False
    
    # ============================================================================
    # 報告排程管理
    # ============================================================================
    
    def get_report_schedule(self, report_type: str) -> str:
        """
        獲取特定報告類型的排程時間
        
        Args:
            report_type: 報告類型 (e.g., "daily", "weekly")
        
        Returns:
            排程時間 (e.g., "09:00 UTC", "Monday 09:00 UTC")
        """
        try:
            key = f"report_schedule_{report_type}"
            default = (
                self.DEFAULT_DAILY_SCHEDULE 
                if report_type == "daily" 
                else self.DEFAULT_WEEKLY_SCHEDULE
            )
            
            schedule = self.settings_repo.get(
                self.user_id,
                key,
                default=default
            )
            
            self.logger.info(
                f"User {self.user_id} {report_type} report schedule: {schedule}"
            )
            return schedule
            
        except Exception as e:
            self.logger.error(
                f"Failed to fetch {report_type} schedule for {self.user_id}: {e}"
            )
            return (
                self.DEFAULT_DAILY_SCHEDULE 
                if report_type == "daily" 
                else self.DEFAULT_WEEKLY_SCHEDULE
            )
    
    def set_report_schedule(self, report_type: str, schedule: str) -> bool:
        """
        設置特定報告類型的排程時間
        
        Args:
            report_type: 報告類型
            schedule: 排程時間
        
        Returns:
            設置是否成功
        """
        try:
            key = f"report_schedule_{report_type}"
            self.settings_repo.set(
                self.user_id,
                key,
                schedule
            )
            
            self.logger.info(
                f"Updated {report_type} schedule for {self.user_id}: {schedule}"
            )
            return True
            
        except Exception as e:
            self.logger.error(
                f"Failed to set {report_type} schedule for {self.user_id}: {e}"
            )
            return False
    
    # ============================================================================
    # 用戶偏好查詢
    # ============================================================================
    
    def get_notification_preferences(self) -> Dict:
        """
        獲取用戶的完整通知偏好設置
        
        Returns:
            包含所有設置的字典
        """
        return {
            "notification_channels": self.get_notification_channels(),
            "enabled_report_types": self.get_enabled_report_types(),
            "daily_schedule": self.get_report_schedule("daily"),
            "weekly_schedule": self.get_report_schedule("weekly"),
            "monthly_schedule": self.get_report_schedule("monthly"),
        }
    
    def should_send_report(self, report_type: str) -> bool:
        """
        檢查是否應該為該報告類型發送通知
        
        Args:
            report_type: 報告類型
        
        Returns:
            是否應該發送
        """
        enabled_types = self.get_enabled_report_types()
        return report_type in enabled_types
    
    def get_active_notification_channels(self) -> List[str]:
        """
        獲取已啟用的通知渠道列表
        
        Returns:
            活躍渠道列表
        """
        channels = self.get_notification_channels()
        
        # 過濾掉未配置必要信息的渠道
        active_channels = []
        for channel in channels:
            if channel == NotificationChannel.EMAIL.value:
                # Email 通常總是可用的
                active_channels.append(channel)
            elif channel == NotificationChannel.TELEGRAM.value:
                # 檢查是否配置了 Telegram Chat ID
                # v10.0: Prioritize channel_telegram_chat_id (consistent with UI)
                telegram_id = self.settings_repo.get(
                    self.user_id,
                    "channel_telegram_chat_id"
                )
                if not telegram_id:
                     telegram_id = self.settings_repo.get(
                        self.user_id,
                        "telegram_chat_id"
                    )
                
                if telegram_id:
                    active_channels.append(channel)
                else:
                    self.logger.warning(
                        f"Telegram channel selected but no channel_telegram_chat_id "
                        f"configured for user {self.user_id}"
                    )
            elif channel == NotificationChannel.WEB.value:
                active_channels.append(channel)
            elif channel == NotificationChannel.SMS.value:
                # 檢查是否配置了電話號碼
                phone = self.settings_repo.get(
                    self.user_id,
                    "notification_phone"
                )
                if phone:
                    active_channels.append(channel)
            elif channel == NotificationChannel.WEBHOOK.value:
                # 檢查是否配置了 Webhook URL
                webhook_url = self.settings_repo.get(
                    self.user_id,
                    "notification_webhook_url"
                )
                if webhook_url:
                    active_channels.append(channel)
        
        return active_channels
