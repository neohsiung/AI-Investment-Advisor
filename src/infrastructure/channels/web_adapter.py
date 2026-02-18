import logging
import json
import uuid
from typing import List, Dict, Any
from datetime import datetime
from src.domain.interfaces import IChannelAdapter
from src.data.database import get_db_connection
from sqlalchemy import text

from src.infrastructure.channels.base_adapter import BaseChannelAdapter

logger = logging.getLogger(__name__)

class WebAdapter(BaseChannelAdapter):
    """
    Adapter for Web (Dashboard) notifications.
    Records alerts into the event_logs table for display on the Dashboard.
    """
    def __init__(self):
        super().__init__()
    
    def send_message(self, user_id: str, message: Any, **kwargs) -> bool:
        """
        Send a generic message (Web).
        """
        if isinstance(message, str):
            return self.send_alert(user_id, "Message", message)
        return False


    async def send_message(self, user_id: str, message: Any, **kwargs) -> bool:
        """
        Record message in event_logs.
        """
        title = "Notification"
        content = ""
        actions = None
        
        if isinstance(message, str):
            content = message
        elif isinstance(message, dict):
            title = message.get("title", title)
            content = message.get("content", str(message))
            actions = message.get("actions")
        
        return await self.send_alert(user_id, title, content, actions, **kwargs)

    async def send_alert(self, user_id: str, title: str, content: str, actions: List[Dict[str, str]] = None, **kwargs) -> bool:
        """
        Record alert in event_logs asynchronously.
        """
        import asyncio
        
        def _execute_db():
            try:
                with get_db_connection() as conn:
                    log_id = str(uuid.uuid4())
                    timestamp = datetime.now().isoformat()
                    metadata = {
                        "user_id": user_id,
                        "actions": actions,
                        "source_adapter": "WebAdapter"
                    }
                    
                    conn.execute(text(
                        "INSERT INTO event_logs (id, timestamp, source, level, title, content, metadata) "
                        "VALUES (:id, :ts, :source, :level, :title, :content, :meta)"
                    ), {
                        "id": log_id,
                        "ts": timestamp,
                        "source": kwargs.get("source", "Sentinel/Workflow"),
                        "level": kwargs.get("level", "INFO"),
                        "title": title,
                        "content": content,
                        "meta": json.dumps(metadata)
                    })
                    conn.commit()
                return True
            except Exception as e:
                logger.error(f"Failed to record Web Alert: {e}")
                return False

        return await asyncio.to_thread(_execute_db)

