
import asyncio
import os
import sys

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.domain.interfaces import Message, LLMConfig
from src.infrastructure.llm.llm_gateway import LLMGatewayFactory
from src.services.settings_service import SettingsService
from src.repositories.settings_repository import AlchemySettingsRepository

async def test_llm_connectivity():
    user_id = "ac1b9257-eb9e-4531-8ee4-33fb2633cd38"
    
    # 1. Test NVIDIA NIM
    print("\n--- Testing NVIDIA NIM Connectivity ---")
    repo = AlchemySettingsRepository()
    nv_key = repo.get(user_id, "nvidia_api_key")
    
    if not nv_key:
        print("✗ NVIDIA API Key not found in DB.")
    else:
        print(f"✓ Found NVIDIA API Key (starts with {nv_key[:10]}...)")
        gateway = LLMGatewayFactory.create("nvidia")
        config = LLMConfig(
            provider="nvidia",
            model="nvidia/nemotron-3-super-120b-a12b", # One of the discovered models
            api_key=nv_key,
            timeout_seconds=30
        )
        try:
            response = await gateway.chat([Message(role="user", content="ping")], config)
            print(f"✓ NVIDIA NIM Response: {response[:50]}...")
        except Exception as e:
            print(f"✗ NVIDIA NIM Failed: {e}")

    # 2. Test Ollama
    print("\n--- Testing Ollama Connectivity ---")
    gateway = LLMGatewayFactory.create("ollama")
    config = LLMConfig(
        provider="ollama",
        model="qwen2.5:7b",
        base_url="http://shared_ollama:11434/v1",
        timeout_seconds=30
    )
    try:
        response = await gateway.chat([Message(role="user", content="ping")], config)
        print(f"✓ Ollama Response: {response[:50]}...")
    except Exception as e:
        print(f"✗ Ollama Failed: {e}")

    # 3. Test Telegram (Direct API probe)
    print("\n--- Testing Telegram Bot Connectivity ---")
    bot_token = repo.get(user_id, "notification_telegram_bot_token")
    if not bot_token:
        print("✗ Telegram Bot Token not found in DB.")
    else:
        import httpx
        url = f"https://api.telegram.org/bot{bot_token}/getMe"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    print(f"✓ Telegram Bot is active: {resp.json()['result']['username']}")
                else:
                    print(f"✗ Telegram Bot probe failed: {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"✗ Telegram Bot Network error: {e}")

if __name__ == "__main__":
    asyncio.run(test_llm_connectivity())
