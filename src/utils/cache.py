import sqlite3
import hashlib
import json
import os
from datetime import timedelta
from datetime import timedelta, datetime
from sqlalchemy import text
from src.utils.logger import setup_logger
from src.utils.time_utils import get_current_time, format_time
from src.data.database import get_db_connection

class ResponseCache:
    def __init__(self, db_path=None, ttl_hours=24):
        self.db_path = db_path
        self.ttl_hours = ttl_hours
        self.logger = setup_logger("ResponseCache")
        self._init_db()

    def _init_db(self):
        """Initialize the cache database."""
        conn = get_db_connection(self.db_path)
        is_sqlite = 'sqlite' in str(conn.engine.url)
        timestamp_type = "DATETIME" if is_sqlite else "TIMESTAMP"
        try:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS response_cache (
                    key TEXT PRIMARY KEY,
                    agent_name TEXT,
                    response TEXT,
                    timestamp {timestamp_type}
                )
            """))
            conn.commit()
        except Exception as e:
            self.logger.error(f"Failed to init cache DB: {e}")
        finally:
            conn.close()

    def _generate_key(self, agent_name, prompt):
        """Generate a unique key based on agent name and prompt content."""
        content = f"{agent_name}:{prompt}"
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def get(self, agent_name, prompt):
        """Retrieve a cached response if valid."""
        key = self._generate_key(agent_name, prompt)
        conn = get_db_connection(self.db_path)
        try:
            row = conn.execute(text("SELECT response, timestamp FROM response_cache WHERE key = :key"), {"key": key}).fetchone()

            if row:
                response, db_timestamp = row
                
                # SQLAlchemy might return datetime object or string
                if isinstance(db_timestamp, str):
                    try:
                        timestamp = datetime.fromisoformat(db_timestamp)
                    except ValueError:
                        timestamp = datetime.now()
                else:
                    timestamp = db_timestamp

                # Check TTL
                now = datetime.now() if timestamp.tzinfo is None else get_current_time()
                if timestamp.tzinfo is None and now.tzinfo is not None:
                    timestamp = timestamp.replace(tzinfo=now.tzinfo)

                if now - timestamp < timedelta(hours=self.ttl_hours):
                    self.logger.info(f"Cache HIT for {agent_name}")
                    return response
                else:
                    self.logger.info(f"Cache EXPIRED for {agent_name}")
            return None
        except Exception as e:
            self.logger.error(f"Cache GET error: {e}")
            return None
        finally:
            conn.close()

    def set(self, agent_name, prompt, response):
        """Save a response to the cache."""
        key = self._generate_key(agent_name, prompt)
        conn = get_db_connection(self.db_path)
        is_sqlite = 'sqlite' in str(conn.engine.url)
        timestamp = format_time() if is_sqlite else datetime.now()
        
        try:
            # Use SQLAlchemy for consistent DB handling (Postgres/SQLite)
            query = text("""
                INSERT INTO response_cache (key, agent_name, response, timestamp)
                VALUES (:key, :agent_name, :response, :timestamp)
                ON CONFLICT(key) DO UPDATE SET 
                    response = excluded.response, 
                    timestamp = excluded.timestamp
            """)
            conn.execute(query, {
                "key": key, 
                "agent_name": agent_name, 
                "response": response, 
                "timestamp": timestamp
            })
            conn.commit()
            self.logger.info(f"Cache SET for {agent_name}")
        except Exception as e:
            self.logger.error(f"Cache SET error: {e}")
        finally:
            conn.close()

    def clear(self):
        """Clear all cache entries."""
        conn = get_db_connection(self.db_path)
        try:
            conn.execute(text("DELETE FROM response_cache"))
            conn.commit()
            self.logger.info("Cache cleared.")
        except Exception as e:
            self.logger.error(f"Cache CLEAR error: {e}")
        finally:
            conn.close()
