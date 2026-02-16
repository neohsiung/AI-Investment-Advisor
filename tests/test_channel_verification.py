import unittest
from unittest.mock import MagicMock, patch
import logging
from datetime import datetime, timedelta

# Adjust path
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.services.verification_service import VerificationService
from src.repositories.verification_repository import VerificationRepository
from src.services.notification_service import NotificationService

class TestChannelVerification(unittest.TestCase):
    def setUp(self):
        self.mock_repo = MagicMock(spec=VerificationRepository)
        self.mock_notification = MagicMock(spec=NotificationService)
        self.service = VerificationService(repo=self.mock_repo, notification_service=self.mock_notification)

    def test_connectivity_success(self):
        # Mock notify_all returning success for LINE
        self.mock_notification.notify_all.return_value = {"LineBotAdapter": (True, "OK")}
        
        success, msg = self.service.test_connectivity("user123", "line")
        
        self.assertTrue(success)
        self.assertEqual(msg, "OK")
        self.mock_notification.notify_all.assert_called_once()
        args, kwargs = self.mock_notification.notify_all.call_args
        self.assertTrue(kwargs['capture_error'])

    def test_connectivity_failure(self):
        # Mock notify_all returning failure
        self.mock_notification.notify_all.return_value = {"LineBotAdapter": (False, "Invalid Token")}
        
        success, msg = self.service.test_connectivity("user123", "line")
        
        self.assertFalse(success)
        self.assertIn("Invalid Token", msg)

    def test_connectivity_adapter_not_found(self):
         self.mock_notification.notify_all.return_value = {"EmailAdapter": (True, "OK")}
         
         success, msg = self.service.test_connectivity("user123", "line")
         self.assertFalse(success)
         self.assertIn("not found", msg)

    def test_initiate_verification_flow(self):
        self.mock_repo.create_verification.return_value = "verif_123"
        self.mock_notification.notify_all.return_value = {"LineBotAdapter": (True, "OK")}
        
        success, msg, vid = self.service.initiate_verification("user_1", "line", timeout_hours=2)
        
        self.assertTrue(success)
        self.assertEqual(vid, "verif_123")
        self.mock_repo.create_verification.assert_called_once()

    def test_verify_reply_success(self):
        # Mock pending verification
        self.mock_repo.get_pending_verification.return_value = {
            "id": "v1", "user_id": "u1", "channel": "line", "code": "OK"
        }
        
        # Act
        result = self.service.verify_reply("u1", "ok", "line") # Case insensitive match
        
        self.assertTrue(result)
        self.mock_repo.update_status.assert_called_with("v1", "verified")
        self.mock_notification.notify_all.assert_called() # Confirmation sent

    def test_verify_reply_fail(self):
        self.mock_repo.get_pending_verification.return_value = {
            "id": "v1", "user_id": "u1", "channel": "line", "code": "OK"
        }
        
        result = self.service.verify_reply("u1", "WRONG_CODE", "line")
        
        self.assertFalse(result)
        self.mock_repo.update_status.assert_not_called()

    def test_verify_any_reply_success(self):
        self.mock_repo.get_any_pending_verification.return_value = {
            "id": "v1", "user_id": "u1", "channel": "line", "code": "OK"
        }
        
        result = self.service.verify_any_reply("u1", "OK")
        
        self.assertTrue(result)
        self.mock_repo.update_status.assert_called_with("v1", "verified")

if __name__ == '__main__':
    logging.basicConfig(level=logging.CRITICAL)
    unittest.main()
