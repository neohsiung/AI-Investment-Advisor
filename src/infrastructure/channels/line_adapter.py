import logging
import os
import json
from typing import Dict, Any, List

# Try importing linebot sdk, handle if missing for phase-by-phase dev
try:
    from linebot.v3 import WebhookHandler
    from linebot.v3.messaging import (
        Configuration,
        ApiClient,
        MessagingApi,
        ReplyMessageRequest,
        PushMessageRequest,
        TextMessage,
        FlexMessage,
        FlexContainer
    )
    from linebot.v3.exceptions import (
        InvalidSignatureError
    )
    HAS_LINE_SDK = True
except ImportError:
    HAS_LINE_SDK = False
    WebhookHandler = object # Mock

from src.domain.interfaces import IChannelAdapter

logger = logging.getLogger(__name__)

class LineBotAdapter(IChannelAdapter):
    """
    Adapter for LINE Messaging API (v3).
    Handles Push Messages (Alerts) and Webhook Events (User Feedback).
    LINE Messaging API (v3) 適配器。
    處理推播訊息 (警報) 與 Webhook 事件 (使用者回饋)。
    """

    def __init__(self):
        """
        Initialize LINE Bot API Client.
        初始化 LINE Bot API 客戶端。
        """
        self.channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "mock_token")
        self.channel_secret = os.getenv("LINE_CHANNEL_SECRET", "mock_secret")
        
        if HAS_LINE_SDK and self.channel_access_token != "mock_token":
            configuration = Configuration(access_token=self.channel_access_token)
            self.api_client = ApiClient(configuration)
            self.messaging_api = MessagingApi(self.api_client)
            self.handler = WebhookHandler(self.channel_secret)
            self.is_active = True
        else:
            logger.warning("LINE Bot SDK not installed or tokens missing. Running in MOCK mode.")
            self.is_active = False

    def send_alert(self, user_id: str, title: str, content: str, actions: List[Dict[str, str]] = None, **kwargs) -> bool:
        """
        Sends a rich Flex Message Alert.
        發送 Flex Message 格式的豐富及時警報。
        
        Args:
            user_id: LINE User ID (or 'broadcast').
            title: Alert Title (e.g. "VIX SPIKE ALERT")
            content: Main body text (內文).
            actions: List of dicts [{"label": "Execute", "data": "action=buy"}] (按鈕動作)
        
        Returns:
            bool: True if successful or mock.
        """
        if not self.is_active:
            logger.info(f"[MOCK LINE] Sending User {user_id}: {title} - {content}")
            return True

        try:
            # Construct Flex Bubble
            bubble_json = {
                "type": "bubble",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": title,
                            "weight": "bold",
                            "color": "#D32F2F", # Red for alert
                            "size": "lg"
                        }
                    ],
                    "backgroundColor": "#FFEBEE"
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": content,
                            "wrap": True,
                            "color": "#333333"
                        }
                    ]
                }
            }
            
            # Add Actions (Buttons)
            if actions:
                footer_contents = []
                for action in actions:
                    footer_contents.append({
                        "type": "button",
                        "style": "primary" if action.get("style") != "secondary" else "secondary",
                        "action": {
                            "type": "postback",
                            "label": action.get("label", "Action"),
                            "data": action.get("data", "no_data"),
                            "displayText": action.get("label", "Action")
                        }
                    })
                
                bubble_json["footer"] = {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "sm",
                    "contents": footer_contents
                }

            flex_message = FlexMessage(
                alt_text=f"Alert: {title}",
                contents=bubble_json
            )

            # Send
            request = PushMessageRequest(
                to=user_id,
                messages=[flex_message]
            )
            self.messaging_api.push_message(request)
            logger.info(f"LINE Alert sent to {user_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to send LINE Flex Message: {e}")
            return False

    def send_flex_alert(self, user_id: str, title: str, content: str, actions: List[Dict[str, str]] = None):
        """
        [DEPRECATED] Use send_alert instead.
        """
        return self.send_alert(user_id, title, content, actions)

    def handle_webhook(self, body: str, signature: str):
        """
        Forward webhook to handler.
        """
        if not self.is_active:
            return
            
        try:
            self.handler.handle(body, signature)
        except InvalidSignatureError:
            raise ValueError("Invalid signature")
