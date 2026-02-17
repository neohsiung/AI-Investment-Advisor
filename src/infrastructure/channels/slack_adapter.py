import hmac
import hashlib
import time
import requests
import json
import logging
from typing import List, Dict, Optional, Any
from src.domain.interfaces import IChannelAdapter

from src.infrastructure.channels.base_adapter import BaseChannelAdapter

logger = logging.getLogger(__name__)

class SlackAdapter(BaseChannelAdapter):
    """
    Slack Adapter using Web API (chat.postMessage).
    Supports Block Kit for rich interaction.
    """
    def __init__(self, bot_token: str = None, channel_id: str = None, signing_secret: str = None):
        import os
        super().__init__(default_target_id=channel_id)
        self.bot_token = (bot_token or os.getenv("SLACK_BOT_TOKEN", "")).strip()
        self.signing_secret = (signing_secret or os.getenv("SLACK_SIGNING_SECRET", "")).strip()
        self.channel_id = self.default_target_id
        self.api_url = "https://slack.com/api/chat.postMessage"
        self.is_active = bool(self.bot_token and self.channel_id)

    def send_message(self, user_id: str, message: Any, **kwargs) -> bool:
        """
        Send a generic message.
        """
        if isinstance(message, str):
            return self.send_alert(user_id, "Message", message)
        return False

    def receive_command(self, payload: Any, **kwargs) -> Any:
        return None

    def authenticate(self, request: Any, **kwargs) -> bool:
        """
        Legacy authenticate method, delegating to verify_signature if headers are present.
        """
        headers = kwargs.get("headers")
        if headers:
            return self.verify_signature(request, headers)
        return True

    def verify_signature(self, payload: Any, headers: Dict[str, Any] = None) -> bool:
        """
        Verify Slack signature (X-Slack-Signature).
        Requires SLACK_SIGNING_SECRET.
        """
        if not self.signing_secret:
            logger.warning("SlackAdapter: Missing SLACK_SIGNING_SECRET. Skipping signature verification.")
            return True # Fallback to allow if not configured, or change to False for strict security
            
        if not headers:
            return False
            
        signature = headers.get('x-slack-signature') or headers.get('X-Slack-Signature')
        timestamp = headers.get('x-slack-request-timestamp') or headers.get('X-Slack-Request-Timestamp')
        
        if not signature or not timestamp:
            logger.error("Slack signature or timestamp missing.")
            return False
            
        # 1. Prevent replay attacks (limit to 5 minutes)
        if abs(time.time() - int(timestamp)) > 60 * 5:
            logger.error("Slack request timestamp too old.")
            return False
            
        # 2. Reconstruct the base string
        # Slack sends body as raw bytes or string. 
        # For signature, it must be exactly as received.
        request_body = payload
        if isinstance(request_body, dict):
            # If already parsed, this is problematic for signature.
            # Usually the router should pass the raw body.
            request_body = json.dumps(request_body, separators=(',', ':'))
            
        sig_basestring = f"v0:{timestamp}:{request_body}"
        
        # 3. Calculate HMAC-SHA256
        computed_signature = 'v0=' + hmac.new(
            self.signing_secret.encode(),
            sig_basestring.encode(),
            hashlib.sha256
        ).hexdigest()
        
        if hmac.compare_digest(computed_signature, signature):
            return True
        else:
            logger.error("Slack signature verification failed.")
            return False

    def send_alert(self, user_id: str, title: str, content: str, actions: List[Dict[str, str]] = None, **kwargs) -> bool:
        """
        Send message to Slack.
        user_id arg can be used to override self.channel_id if provided (e.g. DM).
        """
        target_channel = self._resolve_target_id(user_id)
        
        if not self.bot_token or not target_channel:
            logger.warning("SlackAdapter: Missing token or channel_id. Skipping.")
            return False

        # Build Block Kit
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": title[:3000],  # Slack limit
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": content[:3000]
                }
            }
        ]

        # Add Actions (Buttons)
        if actions:
            elements = []
            for action in actions:
                elements.append({
                    "text": {
                        "type": "plain_text",
                        "text": action.get("label", "Click"),
                        "emoji": True
                    },
                    "value": action.get("data", ""),
                    "action_id": action.get("key", "action"),
                    "type": "button"
                })
            
            blocks.append({
                "type": "actions",
                "elements": elements
            })

        payload = {
            "channel": target_channel,
            "blocks": blocks,
            "text": f"{title}: {content}" # Fallback text
        }

        headers = {
            "Authorization": f"Bearer {self.bot_token}",
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(self.api_url, headers=headers, json=payload, timeout=10)
            data = response.json()
            if data.get("ok"):
                logger.info(f"Slack message sent to {target_channel}")
                return True
            else:
                logger.error(f"Slack API error: {data.get('error')}")
                return False
        except Exception as e:
            logger.error(f"SlackAdapter exception: {e}")
            return False

    def handle_webhook(self, payload: Dict[str, Any], headers: Dict[str, Any] = None):
        """
        Handle Slack Interactive Components (Block Actions).
        """
        if headers and not self.verify_signature(payload, headers):
            return {"ok": False, "error": "Invalid signature"}

        # 1. Handle Block Actions (Buttons)
        if payload.get("type") == "block_actions":
            actions = payload.get("actions", [])
            for action in actions:
                action_id = action.get("action_id") # e.g., "approve"
                value = action.get("value")         # e.g., request_id
                
                if self.callback and action_id and value:
                    logger.info(f"Slack Callback: {action_id} for {value}")
                    self._trigger_callback(value, action_id)
        
        # 2. Handle Message Events (Text)
        elif payload.get("type") == "event_callback":
            event = payload.get("event", {})
            if event.get("type") == "message" and not event.get("bot_id"):
                text = event.get("text")
                user = event.get("user")
                channel = event.get("channel")
                if text and (user or channel):
                    logger.info(f"Slack Text: {text} from {user or channel}")
                    # For Slack, we use channel ID or user ID as the 'address'
                    self._trigger_text_callback(channel or user, text)
        
        return {"ok": True}
