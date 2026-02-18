import asyncio
import logging
from src.services.notification_service import NotificationService
from src.services.settings_service import SettingsService
from src.repositories.settings_repository import SqliteSettingsRepository
from src.data.database import get_db_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def run_diagnostic():
    user_id = '90693c07-6177-42df-97d9-915f3ce7c573'
    logger.info(f"Starting notification diagnostic for user: {user_id}")
    
    # Initialize settings service
    settings_service = SettingsService(user_id=user_id)
    
    # Create notification service
    noti_service = NotificationService.create_with_settings(settings_service, user_id=user_id)
    
    logger.info(f"Loaded {len(noti_service.adapters)} adapters.")
    for adapter in noti_service.adapters:
        adapter_type = adapter.__class__.__name__
        logger.info(f"Testing adapter: {adapter_type}")
        
        try:
            # We use notify_all but filter for this specific adapter to get clear results
            results = await noti_service.notify_all(
                title="Diagnostic Test",
                content="This is a test notification from the diagnostic tool.",
                user_id=user_id,
                channels=[adapter_type.lower().replace('adapter', '').replace('bot', '')],
                capture_error=True
            )
            logger.info(f"Results for {adapter_type}: {results}")
        except Exception as e:
            logger.error(f"Failed to test {adapter_type}: {e}")

if __name__ == "__main__":
    asyncio.run(run_diagnostic())
