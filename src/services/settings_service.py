from sqlalchemy import text
import requests
import pandas as pd
from typing import Optional, Any, Dict, List, Tuple
from src.data.database import get_db_connection

class SettingsService:
    """
    Service for managing user and system settings in the database.
    管理資料庫中使用者與系統設定的服務。
    """
    def __init__(self, db_path: str = None, user_id: str = None):
        """
        Initialize the settings service.
        初始化設定服務。
        """
        self.db_path = db_path
        self.user_id = user_id

    def get_all_settings(self) -> Dict[str, str]:
        """
        Retrieves all settings from the database for the current user.
        為目前使用者從資料庫檢索所有設定。
        """
        conn = get_db_connection(self.db_path)
        settings = {}
        try:
            # Check if table exists first (DB agnostic)
            try:
                conn.execute(text("SELECT 1 FROM settings LIMIT 1"))
            except Exception:
                return {}

            target_uid = self.user_id or 'SYSTEM'
            
            # v4.1.7: Strictly use UUID for data retrieval
            if target_uid:
                query = text("SELECT key, value FROM settings WHERE user_id = :uid")
                rows = conn.execute(query, {"uid": target_uid}).fetchall()

            for row in rows:
                key, value = row[0], row[1]
                # v4.1.1: Auto-decode JSON strings if they look like JSON
                # v4.1.1: 自動解碼看起來像 JSON 的字串
                import json
                if isinstance(value, str):
                    # Try to parse as JSON (for dict/list values)
                    if value.startswith(('{', '[')):
                        try:
                            settings[key] = json.loads(value)
                        except:
                            settings[key] = value
                    else:
                        settings[key] = value
                else:
                    settings[key] = value
        except Exception as e:
            print(f"Error loading settings: {e}")
        finally:
            conn.close()
        return settings

    def get_setting(self, key: str, default: Any = None) -> Any:
        """
        Retrieves a single setting value by its key.
        根據鍵值檢索單一設定值。
        """
        all_settings = self.get_all_settings()
        return all_settings.get(key, default)

    def save_setting(self, key: str, value: Any) -> Tuple[bool, str]:
        """
        Saves or updates a single setting in the database.
        在資料庫中儲存或更新單一設定。
        
        v4.1.1: Values are stored as-is without JSON encoding.
        v4.1.1: 值直接儲存，不進行 JSON 編碼。
        """
        conn = get_db_connection(self.db_path)
        try:
            # v4.1.7: Strictly use UUID for data storage
            target_uid = self.user_id

            # v4.1.1: Store value as-is (no JSON encoding)
            # If value is already a string, use it directly
            # If value is a dict/list, convert to JSON string
            import json
            if isinstance(value, (dict, list)):
                store_value = json.dumps(value)
            else:
                store_value = value

            # Cross-DB compatible Upsert: Delete then Insert
            if target_uid:
                conn.execute(text("DELETE FROM settings WHERE key = :key AND user_id = :uid"),
                             {"key": key, "uid": target_uid})
                conn.execute(text("INSERT INTO settings (key, user_id, value) VALUES (:key, :uid, :value)"),
                             {"key": key, "uid": target_uid, "value": store_value})
            else:
                conn.execute(text("DELETE FROM settings WHERE key = :key AND user_id = 'SYSTEM'"),
                             {"key": key})
                conn.execute(text("INSERT INTO settings (key, user_id, value) VALUES (:key, 'SYSTEM', :value)"),
                             {"key": key, "value": store_value})
            conn.commit()
            return True, "Success"
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

    def save_settings_bulk(self, settings_dict: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Saves or updates multiple settings in a single transaction.
        在單一事務中儲存或更新多個設定。
        """
        conn = get_db_connection(self.db_path)
        try:
            for key, value in settings_dict.items():
                if self.user_id:
                    conn.execute(text("DELETE FROM settings WHERE key = :key AND user_id = :uid"),
                                 {"key": key, "uid": self.user_id})
                    conn.execute(text("INSERT INTO settings (key, user_id, value) VALUES (:key, :uid, :value)"),
                                 {"key": key, "uid": self.user_id, "value": str(value)})
                else:
                    conn.execute(text("DELETE FROM settings WHERE key = :key AND user_id = 'SYSTEM'"),
                                 {"key": key})
                    conn.execute(text("INSERT INTO settings (key, user_id, value) VALUES (:key, 'SYSTEM', :value)"),
                                 {"key": key, "value": str(value)})
            conn.commit()
            return True, "Settings saved successfully."
        except Exception as e:
            return False, f"Error saving settings: {e}"
        finally:
            conn.close()

    def fetch_openrouter_models(self) -> List[str]:
        """
        Fetches the list of available models from the OpenRouter API.
        從 OpenRouter API 獲取可用模型列表。
        """
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
    def get_prompt_history(self, user_id: str, limit: int = 50) -> pd.DataFrame:
        """
        Retrieves the history of prompt optimizations for a user.
        檢索使用者的提示詞優化歷史記錄。
        """
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
    def find_user_by_channel_id(self, channel_id: str) -> Optional[str]:
        """
        Find an internal user ID (email) based on a channel-specific ID (e.g., LINE/Telegram).
        根據特定管道 ID（如 LINE/Telegram）尋找內部使用者 ID（電子郵件）。
        """
        conn = get_db_connection(self.db_path)
        try:
            # We look for ANY key that contains 'user_id' or 'chat_id' where value matches
            query = text("""
                SELECT user_id FROM settings 
                WHERE value = :val 
                AND (key LIKE '%user_id' OR key LIKE '%chat_id')
                LIMIT 1
            """)
            result = conn.execute(query, {"val": channel_id}).fetchone()
            return result[0] if result else None
        except Exception as e:
            print(f"Error in find_user_by_channel_id: {e}")
            return None
        finally:
            conn.close()
