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
    from linebot.v3.webhooks import MessageEvent, PostbackEvent, TextMessageContent

    from linebot.v3.exceptions import (
        InvalidSignatureError
    )
    HAS_LINE_SDK = True
except ImportError:
    HAS_LINE_SDK = False
    WebhookHandler = object # Mock

from src.domain.interfaces import IChannelAdapter
from src.infrastructure.channels.base_adapter import BaseChannelAdapter

logger = logging.getLogger(__name__)

class LineBotAdapter(BaseChannelAdapter):
    """
    LINE Bot Adapter using Messaging API (V3 SDK).
    處理推播訊息 (警報) 與 Webhook 事件 (使用者回饋)。
    """

    def __init__(self, channel_access_token: str = None, channel_secret: str = None, line_user_id: str = None):
        """
        Initialize LINE Bot API Client.
        初始化 LINE Bot API 客戶端。
        Args:
            channel_access_token: Optional token (overrides env)
            channel_secret: Optional secret (overrides env)
        """
        super().__init__(default_target_id=line_user_id)
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

    def send_message(self, user_id: str, message: Any, **kwargs) -> bool:
        """
        Send a generic message.
        kwargs:
            raise_error (bool): If True, raise exception on failure instead of returning False.
        """
        raise_error = kwargs.get("raise_error", False)
        
        if not self.is_active:
            logger.info(f"[MOCK LINE] Sending User {user_id}: {message}")
            return True

        try:
            line_message = None
            if isinstance(message, str):
                line_message = TextMessage(text=message)
            elif isinstance(message, dict):
                msg_type = message.get("type")
                if msg_type == "text":
                    line_message = TextMessage(text=message.get("text"))
                elif msg_type == "flex":
                    contents = message.get("contents")
                    if isinstance(contents, dict):
                        contents = FlexContainer.from_dict(contents)
                    line_message = FlexMessage(
                        alt_text=message.get("alt_text", "Flex Message"),
                        contents=contents
                    )
                elif msg_type == "alert":
                    return self.send_alert(
                        user_id, 
                        message.get("title"), 
                        message.get("content"), 
                        message.get("actions"),
                        **kwargs
                    )

            if line_message:
                request = PushMessageRequest(
                    to=user_id,
                    messages=[line_message]
                )
                self.messaging_api.push_message(request)
                logger.info(f"LINE Message sent to {user_id}")
                return True
            else:
                error_msg = f"Unsupported message format: {message}"
                logger.warning(error_msg)
                if raise_error:
                    raise ValueError(error_msg)
                return False

        except Exception as e:
            logger.error(f"Failed to send LINE Message: {e}")
            if raise_error:
                raise e
            return False

    def authenticate(self, request: Any, headers: Dict[str, Any] = None, **kwargs) -> bool:
        """
        Verify request signature.
        """
        if not self.is_active:
            return True

        if not headers:
            return False

        signature = None
        if isinstance(headers, dict):
             # Header keys might be case-insensitive in frameworks, 
             # but here we expect a dict.
             # Look for 'x-line-signature' or 'X-Line-Signature'
             signature = headers.get('x-line-signature') or headers.get('X-Line-Signature')
        
        if not signature:
            logger.error("LINE Authenticate: Missing signature header.")
            return False

        # Use 3rd party SDK validator if available, or just rely on parser in handle_webhook
        # Since parser.parse raises InvalidSignatureError, we can simulate auth check:
        # But to be strict `authenticate`, we should use SignatureValidator.
        # For now, we will assume true if signature exists, and let handle_webhook/parser fail if invalid.
        # OR, strictly:
        # signature_validator = SignatureValidator(self.channel_secret)
        # return signature_validator.validate(request, signature)
        # Since we didn't import SignatureValidator explicitly in current imports,
        # we'll rely on handle_webhook's try-catch for now for deep validation.
        return True

    def receive_command(self, payload: Any, **kwargs) -> Any:
        """
        Parse payload into events.
        """
        if not self.is_active:
            return []

        # In LINE SDK, parsing requires signature validation too usually.
        # If we separate them, we pass the signature in kwargs?
        signature = kwargs.get("signature")
        if not signature:
             raise ValueError("Signature required for parsing LINE events")

        return self.handler.parser.parse(payload, signature)

    def handle_webhook(self, payload: Any, headers: Dict[str, Any] = None) -> Any:
        """
        Handle incoming webhook request.
        """
        if not self.is_active:
            return

        # 1. Authenticate
        if not self.authenticate(payload, headers):
            logger.warning("LINE Webhook Authentication Failed.")
            return

        signature = headers.get('x-line-signature') or headers.get('X-Line-Signature')

        try:
            # 2. Receive Command (Parse)
            events = self.receive_command(payload, signature=signature)
            
            # 3. Process Events
            for event in events:
                user_id = event.source.user_id
                
                if isinstance(event, PostbackEvent):
                    # Handle Button Click
                    data_str = event.postback.data
                    parsed_data = {}
                    for pair in data_str.split('&'):
                        if '=' in pair:
                            k, v = pair.split('=', 1)
                            parsed_data[k] = v
                            
                    logger.info(f"LINE Postback: {parsed_data} from {user_id}")
                    
                    if hasattr(self, 'callback') and self.callback:
                        req_id = parsed_data.get('id')
                        action = parsed_data.get('action')
                        # Support simple 'action=etoro_link' without id
                        if action: 
                            self.callback(req_id or "global", action)

                elif isinstance(event, MessageEvent) and isinstance(event.message, TextMessageContent):
                    # Handle Text Message
                    text = event.message.text
                    logger.info(f"LINE Text: {text} from {user_id}")
                    
                    if hasattr(self, 'text_callback') and self.text_callback:
                        self.text_callback(user_id, text)
                        
        except InvalidSignatureError:
            logger.error("Invalid LINE signature.")
            raise ValueError("Invalid signature")
        except Exception as e:
            logger.error(f"LINE Webhook Error: {e}")

    def send_alert(self, user_id: str, title: str, content: str, actions: List[Dict[str, str]] = None, **kwargs) -> bool:
        """
        Sends a rich Flex Message Alert.
        发送 Flex Message 格式的豐富及時警報。
        kwargs:
            raise_error (bool): If True, raise exception on failure.
        """
        raise_error = kwargs.get("raise_error", False)

        # Use Base helper to resolve target_to
        target_to = self._resolve_target_id(user_id)

        if not self.is_active or not target_to:
            logger.info(f"[MOCK LINE] Sending User {target_to or user_id}: {title} - {content}")
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
                contents=FlexContainer.from_dict(bubble_json)
            )

            # Send
            request = PushMessageRequest(
                to=target_to,
                messages=[flex_message]
            )
            self.messaging_api.push_message(request)
            logger.info(f"LINE Alert sent to {target_to}")
            return True

        except Exception as e:
            logger.error(f"Failed to send LINE Flex Message: {e}")
            if raise_error:
                raise e
            return False

    def handle_webhook(self, payload: Any, headers: Dict[str, Any] = None):
        """
        Forward webhook to handler.
        Matching IChannelAdapter interface.
        """
        if not self.is_active:
            return
            
        signature = None
        if isinstance(headers, str):
             signature = headers
        elif isinstance(headers, dict):
             for k, v in headers.items():
                 if k.lower() == 'x-line-signature':
                     signature = v
                     break

        if not signature:
            logger.warning("LINE Webhook: Missing signature.")
            return

        try:
            body = payload # payload is the body string for LINE
            events = self.handler.parser.parse(body, signature)
            
            for event in events:
                user_id = event.source.user_id
                
                if isinstance(event, PostbackEvent):
                    # Handle Button Click
                    data_str = event.postback.data
                    parsed_data = {}
                    for pair in data_str.split('&'):
                        if '=' in pair:
                            k, v = pair.split('=', 1)
                            parsed_data[k] = v
                            
                    logger.info(f"LINE Postback: {parsed_data} from {user_id}")
                    
                    req_id = parsed_data.get('id')
                    action = parsed_data.get('action')
                    if req_id and action:
                        self._trigger_callback(req_id, action)

                elif isinstance(event, MessageEvent) and isinstance(event.message, TextMessageContent):
                    # Handle Text Message
                    text = event.message.text
                    logger.info(f"LINE Text: {text} from {user_id}")
                    self._trigger_text_callback(user_id, text)
                        
        except InvalidSignatureError:
            raise ValueError("Invalid signature")
        except Exception as e:
            logger.error(f"LINE Webhook Error: {e}")
