"""
End-to-End Verification: Phase 7 — Channel Gateway & DIKW.
端到端驗證：Phase 7 — 頻道閘道與 DIKW 演進。
"""

import asyncio
import logging
import sys
import os

# Ensure project root is in path
sys.path.append(os.getcwd())

# [Task 8.3] Ensure Local Database for Verification
os.environ["DB_URL"] = "sqlite:///./test_phase7_verify.db"

from src.infrastructure.messaging.channel_gateway import get_gateway
from src.services.notification_service import NotificationService
from src.infrastructure.memory.channel_memory_manager import ChannelMemoryManager
from src.services.settings_service import SettingsService
from src.data.database import init_db

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Phase7Verify")

async def verify_dikw_flow():
    user_id = "verify_user_p7"
    channel_id = "test_channel_123"
    channel_type = "telegram"
    
    print("\n--- [Phase 8.3] Initializing Local Test DB ---")
    # Cleanup old DB for fresh schema
    db_file = "./test_phase7_verify.db"
    if os.path.exists(db_file):
        os.remove(db_file)
        
    # Initialize SQLite for this test
    init_db(force=True)
    
    # Pre-configure settings for the user
    settings_svc = SettingsService(user_id=user_id)
    settings_svc.save_setting("AI_PROVIDER", "Google Gemini")
    settings_svc.save_setting("AI_MODEL_FAST", "gemini-1.5-flash")
    settings_svc.save_setting("API_KEY", os.getenv("API_KEY", "dummy_key"))

    # 1. Setup Support Services
    memory = ChannelMemoryManager()
    # Mock NotificationService - in real usage it would be configured with actual adapters
    notifier = NotificationService(adapters=[])
    
    gateway = get_gateway(notifier, memory)
    
    print("\n--- [Phase 7.1] Start conversation via Gateway ---")
    
    # Simulate a long conversation to trigger DIKW
    messages = [
        "Hello, I'm interested in AI stocks like NVDA.",
        "What's your take on AAPL's current valuation?",
        "I'm also watching MSFT for long term growth.",
        "Can you help me analyze Google's performance?",
        "I prefer high growth but with some dividends if possible.",
        "Let's look at META too.",
        "That's a lot of tech stocks. I'm actually a bit worried about concentration risk.",
        "Maybe I should add some healthcare like UNH?",
        "Actually, let's stick to tech for now until I have more cash.",
        "I have about $50,000 to invest total."
    ]
    
    # Trigger threshold (set to 20 in gateway, let's lower it for test or send more)
    gateway.message_count_threshold = 5 # Lower for verification
    
    for i, msg in enumerate(messages):
        print(f"User > {msg}")
        # In this test, we skip the actual Agent LLM call to save time/tokens if needed, 
        # but handle_inbound_message will call it.
        # We'll just call the internal parts if we want to mock.
        
        await gateway.handle_inbound_message(
            user_id=user_id,
            channel_type=channel_type,
            channel_id=channel_id,
            text=msg
        )
        print(f"Message {i+1} processed.\n")

    print("--- [Phase 7.2] Checking for DIKW Distillation ---")
    # Wait a moment for the background task to potentially finish (though it might fail without LLM keys)
    await asyncio.sleep(2)
    
    # Check Cognitive Memory for distilled insights
    from src.services.cognitive_memory_manager import CognitiveMemoryManager
    cmm = CognitiveMemoryManager(user_id=user_id)
    memories = cmm.get_recent_memories(limit=5, memory_type="distilled_conversation")
    
    if memories:
        print(f"✅ Success! Found {len(memories)} distilled items in cognitive memory.")
        print(f"Latest Summary: {memories[0]['content'].get('summary', 'No summary content')[:100]}...")
    else:
        print("❌ Failed to find distilled memory. Check logs for distillation errors.")

if __name__ == "__main__":
    asyncio.run(verify_dikw_flow())
