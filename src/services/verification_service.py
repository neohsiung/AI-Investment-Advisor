import logging
import datetime
from typing import Dict, Any, Tuple, Optional
from src.repositories.verification_repository import VerificationRepository
from src.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

class VerificationService:
    """
    Service for handling multi-channel connectivity tests and identity verification.
    驗證服務：負責處理多通路連線性測試與身份驗證。
    """
    def __init__(self, repo: Optional[VerificationRepository] = None, notification_service: Optional[NotificationService] = None, settings_service: Any = None, user_id: str = None) -> None:
        """
        Initialize the verification service.
        初始化驗證服務。
        """
        self.user_id = user_id
        self.repo = repo or VerificationRepository()
        self.notification_service = notification_service or NotificationService.create_with_settings(settings_service)

    async def test_connectivity(self, user_id: str, channel: str) -> Tuple[bool, str]:
        """
        Send a test notification to verify channel connectivity asynchronously.
        發送測試通知以驗證管道連線性（非同步）。
        
        Returns:
            Tuple[bool, str]: (Success status, descriptive message)
            Tuple[bool, str]: (成功狀態, 描述性訊息)
        """
        try:
            results = await self.notification_service.notify_all(
                title="Connectivity Test",
                content=f"✅ Transformation Complete. {channel} is online.",
                user_id=user_id,
                channels=[channel],
                category="system",
                capture_error=True
            )
            
            # Find the result for the requested channel
            for k, v in results.items():
                if channel.lower() in k.lower():
                    # v is (success, msg)
                    return v
            
            return False, f"Channel adapter '{channel}' not found or disabled."
        except Exception as e:
            return False, str(e)

    async def initiate_verification(self, user_id: str, channel: str, timeout_hours: int = 1, channel_user_id: str = None) -> Tuple[bool, str, str]:
        """
        Initiate a channel verification process by sending a challenge code asynchronously.
        透過發送挑戰碼啟動管道驗證程序（非同步）。
        
        Returns:
            Tuple[bool, str, str]: (Success status, response message, verification_id)
            Tuple[bool, str, str]: (成功狀態, 回應訊息, 驗證 ID)
        """
        # 1. Create Challenge
        code = "OK"  
        # Use UTC for consistency
        now_utc = datetime.datetime.utcnow()
        expires_at = now_utc + datetime.timedelta(hours=timeout_hours)
        
        # 2. Send Challenge Message
        try:
            content = (
                f"🛡️ Channel Verification Request\n"
                f"Please reply with '{code}' to verify this channel.\n"
                f"This request expires in {timeout_hours} hour(s)."
            )
            
            send_results = await self.notification_service.notify_all(
                title="Channel Verification",
                content=content,
                user_id=user_id,
                channels=[channel],
                capture_error=True
            )
            
            # Check if specific channel succeeded
            adapter_key_found = False
            for k, v in send_results.items():
                if channel.lower() in k.lower():
                    adapter_key_found = True
                    success, msg = v[:2]
                    if not success:
                        return False, f"Failed to send message: {msg}", None
            
            if not adapter_key_found:
                 return False, f"Adapter for {channel} not found or not enabled.", None

            # 3. Resolve channel_user_id (Fallback if not provided)
            if not channel_user_id and self.notification_service.settings_service:
                settings = self.notification_service.settings_service.get_all_settings()
                key_map = {
                    "line": "channel_line_user_id",
                    "telegram": "channel_telegram_chat_id",
                    "slack": "channel_slack_channel_id",
                    "messenger": "channel_messenger_user_id"
                }
                key = key_map.get(channel.lower())
                if key:
                    channel_user_id = settings.get(key)

            # 4. Persist State
            verification_id = self.repo.create_verification(user_id, channel, code, expires_at, channel_user_id=channel_user_id)
            if not verification_id:
                return False, "Database error: Failed to create verification record.", None

            return True, "Verification message sent. Waiting for reply.", verification_id

        except Exception as e:
            logger.error(f"Verification initiation failed: {e}")
            return False, f"System error: {e}", None

    async def verify_reply(self, user_id: str, content: str, channel: str) -> bool:
        """
        Verify a user's reply against a pending verification challenge asynchronously.
        """
        # Normalize content
        content = content.strip().upper()
        
        pending = self.repo.get_pending_verification(user_id, channel)
        if not pending:
            return False # No pending verification
            
        expected_code = pending['code'].upper()
        
        if content == expected_code:
            self.repo.update_status(pending['id'], "verified")
            
            # Send Success Confirmation
            await self.notification_service.notify_all(
                title="Verification Successful",
                content=f"✅ {channel} Channel Verified Successfully!",
                user_id=user_id,
                channels=[channel]
            )
            return True
        else:
            # Optional: Log failure or ignore non-matching messages
            return False

    async def verify_any_reply(self, user_id: str, content: str) -> bool:
        """
        Match a user reply against ANY pending verification challenge for that user asynchronously.
        """
        content = content.strip().upper()
        # 1. Try finding by user_id (could be email or raw channel ID)
        pending = self.repo.get_any_pending_verification(user_id)
        
        if not pending:
            return False
            
        expected_code = pending['code'].upper()
        channel = pending['channel']
        
        if content == expected_code:
            self.repo.update_status(pending['id'], "verified")
            
            # Send Success Confirmation
            logger.info(f"Verification Success for {user_id} on {channel}. Sending feedback.")
            success = await self.notification_service.notify_all(
                title="Verification Successful",
                content=f"✅ {channel.upper()} Channel Verified Successfully!",
                user_id=user_id,
                channels=[channel]
            )
            if not success:
                logger.warning(f"Failed to send verification confirmation to {user_id} via {channel}")
            return True
            
        logger.debug(f"Verification mismatch for {user_id}: expected {expected_code}, got {content}")
        return False

    def get_status(self, verification_id: str) -> Dict[str, Any]:
        """
        Get the current status of a verification request.
        獲取驗證請求的目前狀態。
        """
        return self.repo.get_verification_by_id(verification_id)
