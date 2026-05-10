import asyncio
import os
import sys
import httpx
import json

# Add src to path
sys.path.append(os.getcwd())

from src.services.settings_service import SettingsService

async def setup_webhook(public_url: str, user_id: str = None):
    """
    Sets the Telegram bot webhook to the public URL.
    """
    if not user_id:
        # Find first user with telegram enabled
        from src.repositories.user_repository import AlchemyUserRepository
        user_repo = AlchemyUserRepository()
        users = user_repo.get_all_active_users()
        if not users:
            print("❌ Error: No active users found in database.")
            return False
        user_id = users[0]

    ss = SettingsService(user_id=user_id)
    bot_token = ss.get_setting("channel_telegram_bot_token")
    
    if not bot_token:
        print(f"❌ Error: No Telegram bot token found for user {user_id}")
        return False

    webhook_url = f"{public_url.rstrip('/')}/webhook/telegram"
    print(f"🌐 Setting Telegram webhook to: {webhook_url}")
    
    api_url = f"https://api.telegram.org/bot{bot_token}/setWebhook"
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(api_url, json={"url": webhook_url})
        result = resp.json()
        
        if result.get("ok"):
            print(f"✅ Success: {result.get('description')}")
            return True
        else:
            print(f"❌ Failed: {result.get('description')}")
            return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python src/setup_telegram_webhook.py <PUBLIC_URL>")
        sys.exit(1)
        
    public_url = sys.argv[1]
    asyncio.run(setup_webhook(public_url))
