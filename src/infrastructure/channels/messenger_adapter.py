import requests
import json
import logging
from typing import List, Dict, Optional, Any
from src.domain.interfaces import IChannelAdapter

logger = logging.getLogger(__name__)

class MessengerAdapter(IChannelAdapter):
    """
    Facebook Messenger Adapter using Graph API (Send API).
    """
    def __init__(self, page_token: str = None, verify_token: str = None):
        import os
        self.page_token = (page_token or os.getenv("MESSENGER_PAGE_TOKEN", "")).strip()
        self.verify_token = (verify_token or os.getenv("MESSENGER_VERIFY_TOKEN", "")).strip()
        self.api_version = "v18.0" # Use a recent stable version
        self.base_url = f"https://graph.facebook.com/{self.api_version}/me/messages"
        self.is_active = bool(self.page_token)

    def send_alert(self, user_id: str, title: str, content: str, actions: List[Dict[str, str]] = None, **kwargs) -> bool:
        """
        Send message to Messenger (PSID).
        user_id must be a PSID (Page-Scoped ID).
        """
        if not self.page_token or not user_id:
             logger.warning("MessengerAdapter: Missing token or user_id (PSID). Skipping.")
             return False

        params = {
            "access_token": self.page_token
        }
        
        # Construct Payload
        # If actions, use Button Template or Generic Template
        # Note: Button Template has text limit (640 chars). If content is long, send text first then buttons.
        
        # Strategy: Send Text First, then Buttons if needed interaction
        # Actually Generic Template allows image + title + subtitle + buttons.
        
        # Let's try simple text message first if no actions
        if not actions:
             payload = {
                 "recipient": {"id": user_id},
                 "message": {"text": f"{title}\n\n{content}"[:2000]}
             }
        else:
             # Use Button Template
             buttons = []
             for action in actions:
                 buttons.append({
                     "type": "postback",
                     "title": action.get("label", "Click")[:20], # limit 20 chars
                     "payload": action.get("data", "action")
                 })
                 if len(buttons) >= 3: break # Limit 3 buttons
             
             payload = {
                 "recipient": {"id": user_id},
                 "message": {
                     "attachment": {
                         "type": "template",
                         "payload": {
                             "template_type": "button",
                             "text": f"{title}\n{content}"[:640], # Limit 640 chars
                             "buttons": buttons
                         }
                     }
                 }
             }

        try:
            response = requests.post(self.base_url, params=params, json=payload, timeout=10)
            data = response.json()
            if "recipient_id" in data:
                logger.info(f"Messenger message sent to {user_id}")
                return True
            else:
                logger.error(f"Messenger API error: {data}")
                return False
        except Exception as e:
            logger.error(f"MessengerAdapter exception: {e}")
            return False
    def register_callback(self, callback_func):
        self.callback = callback_func

    def handle_webhook(self, payload: Dict[str, Any], headers: Dict[str, Any] = None):
        """
        Handle Messenger Postbacks.
        """
        # Messenger payload structure: entry[].messaging[].postback
        entries = payload.get("entry", [])
        for entry in entries:
            messaging_events = entry.get("messaging", [])
            for event in messaging_events:
                 if "postback" in event:
                     postback = event["postback"]
                     payload_str = postback.get("payload") # e.g. "action=approve&id=123"
                     
                     # Parse same way as Telegram/Generic
                     params = {}
                     if payload_str:
                         for part in payload_str.split("&"):
                             if "=" in part:
                                 k, v = part.split("=", 1)
                                 params[k] = v

                     request_id = params.get("id")
                     action = params.get("action") # "approve" logic usually implies action parameter
                     # But here we might have just sent "approve_123" or similar. 
                     # Let's assume standardized "action=approve&id=123" format in send_alert.

                     if self.callback and request_id and action:
                         logger.info(f"Messenger Callback: {action} for {request_id}")
                         self.callback(request_id, action)

        return "EVENT_RECEIVED"
