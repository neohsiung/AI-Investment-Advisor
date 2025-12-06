from sqlalchemy import text
import requests
from src.database import get_db_connection

class SettingsService:
    def __init__(self, db_path=None):
        self.db_path = db_path

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

            rows = conn.execute(text("SELECT key, value FROM settings")).fetchall()
            for row in rows:
                settings[row[0]] = row[1]
        except Exception as e:
            print(f"Error loading settings: {e}")
        finally:
            conn.close()
        return settings

    def save_setting(self, key, value):
        """Saves a single setting."""
        conn = get_db_connection(self.db_path)
        try:
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
