import datetime
import typing
import uuid
import logging
from abc import ABC, abstractmethod
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
from sqlalchemy import text, desc, or_
from src.data.database import BaseRepository, get_db_engine
from src.data.models import ChannelVerification

logger = logging.getLogger(__name__)

class IVerificationRepository(ABC):
    """
    Interface for Verification Repository.
    驗證儲存庫介面。
    """
    @abstractmethod
    def create_verification(self, user_id: str, channel: str, channel_user_id: str, code: str, expires_at: datetime.datetime) -> None:
        """
        Create a new verification record.
        建立新的驗證記錄。
        """
        pass

    @abstractmethod
    def get_by_code(self, channel: str, code: str) -> Optional[Dict[str, Any]]:
        """
        Get a pending verification by channel and code.
        依頻道與代碼取得待處理的驗證。
        """
        pass

    @abstractmethod
    def get_by_user_id(self, user_id: str, channel: str) -> Optional[Dict[str, Any]]:
        """
        Get the latest verification for a user.
        取得使用者的最新驗證。
        """
        pass

    @abstractmethod
    def get_pending_verification(self, user_id: str, channel: str) -> Optional[Dict[str, Any]]:
        """
        Get a pending, non-expired verification for a specific channel.
        取得特定頻道且未過期的待處理驗證。
        """
        pass

    @abstractmethod
    def get_any_pending_verification(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get any pending, non-expired verification for a user.
        取得使用者任何頻道的待處理驗證。
        """
        pass

    @abstractmethod
    def update_status(self, verification_id: str, status: str, error_message: str = None) -> bool:
        """
        Update the status of a verification.
        更新驗證狀態。
        """
        pass

    @abstractmethod
    def get_verification_by_id(self, verification_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a verification record by ID.
        依 ID 取得驗證記錄。
        """
        pass

class AlchemyVerificationRepository(BaseRepository, IVerificationRepository):
    """
    Implementation of IVerificationRepository using SQLAlchemy ORM.
    使用 SQLAlchemy ORM 實作的 IVerificationRepository。
    """
    def __init__(self, db_path: str = None, engine: Any = None):
        """
        Initialize the repository.
        初始化儲存庫。
        """
        BaseRepository.__init__(self, engine or get_db_engine(db_path))

    def create_verification(self, user_id: str, channel: str, channel_user_id: str, code: str, expires_at: datetime.datetime) -> None:
        """
        Create a new verification record (ORM).
        建立新的驗證記錄 (ORM)。
        """
        session = self.session
        try:
            verif = ChannelVerification(
                id=str(uuid.uuid4()),
                user_id=str(user_id),
                channel=channel,
                channel_user_id=str(channel_user_id),
                code=code,
                expires_at=expires_at
            )
            session.add(verif)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to create verification: {e}")
            raise

    def get_by_code(self, channel: str, code: str) -> Optional[Dict[str, Any]]:
        """
        Get a pending verification by channel and code (ORM).
        依頻道與代碼取得待處理的驗證 (ORM)。
        """
        verif = self.session.query(ChannelVerification).filter_by(
            channel=channel, code=code, status='pending'
        ).first()
        return self._to_dict(verif) if verif else None

    def get_by_user_id(self, user_id: str, channel: str) -> Optional[Dict[str, Any]]:
        """
        Get the latest verification for a user (ORM).
        取得使用者的最新驗證 (ORM)。
        """
        verif = self.session.query(ChannelVerification).filter_by(
            user_id=user_id, channel=channel
        ).order_by(desc(ChannelVerification.created_at)).first()
        return self._to_dict(verif) if verif else None

    def get_pending_verification(self, user_id: str, channel: str) -> Optional[Dict[str, Any]]:
        """
        Get a pending, non-expired verification for a specific channel (ORM).
        取得特定頻道且未過期的待處理驗證 (ORM)。
        """
        verif = self.session.query(ChannelVerification).filter(
            or_(ChannelVerification.user_id == user_id, ChannelVerification.channel_user_id == user_id),
            ChannelVerification.channel == channel,
            ChannelVerification.status == 'pending',
            ChannelVerification.expires_at > datetime.datetime.now(datetime.timezone.utc)
        ).order_by(desc(ChannelVerification.created_at)).first()
        return self._to_dict(verif) if verif else None

    def get_any_pending_verification(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get any pending, non-expired verification for a user (ORM).
        取得使用者任何頻道的待處理驗證 (ORM)。
        """
        # Improved: Check both user_id (internal) AND channel_user_id (external/platform ID)
        logger.debug(f"get_any_pending_verification searching for: {user_id}")
        verif = self.session.query(ChannelVerification).filter(
            or_(
                ChannelVerification.user_id == user_id, 
                ChannelVerification.channel_user_id == user_id
            ),
            ChannelVerification.status == 'pending',
            ChannelVerification.expires_at > datetime.datetime.utcnow() # Use UTC
        ).order_by(desc(ChannelVerification.created_at)).first()
        
        if verif:
            logger.info(f"DB Found Verification: ID={verif.id}, user_id={verif.user_id}, channel_id={verif.channel_user_id}, code={verif.code}")
        else:
            logger.warning(f"DB Match Failure for user_id/channel_user_id: {user_id}")
            
        return self._to_dict(verif) if verif else None

    def update_status(self, verification_id: str, status: str, error_message: str = None) -> bool:
        """
        Update the status of a verification (ORM).
        更新驗證狀態 (ORM)。
        """
        session = self.session
        try:
            verif = session.get(ChannelVerification, verification_id)
            if verif:
                verif.status = status
                verif.error_message = error_message
                session.commit()
                return True
            return False
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to update verification status: {e}")
            return False

    def get_verification_by_id(self, verification_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a verification record by ID (ORM).
        依 ID 取得驗證記錄 (ORM)。
        """
        verif = self.session.get(ChannelVerification, verification_id)
        return self._to_dict(verif) if verif else None

    def _to_dict(self, model: ChannelVerification) -> Dict[str, Any]:
        """
        Model to dict utility.
        Model 轉 Dict 工具。
        """
        if not model: return None
        return {
            "id": model.id,
            "user_id": model.user_id,
            "channel": model.channel,
            "channel_user_id": model.channel_user_id,
            "code": model.code,
            "status": model.status,
            "error_message": model.error_message,
            "expires_at": model.expires_at,
            "created_at": model.created_at
        }

# Legacy alias removed in v4.1.7
# @deprecated: Use AlchemyVerificationRepository
