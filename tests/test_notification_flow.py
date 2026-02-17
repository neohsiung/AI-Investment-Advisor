from unittest.mock import MagicMock, AsyncMock, patch
import unittest
import asyncio
from datetime import datetime

# Adjust path
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.services.sentinel_service import SentinelService
from src.services.council_service import CouncilService
from src.services.settings_service import SettingsService
from src.services.notification_service import NotificationService

class TestSentinelNotification(unittest.TestCase):
    def setUp(self):
        self.mock_repo_patcher = patch('src.services.sentinel_service.SentinelRepository')
        self.mock_repo_cls = self.mock_repo_patcher.start()
        self.mock_repo = self.mock_repo_cls.return_value
        
        self.mock_settings = MagicMock(spec=SettingsService)
        self.mock_settings.user_id = "test_user_123"
        self.mock_council = MagicMock(spec=CouncilService)
        self.mock_council.start_session = AsyncMock(return_value={"consensus": "Hold Position"})
        self.mock_notification = MagicMock(spec=NotificationService)
        
        # Patch dependencies
        self.sentinel = SentinelService(
            settings_service=self.mock_settings,
            council_service=self.mock_council,
            notification_service=self.mock_notification
        )
        # self.sentinel.council_service = self.mock_council # Already passed in init
         # self.sentinel.notification_service = self.mock_notification
        
        self.mock_repo.is_duplicate_alert.return_value = False

    def tearDown(self):
        self.mock_repo_patcher.stop()

    def test_alert_flow_and_format(self):
        triggers = ["🔴 VIX Spike: 45.0 > 30.0", "🏦 Fed Funds Rate Up"]
        
        # execution
        asyncio.run(self.sentinel._do_send_alert(triggers, source="TestSentinel"))
        
        # Verify CouncilService called with user_id
        self.mock_council.start_session.assert_called_once()
        args, kwargs = self.mock_council.start_session.call_args
        self.assertEqual(kwargs['user_id'], "test_user_123")
        
        # Verify Notification Format
        self.mock_notification.notify_all.assert_called_once()
        call_args = self.mock_notification.notify_all.call_args[1]
        content = call_args['content']
        
        print("\n--- Generated Notification Content ---")
        print(content)
        print("--------------------------------------\n")
        
        self.assertIn("### 🛡️ Sentinel Event Loop", content)
        self.assertIn("1. 🔴 VIX Spike: 45.0 > 30.0", content)
        self.assertIn("2. 🏦 Fed Funds Rate Up", content)

if __name__ == "__main__":
    unittest.main()
