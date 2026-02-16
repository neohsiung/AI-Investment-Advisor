import sqlite3
import datetime
import uuid
import logging
from src.data.database import get_db_connection

logger = logging.getLogger(__name__)

class VerificationRepository:
    def __init__(self, db_path="data/portfolio.db"):
        self.db_path = db_path
        self._init_table()

    def _init_table(self):
        query = """
        CREATE TABLE IF NOT EXISTS channel_verifications (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            channel TEXT,
            code TEXT,
            status TEXT DEFAULT 'pending',
            error_message TEXT,
            expires_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        try:
            with get_db_connection(self.db_path) as conn:
                conn.execute(query)
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to init channel_verifications table: {e}")

    def create_verification(self, user_id: str, channel: str, code: str, expires_at: datetime.datetime):
        verification_id = str(uuid.uuid4())
        query = """
        INSERT INTO channel_verifications (id, user_id, channel, code, status, expires_at)
        VALUES (?, ?, ?, ?, 'pending', ?)
        """
        try:
            with get_db_connection(self.db_path) as conn:
                conn.execute(query, (verification_id, user_id, channel, code, expires_at))
                conn.commit()
            return verification_id
        except Exception as e:
            logger.error(f"Failed to create verification: {e}")
            return None

    def get_pending_verification(self, user_id: str, channel: str):
        query = """
        SELECT * FROM channel_verifications 
        WHERE user_id = ? AND channel = ? AND status = 'pending' AND expires_at > CURRENT_TIMESTAMP
        ORDER BY created_at DESC LIMIT 1
        """
        try:
            with get_db_connection(self.db_path) as conn:
                row = conn.execute(query, (user_id, channel)).fetchone()
                return self._row_to_dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get pending verification: {e}")
            return None

    def get_any_pending_verification(self, user_id: str):
        query = """
        SELECT * FROM channel_verifications 
        WHERE user_id = ? AND status = 'pending' AND expires_at > CURRENT_TIMESTAMP
        ORDER BY created_at DESC LIMIT 1
        """
        try:
            with get_db_connection(self.db_path) as conn:
                row = conn.execute(query, (user_id,)).fetchone()
                return self._row_to_dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get any pending verification: {e}")
            return None

    def update_status(self, verification_id: str, status: str, error_message: str = None):
        query = """
        UPDATE channel_verifications 
        SET status = ?, error_message = ?
        WHERE id = ?
        """
        try:
            with get_db_connection(self.db_path) as conn:
                conn.execute(query, (status, error_message, verification_id))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to update verification status: {e}")
            return False
            
    def get_verification_by_id(self, verification_id: str):
        query = "SELECT * FROM channel_verifications WHERE id = ?"
        try:
            with get_db_connection(self.db_path) as conn:
                row = conn.execute(query, (verification_id,)).fetchone()
                return self._row_to_dict(row) if row else None
        except Exception as e:
             logger.error(f"Failed to get verification by id: {e}")
             return None

    def _row_to_dict(self, row):
        return {
            "id": row[0],
            "user_id": row[1],
            "channel": row[2],
            "code": row[3],
            "status": row[4],
            "error_message": row[5],
            "expires_at": row[6],
            "created_at": row[7]
        }
