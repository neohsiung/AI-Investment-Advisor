import json
import os
import secrets as _secrets
from datetime import datetime
from typing import List, Dict, Tuple, Any, Optional, Callable, Sequence
from abc import ABC, abstractmethod
from cryptography.fernet import Fernet
from sqlalchemy import text
from src.data.database import BaseRepository, get_db_engine
from src.data.models import Setting
from src.utils.logger import setup_logger

_logger = setup_logger("SettingsRepository")

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
    def set_many(self, user_id: str, settings: Dict[str, Any]) -> None:
        """
        Atomically set multiple settings — all succeed or none are written.
        原子性寫入多筆設定：全部成功或全部不寫入。
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
        Initialize the repository with optional encryption support.
        """
        BaseRepository.__init__(self, engine or get_db_engine())
        
        # v11.1: Initialize encryption cipher if secret key exists
        self.secret_key = os.getenv("APP_SECRET_KEY")
        self.cipher = Fernet(self.secret_key.encode()) if self.secret_key else None
        self.sensitive_patterns = ["api_key", "token", "secret", "password", "private_key", "_pass", "_key"]

    def _should_encrypt(self, key: str) -> bool:
        """Determines if a key contains sensitive information that should be encrypted."""
        return any(pattern in key.lower() for pattern in self.sensitive_patterns)

    def _encrypt(self, value: Any) -> str:
        """Encrypts the value if the cipher is available. Idempotent — won't double-encrypt."""
        if not self.cipher or value is None:
            return value
        str_val = json.dumps(value) if not isinstance(value, str) else value
        if str_val.startswith("ENC:"):
            return str_val
        encrypted_bytes = self.cipher.encrypt(str_val.encode())
        return f"ENC:{encrypted_bytes.decode()}"

    def _decrypt(self, value: Any) -> Any:
        """Decrypts the value if it looks encrypted and the cipher is available."""
        if not isinstance(value, str):
            return value
            
        # v4.3.1: Strip potential quotes or whitespace from DB/JSON storage
        raw_val = value.strip().strip('"').strip("'")
        
        if not raw_val.startswith("ENC:"):
            return value
            
        if not self.cipher:
            _logger.warning(
                "Value is encrypted (ENC: prefix) but APP_SECRET_KEY is not set. "
                "Set APP_SECRET_KEY in .env to decrypt stored credentials."
            )
            return value
            
        try:
            # Strip 'ENC:' prefix and decrypt
            encrypted_data = raw_val[4:]
            decrypted_bytes = self.cipher.decrypt(encrypted_data.encode())
            decrypted_str = decrypted_bytes.decode('utf-8')
            try:
                return json.loads(decrypted_str)
            except json.JSONDecodeError:
                return decrypted_str
        except Exception as e:
            _logger.warning(f'Exception in settings_repository.py: {e}', exc_info=True)
            _logger.error(
                "Decryption failed — APP_SECRET_KEY may have rotated. "
                "Returning raw encrypted value; credential will appear invalid.",
                exc_info=True,
            )
            return value

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
        Get a specific setting value (ORM) with transparent decryption.
        """
        resolved_uid = self._resolve_user(user_id)
        
        try:
            setting = self.session.query(Setting).filter_by(user_id=resolved_uid, key=key).first()
            if not setting:
                return default
            raw_value = setting.value
            if self._should_encrypt(key):
                return self._decrypt(raw_value)
            return raw_value
        except Exception as e:
            _logger.warning(f'Exception in settings_repository.py: {e}', exc_info=True)
            _logger.exception(f"get() failed for user={resolved_uid!r} key={key!r}")
            return default
        finally:
            self.close_session()

    def get_many_with_meta(
        self, user_id: str, keys: Sequence[str]
    ) -> Dict[str, Tuple[Any, Optional[datetime]]]:
        """
        Fetch several settings in one query, each paired with its row's
        `updated_at`. Absent keys come back as `(None, None)`.

        Exists so callers can build a change token out of row timestamps
        instead of out of the values themselves — see BrokerFactory, which
        needs to notice a credential rotation without ever hashing the
        credential. Also strictly cheaper than the N separate `get()` calls it
        replaces there.

        一次查詢取回多個設定值與其 updated_at；不存在的 key 回 (None, None)。
        讓呼叫端能用「列的時間戳」而非「值本身」組出變更權杖（見 BrokerFactory：
        要偵測憑證輪換，但絕不雜湊憑證），順帶把 N 次 get() 併成一次查詢。
        """
        resolved_uid = self._resolve_user(user_id)
        result: Dict[str, Tuple[Any, Optional[datetime]]] = {k: (None, None) for k in keys}
        if not keys:
            return result
        try:
            rows = (
                self.session.query(Setting)
                .filter(Setting.user_id == resolved_uid, Setting.key.in_(list(keys)))
                .all()
            )
            for row in rows:
                value = self._decrypt(row.value) if self._should_encrypt(row.key) else row.value
                result[row.key] = (value, row.updated_at)
            return result
        except Exception as e:
            _logger.warning(f'Exception in settings_repository.py: {e}', exc_info=True)
            _logger.exception(f"get_many_with_meta() failed for user={resolved_uid!r}")
            return result
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
        Set or update a specific setting value (Upsert via ORM) with transparent encryption.
        """
        resolved_uid = self._resolve_user(user_id)
        
        session = self.session
        try:
            # Ensure value is JSON-serializable if not basic type
            if isinstance(value, (dict, list)):
                store_value = value # SQLAlchemy handles JSON for us if the model type is right, but here it's likely a generic 'JSON' column or string
            else:
                store_value = value
            
            # v11.1: Transparently encrypt sensitive data
            if self._should_encrypt(key):
                store_value = self._encrypt(value)
            
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

    def set_many(self, user_id: str, settings: Dict[str, Any]) -> None:
        """
        Atomic all-or-nothing bulk upsert: one transaction, one commit.

        Callers write related keys together — notably the eToro credential PAIR
        (`etoro_api_key` + `etoro_user_key`) and the `ai_trading_enabled` kill
        switch. Looping over `set()` committed per key, so a mid-loop failure
        left a half-applied state; for a credential pair that means one key
        rotated and the other not, which is exactly the shape of the
        2026-08-02 outage. Here nothing lands unless everything lands.

        Deliberately dialect-agnostic ORM (no `on_conflict_do_update`) —
        repository tests run against in-memory sqlite.
        原子性批次寫入：單一 transaction、單一 commit。
        憑證是成對的，逐 key commit 會留下「一把換了一把沒換」的半套狀態。
        """
        if not settings:
            return

        resolved_uid = self._resolve_user(user_id)
        session = self.session
        try:
            keys = list(settings.keys())
            existing = {
                row.key: row
                for row in session.query(Setting)
                .filter(Setting.user_id == resolved_uid, Setting.key.in_(keys))
                .all()
            }

            for key, value in settings.items():
                store_value = self._encrypt(value) if self._should_encrypt(key) else value
                row = existing.get(key)
                if row is not None:
                    row.value = store_value
                else:
                    session.add(Setting(user_id=resolved_uid, key=key, value=store_value))

            session.commit()
        except Exception:
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
            return [
                (r.key, self._decrypt(r.value) if self._should_encrypt(r.key) else r.value)
                for r in rows
            ]
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
        Find a user by webhook API key using application-side decrypt + constant-time compare.
        Raw SQL value comparison is avoided so this works regardless of encryption state.
        """
        try:
            rows = self.session.execute(
                text("SELECT user_id, value FROM settings WHERE key = 'webhook_api_key'")
            ).fetchall()
            candidates = []
            for row in rows:
                stored_val = self._decrypt(row[1])
                if isinstance(stored_val, str):
                    stored_val = stored_val.strip('"')
                if _secrets.compare_digest(str(stored_val), str(secret)):
                    return row[0]
                candidates.append(str(stored_val))

            # No match — emit a NON-SECRET diagnostic: lengths and an
            # "is it still ciphertext?" flag. No value, and no digest of a
            # value, ever reaches the log.
            #
            # 2026-08-02: dropped a truncated SHA-256 fingerprint that used to
            # be logged here. It contributed nothing the flag below doesn't
            # already give, and running a secret through a fast hash is the
            # pattern static analysis flags (py/weak-sensitive-data-hashing) —
            # correctly, since "we only truncate it" is not a security property
            # anyone should have to audit.
            #
            # `still_enc` is what actually separates the two failure modes:
            #   - genuine key mismatch: every candidate decrypts, so all show
            #     still_enc=False and the lengths tell you whether the operator
            #     pasted a truncated or entirely different value
            #   - APP_SECRET_KEY rotated: _decrypt swallows the Fernet failure
            #     and hands back the raw ciphertext, so still_enc=True and the
            #     length jumps to the ciphertext length
            #
            # 只記錄長度與 still_enc 旗標，既不記錄值也不記錄值的雜湊。
            # still_enc 才是區分「金鑰不符」與「APP_SECRET_KEY 輪換」的關鍵，
            # 原本那個截斷雜湊對這個判斷沒有貢獻。
            _logger.warning(
                "Webhook secret mismatch: presented(len=%d) | candidates=%d | %s",
                len(str(secret)), len(candidates),
                ", ".join(
                    f"[len={len(c)} still_enc={c.startswith(('ENC:', 'FERN:', 'B64H:'))}]"
                    for c in candidates
                ) or "(no webhook_api_key rows)",
            )
            return None
        except Exception as e:
            _logger.warning(f'Exception in settings_repository.py: {e}', exc_info=True)
            return None
        finally:
            self.close_session()

# Legacy aliases removed in v4.1.7
# @deprecated: Use AlchemySettingsRepository
