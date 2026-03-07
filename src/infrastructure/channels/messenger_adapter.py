import os
import json
import hmac
import hashlib
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, Any, List
from src.utils.logger import setup_logger
from src.infrastructure.channels.base_adapter import BaseChannelAdapter

logger = setup_logger("MessengerAdapter")

class MessengerAdapter(BaseChannelAdapter):
    """
    Facebook Messenger Adapter using Graph API (Send API).
    """
    def __init__(self, page_token: str = None, verify_token: str = None, app_secret: str = None):
        import os
        super().__init__()
        self.page_token = (page_token or os.getenv("MESSENGER_PAGE_TOKEN", "")).strip()
        self.verify_token = (verify_token or os.getenv("MESSENGER_VERIFY_TOKEN", "")).strip()
        self.app_secret = (app_secret or os.getenv("MESSENGER_APP_SECRET", "")).strip()
        self.api_version = "v18.0" # Use a recent stable version
        self.base_url = f"https://graph.facebook.com/{self.api_version}/me/messages"
        self.is_active = bool(self.page_token)

    async def send_message(self, user_id: str, message: Any, **kwargs) -> bool:
        """
        Send a generic message asynchronously.
        """
        if isinstance(message, str):
            return await self.send_alert(user_id, "Message", message)
        return False

    async def receive_command(self, payload: Any, **kwargs) -> Any:
        return None

    async def authenticate(self, request: Any, **kwargs) -> bool:
        """
        Standard authenticate method.
        """
        headers = kwargs.get("headers")
        if headers:
            return self.verify_signature(request, headers)
        return True

    def verify_signature(self, payload: Any, headers: Dict[str, Any] = None) -> bool:
        """
        Verify Messenger signature (X-Hub-Signature-256).
        """
        if not self.app_secret:
            logger.warning("MessengerAdapter: Missing MESSENGER_APP_SECRET. Skipping signature verification.")
            return True
            
        if not headers:
            return False
            
        signature = headers.get('x-hub-signature-256') or headers.get('X-Hub-Signature-256')
        if not signature:
            logger.error("Messenger signature missing.")
            return False
            
        if not signature.startswith('sha256='):
            logger.error("Invalid Messenger signature format.")
            return False
            
        expected_sig = signature[7:]
        
        request_body = payload
        if isinstance(request_body, dict):
            request_body = json.dumps(request_body, separators=(',', ':'))
            
        computed_sig = hmac.new(
            self.app_secret.encode(),
            request_body.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(computed_sig, expected_sig)

    async def send_alert(self, user_id: str, title: str, content: str, actions: List[Dict[str, str]] = None, **kwargs) -> bool:
        """
        Send message to Messenger (PSID) asynchronously.
        """
        import httpx
        target_psid = self._resolve_target_id(user_id)
        
        if not self.page_token or not target_psid:
             logger.warning("MessengerAdapter: Missing token or user_id (PSID). Skipping.")
             return False

        params = {"access_token": self.page_token}
        
        if not actions:
             payload = {
                 "recipient": {"id": target_psid},
                 "message": {"text": f"{title}\n\n{content}"[:2000]}
             }
        else:
             buttons = []
             for action in actions:
                 buttons.append({
                     "type": "postback",
                     "title": action.get("label", "Click")[:20],
                     "payload": action.get("data", "action")
                 })
                 if len(buttons) >= 3: break
             
             payload = {
                 "recipient": {"id": target_psid},
                 "message": {
                     "attachment": {
                         "type": "template",
                         "payload": {
                             "template_type": "button",
                             "text": f"{title}\n{content}"[:640],
                             "buttons": buttons
                         }
                     }
                 }
             }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(self.base_url, params=params, json=payload, timeout=10.0)
                data = response.json()
                if "recipient_id" in data:
                    logger.info(f"Messenger message sent to {target_psid}")
                    return True
                else:
                    logger.error(f"Messenger API error: {data}")
                    return False
        except Exception as e:
            logger.error(f"MessengerAdapter exception: {e}")
            return False

    async def handle_webhook(self, payload: Dict[str, Any], headers: Dict[str, Any] = None):
        """
        Handle Messenger Postbacks asynchronously.
        """
        if headers and not self.verify_signature(payload, headers):
            return "INVALID_SIGNATURE"

        # Messenger payload structure: entry[].messaging[]
        entries = payload.get("entry", [])
        for entry in entries:
            messaging_events = entry.get("messaging", [])
            for event in messaging_events:
                 sender_id = event.get("sender", {}).get("id")
                 
                 # 1. Handle Postback (Buttons)
                 if "postback" in event:
                     postback = event["postback"]
                     payload_str = postback.get("payload")
                     
                     params = {}
                     if payload_str:
                         for part in payload_str.split("&"):
                             if "=" in part:
                                 k, v = part.split("=", 1)
                                 params[k] = v

                     request_id = params.get("id")
                     action = params.get("action")

                     if self.callback and request_id and action:
                         logger.info(f"Messenger Callback: {action} for {request_id}")
                         await self._trigger_callback(request_id, action)
                 
                 # 2. Handle Message (Text)
                 elif "message" in event:
                     message = event["message"]
                     # Ignore messages from the page itself (echoes) or attachments
                     if not message.get("is_echo") and "text" in message:
                         text = message.get("text")
                         if sender_id and text:
                             logger.info(f"Messenger Text: {text} from {sender_id}")
                             await self._trigger_text_callback(sender_id, text)

        return "EVENT_RECEIVED"
