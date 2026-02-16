import logging
import datetime
from typing import Dict, Any, Tuple
from src.repositories.verification_repository import VerificationRepository
from src.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

class VerificationService:
    def __init__(self, repo: VerificationRepository = None, notification_service: NotificationService = None):
        self.repo = repo or VerificationRepository()
        self.notification_service = notification_service or NotificationService()

    def test_connectivity(self, user_id: str, channel: str) -> Tuple[bool, str]:
        """
        Sends a simple test message to check connectivity.
        Returns: (success, message)
        """
        try:
            results = self.notification_service.notify_all(
                title="Connectivity Test",
                content=f"✅ Transformation Complete. {channel} is online.",
                user_id=user_id,
                channels=[channel],
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

    def initiate_verification(self, user_id: str, channel: str, timeout_hours: int = 1) -> Tuple[bool, str, str]:
        """
        Starts a verification process for a specific channel.
        Sends a challenge message.
        Returns: (success, message, verification_id)
        """
        # 1. Create Challenge
        code = "OK"  # Keeping it simple as requested
        expires_at = datetime.datetime.now() + datetime.timedelta(hours=timeout_hours)
        
        # 2. Persist State
        verification_id = self.repo.create_verification(user_id, channel, code, expires_at)
        if not verification_id:
            return False, "Database error: Failed to create verification record.", None

        # 3. Send Challenge Message
        try:
            # Message Content
            content = (
                f"🛡️ Channel Verification Request\n"
                f"Please reply with '{code}' to verify this channel.\n"
                f"This request expires in {timeout_hours} hour(s)."
            )
            
            send_results = self.notification_service.notify_all(
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
                    success, msg = v
                    if not success:
                        self.repo.update_status(verification_id, "failed", msg)
                        return False, f"Failed to send message: {msg}", verification_id
            
            if not adapter_key_found:
                 self.repo.update_status(verification_id, "failed", "Adapter Not Found")
                 return False, f"Adapter for {channel} not found or not enabled.", verification_id

            return True, "Verification message sent. Waiting for reply.", verification_id

        except Exception as e:
            self.repo.update_status(verification_id, "failed", str(e))
            logger.error(f"Verification initiation failed: {e}")
            return False, f"System error: {e}", verification_id

    def verify_reply(self, user_id: str, content: str, channel: str) -> bool:
        """
        Called when a message is received from a user (e.g. via Webhook).
        Matches against pending verifications.
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
            self.notification_service.notify_all(
                title="Verification Successful",
                content=f"✅ {channel} Channel Verified Successfully!",
                user_id=user_id,
                channels=[channel]
            )
            return True
        else:
            # Optional: Log failure or ignore non-matching messages
            return False

    def verify_any_reply(self, user_id: str, content: str) -> bool:
        """
        Checks if the content matches ANY pending verification for this user.
        Used when the source channel is not explicitly passed or to capture cross-channel verification.
        """
        content = content.strip().upper()
        pending = self.repo.get_any_pending_verification(user_id)
        
        if not pending:
            return False
            
        expected_code = pending['code'].upper()
        channel = pending['channel']
        
        if content == expected_code:
            self.repo.update_status(pending['id'], "verified")
            
            # Send Success Confirmation
            self.notification_service.notify_all(
                title="Verification Successful",
                content=f"✅ {channel} Channel Verified Successfully!",
                user_id=user_id,
                channels=[channel]
            )
            return True
        return False

    def get_status(self, verification_id: str) -> Dict[str, Any]:
        return self.repo.get_verification_by_id(verification_id)
