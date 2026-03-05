from abc import ABC, abstractmethod
from typing import Any, List, Optional, Tuple
from sqlalchemy import text
from src.data.database import BaseRepository, get_db_engine
from src.data.models import Setting

class ISettingsRepository(ABC):
    """
    Interface for Settings Repository.
    設定儲存庫介面。
    """
    @abstractmethod
    def get(self, user_id: str, key: str, default: Any = None) -> Any:
        """
        Get a specific setting value.
        取得特定設定值。
        """
        pass

    @abstractmethod
    def close_session(self) -> None:
        """
        Close the database session.
        關閉資料庫工作階段。
        """
        pass

    @abstractmethod
    def set(self, user_id: str, key: str, value: Any) -> None:
        """
        Set or update a specific setting value.
        設定或更新特定設定值。
        """
        pass

    @abstractmethod
    def get_all(self, user_id: str) -> List[Tuple[str, Any]]:
        """
        Get all settings for a user.
        取得使用者的所有設定。
        """
        pass

    @abstractmethod
    def get_global(self) -> List[Tuple[str, Any]]:
        """
        Get all global/system settings.
        取得所有全域/系統設定。
        """
        pass

    @abstractmethod
    def get_by_prefix(self, prefix: str) -> List[Tuple[str, Any]]:
        """
        Get settings starting with a specific prefix.
        取得以特定前綴開頭的設定。
        """
        pass

    @abstractmethod
    def find_user_by_channel_id(self, channel_id: str) -> Optional[str]:
        """
        Find an internal user ID based on a channel-specific ID.
        根據管道 ID 尋找內部使用者 ID。
        """
        pass

class AlchemySettingsRepository(BaseRepository, ISettingsRepository):
    """
    Implementation of ISettingsRepository using SQLAlchemy ORM.
    使用 SQLAlchemy ORM 實作的 ISettingsRepository。
    """
    def __init__(self, engine: Any = None):
        """
        Initialize the repository.
        初始化儲存庫。
        """
        BaseRepository.__init__(self, engine or get_db_engine())

    def get(self, user_id: str, key: str, default: Any = None) -> Any:
        """
        Get a specific setting value (ORM).
        取得特定設定值 (ORM)。
        """
        try:
            # Strictly use user_id as UUID per v4.1.7 requirements
            setting = self.session.query(Setting).filter_by(user_id=user_id, key=key).first()
            return setting.value if setting else default
        except Exception as e:
            # Fallback for missing table during tests or initial setup
            return default
        finally:
            self.close_session()

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Alias for get() to support legacy calls with system user."""
        return self.get("system", key, default)

    def save_setting(self, key: str, value: Any) -> Tuple[bool, str]:
        """Alias for set() to support legacy calls with system user."""
        try:
            self.set("system", key, value)
            return True, "Success"
        except Exception as e:
            return False, str(e)

    def set(self, user_id: str, key: str, value: Any) -> None:
        """
        Set or update a specific setting value (Upsert via ORM).
        設定或更新特定設定值 (透過 ORM Upsert)。
        """
        session = self.session
        try:
            # Ensure value is JSON-serializable
            # SQLAlchemy JSON column will handle serialization, but we need to ensure the value is valid
            import json
            if isinstance(value, bool):
                # Standardize boolean storage
                store_value = value
            elif isinstance(value, str):
                # For string values, store as-is (SQLAlchemy will wrap in JSON)
                store_value = value
            elif isinstance(value, (dict, list, int, float)):
                # For basic and complex types, let SQLAlchemy handle it
                store_value = value
            else:
                # For other types, convert to string
                store_value = str(value)
            
            setting = session.query(Setting).filter_by(user_id=user_id, key=key).first()
            if setting:
                setting.value = store_value
            else:
                setting = Setting(user_id=user_id, key=key, value=store_value)
                session.add(setting)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to set setting {key} for user {user_id}: {e}")
            raise
        finally:
            self.close_session()

    def get_all(self, user_id: str) -> List[Tuple[str, Any]]:
        """
        Get all settings for a user (ORM).
        取得該使用者所有設定 (ORM)。
        """
        try:
            rows = self.session.query(Setting).filter_by(user_id=user_id).all()
            return [(r.key, r.value) for r in rows]
        finally:
            self.close_session()

    def get_global(self) -> List[Tuple[str, Any]]:
        """
        Get all global/system settings (ORM).
        取得全域設定 (ORM)。
        """
        try:
            # Logic: user_id is NULL or 'system'
            rows = self.session.query(Setting).filter(
                (Setting.user_id == None) | (Setting.user_id == 'system')
            ).all()
            return [(r.key, r.value) for r in rows]
        finally:
            self.close_session()

    def get_by_prefix(self, prefix: str) -> List[Tuple[str, Any]]:
        """
        Get settings starting with a specific prefix (ORM).
        依前綴取得設定 (ORM)。
        """
        try:
            rows = self.session.query(Setting).filter(Setting.key.like(f"{prefix}%")).all()
            return [(r.key, r.value) for r in rows]
        finally:
            self.close_session()

    def find_user_by_channel_id(self, channel_id: str) -> Optional[str]:
        """
        Find an internal user ID (email) based on a channel-specific ID (e.g., LINE/Telegram).
        根據特定管道 ID（如 LINE/Telegram）尋找內部使用者 ID（電子郵件）。
        """
        try:
            # We look for ANY key that contains 'user_id' or 'chat_id' where value matches
            from sqlalchemy import text
            query = text("""
                SELECT user_id FROM settings 
                WHERE value = :val 
                AND (key LIKE '%user_id' OR key LIKE '%chat_id')
                LIMIT 1
            """)
            result = self.session.execute(query, {"val": channel_id}).fetchone()
            return result[0] if result else None
        except Exception as e:
            return None
        finally:
            self.close_session()

# Legacy aliases removed in v4.1.7
# @deprecated: Use AlchemySettingsRepository
