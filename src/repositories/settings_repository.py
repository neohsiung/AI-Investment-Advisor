from abc import ABC, abstractmethod
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
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
    def get_by_prefix(self, prefix: str, user_id: Optional[str] = None) -> List[Tuple[str, Any]]:
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
        
    @abstractmethod
    def get_channel_ids_for_user(self, user_id: str) -> Dict[str, str]:
        """
        Get all channel IDs mapped to an internal user.
        回傳所有綁定到該內部使用者的通道 ID (例如: {"telegram": "123", "line": "U456"}).
        """

    @abstractmethod
    def find_user_by_webhook_secret(self, secret: str) -> Optional[str]:
        """
        Find an internal user ID based on a webhook secret / API key.
        根據 Webhook 密鑰 / API Key 尋找內部使用者 ID。
        """
        pass

    @abstractmethod
    def delete(self, user_id: str, key: str) -> bool:
        """
        Delete a specific setting.
        刪除特定設定。
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

    def _resolve_user(self, user_id: str) -> str:
        """
        v4.3.0: Enforce mandatory user isolation.
        No more 'system' fallback. All settings must belong to a real user UUID.
        """
        if user_id in ('system', 'SYSTEM', 'None', '', None):
             # 🚨 CRITICAL: In a strictly isolated system, passing 'system' is an error.
             # We throw an error to force developer to fix the caller logic.
             raise ValueError(f"Global 'system' user is retired. Settings must be assigned to a real User UUID. Received: {user_id}")
        
        return user_id

    def get(self, user_id: str, key: str, default: Any = None) -> Any:
        """
        Get a specific setting value (ORM).
        """
    def get(self, user_id: str, key: str, default: Any = None) -> Any:
        """
        Get a specific setting value (ORM).
        """
        resolved_uid = self._resolve_user(user_id)
        
        try:
            setting = self.session.query(Setting).filter_by(user_id=resolved_uid, key=key).first()
            return setting.value if setting else default
        except Exception:
            return default
        finally:
            self.close_session()

    def save_setting(self, key: str, value: Any, user_id: str) -> Tuple[bool, str]:
        """Set or update a specific setting value (Alias for set). user_id is mandatory."""
        try:
            # v4.3.0: user_id is now mandatory. No defaults.
            self.set(user_id, key, value)
            return True, "Success"
        except Exception as e:
            return False, str(e)

    def set(self, user_id: str, key: str, value: Any) -> None:
        """
        Set or update a specific setting value (Upsert via ORM).
        """
        resolved_uid = self._resolve_user(user_id)
        
        session = self.session
        try:
            # Ensure value is JSON-serializable
            import json
            if isinstance(value, bool):
                store_value = value
            elif isinstance(value, str):
                store_value = value
            elif isinstance(value, (dict, list, int, float)):
                store_value = value
            else:
                store_value = str(value)
            
            setting = session.query(Setting).filter_by(user_id=resolved_uid, key=key).first()
            if setting:
                setting.value = store_value
            else:
                setting = Setting(user_id=resolved_uid, key=key, value=store_value)
                session.add(setting)
            session.commit()
        except Exception as e:
            session.rollback()
            raise
        finally:
            self.close_session()

    def delete(self, user_id: str, key: str) -> bool:
        """
        Delete a specific setting for a user.
        """
        resolved_uid = self._resolve_user(user_id)
        
        session = self.session
        try:
            setting = session.query(Setting).filter_by(user_id=resolved_uid, key=key).first()
            if setting:
                session.delete(setting)
                session.commit()
                return True
            return False
        except Exception as e:
            session.rollback()
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

    def get_by_prefix(self, prefix: str, user_id: Optional[str] = None) -> List[Tuple[str, Any]]:
        """
        Get settings starting with a specific prefix (ORM).
        依前綴取得設定 (ORM)。
        """
        if user_id:
            user_id = self._resolve_user(user_id)
            
        try:
            query = self.session.query(Setting).filter(Setting.key.like(f"{prefix}%"))
            if user_id:
                query = query.filter(Setting.user_id == user_id)
            rows = query.all()
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

    def get_channel_ids_for_user(self, user_id: str) -> Dict[str, str]:
        """
        Get all channel IDs (e.g., Telegram, LINE) mapped to an internal user.
        """
        resolved_uid = self._resolve_user(user_id)
        channel_ids = {}
        try:
            from sqlalchemy import text
            query = text("""
                SELECT key, value FROM settings 
                WHERE user_id = :uid 
                AND (key LIKE '%user_id' OR key LIKE '%chat_id')
                AND value IS NOT NULL AND value != ''
            """)
            result = self.session.execute(query, {"uid": resolved_uid}).fetchall()
            
            for key, val in result:
                # Convert raw setting keys to a clean channel identifier
                val_str = str(val).strip('"').strip("'")
                if "telegram" in key.lower():
                    channel_ids["telegram"] = val_str
                elif "line" in key.lower():
                    channel_ids["line"] = val_str
                else:
                    channel_ids[key] = val_str
                    
            return channel_ids
        except Exception as e:
            return {}
        finally:
            self.close_session()

    def find_user_by_webhook_secret(self, secret: str) -> Optional[str]:
        """
        Find an internal user ID (email/UUID) based on a webhook secret / API key.
        """
        try:
            # We look for a specific key 'webhook_api_key'
            query = text("""
                SELECT user_id FROM settings 
                WHERE TRIM(BOTH '"' FROM value) = :val 
                AND key = 'webhook_api_key'
                LIMIT 1
            """)
            result = self.session.execute(query, {"val": secret}).fetchone()
            return result[0] if result else None
        except Exception:
            return None
        finally:
            self.close_session()

# Legacy aliases removed in v4.1.7
# @deprecated: Use AlchemySettingsRepository
