from sqlalchemy import text
import requests
from src.data.database import get_db_connection

class SettingsService:
    def __init__(self, db_path=None, user_id=None):
        self.db_path = db_path
        self.user_id = user_id

    def get_all_settings(self):
        """Retrieves all settings from the database as a dictionary."""
        conn = get_db_connection(self.db_path)
        settings = {}
        try:
            # Check if table exists first (DB agnostic)
            try:
                conn.execute(text("SELECT 1 FROM settings LIMIT 1"))
            except Exception:
                return {}

            if self.user_id:
                query = text("SELECT key, value FROM settings WHERE user_id = :uid")
                rows = conn.execute(query, {"uid": self.user_id}).fetchall()
            else:
                # Fallback or admin global settings?
                # For now return empty or global if we had global settings
                # But schema requires PK (key, user_id)
                # Query without filter might duplicate keys?
                query = text("SELECT key, value FROM settings")
                rows = conn.execute(query).fetchall()

            for row in rows:
                settings[row[0]] = row[1]
        except Exception as e:
            print(f"Error loading settings: {e}")
        finally:
            conn.close()
        return settings

    def get_setting(self, key, default=None):
        """Retrieves a single setting value."""
        all_settings = self.get_all_settings()
        return all_settings.get(key, default)

    def save_setting(self, key, value):
        """Saves a single setting."""
        conn = get_db_connection(self.db_path)
        try:
            if self.user_id:
                conn.execute(text("INSERT OR REPLACE INTO settings (key, user_id, value) VALUES (:key, :uid, :value)"),
                             {"key": key, "uid": self.user_id, "value": value})
            else:
                # Fallback
                 conn.execute(text("INSERT OR REPLACE INTO settings (key, value) VALUES (:key, :value)"),
                             {"key": key, "value": value})
            conn.commit()
            return True, "Success"
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

    def save_settings_bulk(self, settings_dict):
        """Saves multiple settings."""
        conn = get_db_connection(self.db_path)
        try:
            for key, value in settings_dict.items():
                if self.user_id:
                    conn.execute(text("INSERT OR REPLACE INTO settings (key, user_id, value) VALUES (:key, :uid, :value)"),
                                 {"key": key, "uid": self.user_id, "value": str(value)})
                else:
                    conn.execute(text("INSERT OR REPLACE INTO settings (key, value) VALUES (:key, :value)"),
                                 {"key": key, "value": str(value)})
            conn.commit()
            return True, "Settings saved successfully."
        except Exception as e:
            return False, f"Error saving settings: {e}"
        finally:
            conn.close()

    def fetch_openrouter_models(self):
        """Fetches available models from OpenRouter API."""
        try:
            response = requests.get("https://openrouter.ai/api/v1/models", timeout=10)
            if response.status_code == 200:
                data = response.json()
                return sorted([model["id"] for model in data.get("data", [])])
            else:
                return []
        except Exception as e:
            print(f"Error fetching OpenRouter models: {e}")
            return []
    def get_prompt_history(self, user_id, limit=50):
        """Retrieves prompt optimization history."""
        import pandas as pd
        conn = get_db_connection(self.db_path)
        try:
            # Check if table exists (optional safety, or assume existence)
            query = text("SELECT timestamp, target_agent, reason, diff_content FROM prompt_history WHERE user_id = :uid ORDER BY timestamp DESC LIMIT :limit")
            df = pd.read_sql(query, conn, params={"uid": user_id, "limit": limit})
            return df
        except Exception as e:
            print(f"Error reading prompt history: {e}")
            return pd.DataFrame()
        finally:
            conn.close()
