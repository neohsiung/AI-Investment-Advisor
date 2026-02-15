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
        FlexContainer,
        TextMessageContent
    )
    from linebot.v3.webhooks import MessageEvent, PostbackEvent

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

    def __init__(self, channel_access_token: str = None, channel_secret: str = None):
        """
        Initialize LINE Bot API Client.
        初始化 LINE Bot API 客戶端。
        Args:
            channel_access_token: Optional token (overrides env)
            channel_secret: Optional secret (overrides env)
        """
        self.channel_access_token = (channel_access_token or os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "mock_token")).strip()
        self.channel_secret = (channel_secret or os.getenv("LINE_CHANNEL_SECRET", "mock_secret")).strip()
        
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

    def register_callback(self, callback_func):
        """
        Register a callback function to handle Button interactions (Postback).
        callback_func(request_id, action)
        """
        self.callback = callback_func

    def register_text_callback(self, callback_func):
        """
        Register a callback function to handle Text messages.
        callback_func(user_id, text)
        """
        self.text_callback = callback_func

    def handle_webhook(self, payload: Any, headers: Dict[str, Any] = None):
        """
        Forward webhook to handler.
        Matching IChannelAdapter interface.
        """
        if not self.is_active:
            return
            
        # Extract Signature
        signature = None
        if isinstance(headers, str):
             # Legacy call: handle_webhook(body, signature_str)
             signature = headers
        elif isinstance(headers, dict):
             # New IChannelAdapter interface
             # Case-insensitive lookup for headers if possible, but assuming standard dict
             for k, v in headers.items():
                 if k.lower() == 'x-line-signature':
                     signature = v
                     break

        if not signature:
            logger.warning("LINE Webhook: Missing signature.")
            return

        try:
            body = payload # payload is the body string for LINE
            # Define internal handler for events if not already done
            # Note: In a real implementation this should be done in __init__ 
            # but we need the handler instance to add specific event handlers
            
            events = self.handler.parser.parse(body, signature)
            
            for event in events:
                user_id = event.source.user_id
                
                if isinstance(event, PostbackEvent):
                    # Handle Button Click
                    data_str = event.postback.data
                    
                    # Parse data string "action=approve&id=..."
                    parsed_data = {}
                    for pair in data_str.split('&'):
                        if '=' in pair:
                            k, v = pair.split('=', 1)
                            parsed_data[k] = v
                            
                    logger.info(f"LINE Postback: {parsed_data} from {user_id}")
                    
                    if hasattr(self, 'callback') and self.callback:
                        # InteractionService expects (request_id, action)
                        req_id = parsed_data.get('id')
                        action = parsed_data.get('action')
                        if req_id and action:
                            self.callback(req_id, action)
                        else:
                            # Fallback for legacy or raw data
                            # self.callback(user_id, data_str) # Disable fallback if signature mismatch risk
                            pass

                elif isinstance(event, MessageEvent) and isinstance(event.message, TextMessageContent):
                    # Handle Text Message
                    text = event.message.text
                    logger.info(f"LINE Text: {text} from {user_id}")
                    
                    if hasattr(self, 'text_callback') and self.text_callback:
                        self.text_callback(user_id, text)
                        
        except InvalidSignatureError:
            raise ValueError("Invalid signature")
        except Exception as e:
            logger.error(f"LINE Webhook Error: {e}")
