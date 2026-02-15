import requests
import json
import logging
from typing import List, Dict, Optional, Any
from src.domain.interfaces import IChannelAdapter

logger = logging.getLogger(__name__)

class SlackAdapter(IChannelAdapter):
    """
    Slack Adapter using Web API (chat.postMessage).
    Supports Block Kit for rich interaction.
    """
    def __init__(self, bot_token: str = None, channel_id: str = None):
        import os
        self.bot_token = (bot_token or os.getenv("SLACK_BOT_TOKEN", "")).strip()
        self.channel_id = (channel_id or os.getenv("SLACK_CHANNEL_ID", "")).strip()
        self.api_url = "https://slack.com/api/chat.postMessage"
        self.is_active = bool(self.bot_token and self.channel_id)

    def send_alert(self, user_id: str, title: str, content: str, actions: List[Dict[str, str]] = None, **kwargs) -> bool:
        """
        Send message to Slack.
        user_id arg can be used to override self.channel_id if provided (e.g. DM).
        """
        target_channel = user_id if user_id else self.channel_id
        
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
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": action.get("label", "Click"),
                        "emoji": True
                    },
                    "value": action.get("data", ""),
                    "action_id": action.get("key", "action")
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
    def register_callback(self, callback_func):
        self.callback = callback_func

    def handle_webhook(self, payload: Dict[str, Any], headers: Dict[str, Any] = None):
        """
        Handle Slack Interactive Components (Block Actions).
        Payload is usually form-encoded JSON string in 'payload' field, but here we assume pre-parsed dict or similar.
        For FastAPI Form data, the caller might need to parse `payload` field.
        """
        # Verification check (usually done in middleware or router via headers)
        # Here we process the parsed JSON payload
        
        # Check if it's an interaction payload
        if payload.get("type") == "block_actions":
            actions = payload.get("actions", [])
            for action in actions:
                action_id = action.get("action_id") # e.g., "approve"
                value = action.get("value")         # e.g., request_id
                
                if self.callback and action_id and value:
                    logger.info(f"Slack Callback: {action_id} for {value}")
                    self.callback(value, action_id)
        
        return {"ok": True}
