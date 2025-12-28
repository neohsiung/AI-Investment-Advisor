from abc import ABC, abstractmethod
from sqlalchemy import text
from src.data.database import get_db_connection

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

    @abstractmethod
    def get_global(self):
        pass

    @abstractmethod
    def get_by_prefix(self, prefix: str):
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

    def get_global(self):
        """
        取得全域設定 (假設 user_id IS NULL 或特定 admin user)
        這裡假設全域設定的 user_id 為 NULL 或 'system'
        """
        with get_db_connection() as conn:
            # Try NULL or 'system'
            query = text("SELECT key, value FROM settings WHERE user_id IS NULL OR user_id = 'system'")
            return conn.execute(query).fetchall()

    def get_by_prefix(self, prefix: str):
        with get_db_connection() as conn:
            query = text("SELECT key, value FROM settings WHERE key LIKE :prefix")
            return conn.execute(query, {"prefix": f"{prefix}%"}).fetchall()
