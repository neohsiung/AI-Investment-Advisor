import asyncio
import logging
import datetime
from sqlalchemy import text
from src.data.sentinel_repository import SentinelRepository
from src.services.verification_service import VerificationService
from src.repositories.verification_repository import VerificationRepository

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def verify_stabilization():
    print("\n--- Testing UTC Timestamp Consistency ---")
    repo = SentinelRepository()
    
    # 1. Clean up old logs for test signal
    with repo.engine.connect() as conn:
        conn.execute(text("DELETE FROM event_logs WHERE source = 'Sentinel' AND json_extract(metadata, '$.signal_id') = 'test_signal'"))
        conn.commit()

    # 2. Log an alert
    print("Logging alert with current UTC...")
    repo.log_alert("Test Title", "Test Content", metadata={"signal_id": "test_signal", "value": 10.0})
    
    # Check if it exists in next 24h
    is_dup = repo.is_duplicate_alert("Test Title", "Test Content", hours=24, signal_id="test_signal")
    print(f"Duplicate Check: {is_dup}")
    assert is_dup is True, "Suppression failed! Timestamp probably mismatch."

    print("\n--- Testing Early Identity Mapping ---")
    v_repo = VerificationRepository()
    v_service = VerificationService(repo=v_repo)
    
    user_email = "test_user@example.com"
    channel = "line"
    channel_id = "U_TEST_123"
    
    # 3. Initiate verification with early mapping
    print(f"Initiating verification for {user_email} on {channel} with ID {channel_id}...")
    success, msg, vid = v_service.initiate_verification(user_email, channel, channel_user_id=channel_id)
    assert success is True
    
    # 4. Verify inbound reply matching by channel_id (Catch-22 solve)
    print(f"Testing inbound 'OK' from raw channel ID {channel_id}...")
    # This simulates what InteractionService does
    result = v_service.verify_any_reply(channel_id, "OK")
    print(f"Match Result: {result}")
    assert result is True, "Catch-22 logic failed! Could not match by channel_id."

    # 5. Check if status updated
    status_data = v_service.get_status(vid)
    print(f"Final Status: {status_data['status']}")
    assert status_data['status'] == 'verified'

if __name__ == "__main__":
    asyncio.run(verify_stabilization())
