import sqlite3
import hashlib
import json
import os
from datetime import timedelta
from datetime import timedelta, datetime
from sqlalchemy import text
from src.utils.logger import setup_logger
from src.utils.time_utils import get_current_time, format_time
from src.database import get_db_connection

class ResponseCache:
    def __init__(self, db_path="data/cache.db", ttl_hours=24):
        self.db_path = db_path
        self.ttl_hours = ttl_hours
        self.logger = setup_logger("ResponseCache")
        self._init_db()

    def _init_db(self):
        """Initialize the cache database."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = get_db_connection(self.db_path)
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS response_cache (
                    key TEXT PRIMARY KEY,
                    agent_name TEXT,
                    response TEXT,
                    timestamp DATETIME
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
                response, timestamp_str = row
                # Parse timestamp (assuming ISO format from format_time)
                # We need to handle potential timezone differences if DB has old data
                # But for now, let's assume consistent usage of time_utils
                try:
                    timestamp = datetime.fromisoformat(timestamp_str)
                except ValueError:
                    # Fallback for old data or different format
                    timestamp = datetime.now() 

                # Check TTL
                # get_current_time() returns aware datetime, timestamp from DB should be aware too if saved via format_time()
                # If timestamp is naive (old data), we might get error comparing aware vs naive.
                # Let's ensure we compare correctly.
                now = get_current_time()
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=now.tzinfo) # Assume same TZ
                
                if now - timestamp < timedelta(hours=self.ttl_hours):
                    self.logger.info(f"Cache HIT for {agent_name}")
                    return response
                else:
                    self.logger.info(f"Cache EXPIRED for {agent_name}")
            return None
        except Exception as e:
            self.logger.error(f"Cache GET error: {e}")
            return None

    def set(self, agent_name, prompt, response):
        """Save a response to the cache."""
        key = self._generate_key(agent_name, prompt)
        timestamp = format_time() # Use standardized time string
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO response_cache (key, agent_name, response, timestamp)
                VALUES (?, ?, ?, ?)
            """, (key, agent_name, response, timestamp))
            conn.commit()
            conn.close()
            self.logger.info(f"Cache SET for {agent_name}")
        except Exception as e:
            self.logger.error(f"Cache SET error: {e}")

    def clear(self):
        """Clear all cache entries."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM response_cache")
            conn.commit()
            conn.close()
            self.logger.info("Cache cleared.")
        except Exception as e:
            self.logger.error(f"Cache CLEAR error: {e}")
