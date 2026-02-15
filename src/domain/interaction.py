from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
import uuid

class InteractionType(Enum):
    APPROVAL = "APPROVAL"       # Yes/No confirmation
    CLARIFICATION = "CLARIFY"   # Open-ended question
    COMMAND = "COMMAND"         # User initiated

class InteractionStatus(Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    COMPLETED = "COMPLETED"

@dataclass
class InteractionRequest:
    """
    Represents a request for user interaction (e.g. approval).
    """
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: InteractionType = InteractionType.APPROVAL
    title: str = ""
    content: str = ""
    payload: Dict[str, Any] = field(default_factory=dict) # Context data (e.g. Order details)
    
    status: InteractionStatus = InteractionStatus.PENDING
    response: Optional[str] = None
    
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    
    channel_id: Optional[str] = None # Which channel sent/received this
    user_id: Optional[str] = None

    def is_pending(self) -> bool:
        if self.status != InteractionStatus.PENDING:
            return False
        if self.expires_at and datetime.now() > self.expires_at:
            self.status = InteractionStatus.EXPIRED
            return False
        return True
