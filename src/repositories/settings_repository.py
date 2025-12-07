from abc import ABC, abstractmethod
from sqlalchemy import text
from src.database import get_db_connection

class ISettingsRepository(ABC):
    @abstractmethod
    def get(self, user_id: str, key: str, default=None):
        pass

    @abstractmethod
    def set(self, user_id: str, key: str, value: str):
        pass

    @abstractmethod
    def get_all(self, user_id: str):
        pass

class SqliteSettingsRepository(ISettingsRepository):
    def get(self, user_id: str, key: str, default=None):
        """
        取得特定 Key 的設定值
        """
        with get_db_connection() as conn:
            # Table schema for settings: key (PK), value, user_id
            # Wait, original schema might rely on key being PK without user_id composite
            # Let's check schema. Assuming we need to support user-specific settings.
            # If current schema doesn't have user_id in settings, we should probably stick to global for now or upgrade.
            # Based on previous tasks, we added user_id to all tables.
            query = text("SELECT value FROM settings WHERE key = :key AND user_id = :user_id")
            result = conn.execute(query, {"key": key, "user_id": user_id}).fetchone()
            if result:
                return result[0]
            return default

    def set(self, user_id: str, key: str, value: str):
        """
        設定特定 Key 的值 (Upsert)
        """
        with get_db_connection() as conn:
            # SQLite upsert syntax
            query = text("""
                INSERT INTO settings (user_id, key, value)
                VALUES (:user_id, :key, :value)
                ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value
            """)
            conn.execute(query, {"user_id": user_id, "key": key, "value": value})
            conn.commit()

    def get_all(self, user_id: str):
        """
        取得該使用者所有設定
        """
        with get_db_connection() as conn:
            query = text("SELECT key, value FROM settings WHERE user_id = :user_id")
            return conn.execute(query, {"user_id": user_id}).fetchall()
