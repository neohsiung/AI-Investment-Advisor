import asyncio
import logging
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timedelta

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def verify_buffer():
    print("--- Sentinel Buffer Verification ---")
    
    # 1. Mock Dependencies
    mock_repo = MagicMock()
    mock_repo.is_duplicate_alert.return_value = False # Always allow
    mock_council = AsyncMock()
    mock_council.start_session.return_value = {"consensus": "HOLD"}
    mock_notify = MagicMock()
    
    # 2. Initialize Service (Partial Mock)
    from src.services.sentinel_service import SentinelService
    service = SentinelService(
        council_service=mock_council, 
        notification_service=mock_notify
    )
    service.repo = mock_repo # Inject mock repo
    
    # Override _do_send_alert to track calls
    service._do_send_alert = AsyncMock()
    
    # Test 1: Normal Trigger (Should Buffer)
    print("\nTest 1: Normal Trigger (Should Buffer)")
    await service._escalate(["Warning: Low Volatility"])
    
    if len(service._trigger_buffer) == 1:
        print("✅ Buffer has 1 item.")
    else:
        print(f"❌ Buffer failed: {len(service._trigger_buffer)}")
        
    if service._do_send_alert.call_count == 0:
        print("✅ Alert NOT sent immediately.")
    else:
        print("❌ Alert sent immediately!")
        
    # Test 2: Add more triggers (Should Aggregate)
    print("\nTest 2: Add second trigger")
    await service._escalate(["Warning: News Event"])
    
    if len(service._trigger_buffer) == 2:
        print("✅ Buffer has 2 items.")
    else:
        print(f"❌ Buffer count mismatch: {len(service._trigger_buffer)}")

    # Test 3: Force Flush (Simulate Timeout)
    print("\nTest 3: Force Flush")
    await service._flush_buffer(force=True)
    
    if service._do_send_alert.call_count == 1:
        print("✅ Alert sent after flush.")
        args = service._do_send_alert.call_args[0]
        triggers = args[0]
        print(f"   Payload: {triggers}")
        if len(triggers) == 2:
             print("✅ Payload contains aggregated triggers.")
        else:
             print("❌ Payload missing items.")
    else:
        print(f"❌ Alert Not sent? Count: {service._do_send_alert.call_count}")
        
    # Reset
    service._do_send_alert.reset_mock()
    service._trigger_buffer = []
    
    # Test 4: Critical Trigger (Should Flush Immediately)
    print("\nTest 4: Critical Trigger")
    await service._escalate(["🔴 CRITICAL VIX SPIKE"])
    
    if service._do_send_alert.call_count == 1:
        print("✅ Critical alert sent immediately.")
        triggers = service._do_send_alert.call_args[0][0]
        if "🔴 CRITICAL VIX SPIKE" in triggers:
             print("✅ Payload correct.")
    else:
        print(f"❌ Critical alert buffer failed. Count: {service._do_send_alert.call_count}")

if __name__ == "__main__":
    asyncio.run(verify_buffer())
