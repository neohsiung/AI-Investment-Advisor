
import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from src.services.settings_service import SettingsService
from src.services.notification_service import NotificationService
from src.services.market_data_service import MarketDataService
from src.services.sentinel_service import SentinelService
from src.data.database import init_db

async def verify_telegram_routing():
    print("\n--- Verifying Telegram Routing ---")
    import uuid
    test_user_id = str(uuid.uuid4())
    print(f"Using Test User ID: {test_user_id}")
    
    # 1. Setup mock user settings
    settings_svc = SettingsService(user_id=test_user_id)
    settings_svc.save_setting("channel_telegram_enabled", "true")
    settings_svc.save_setting("channel_telegram_bot_token", "MOCK_TOKEN")
    settings_svc.save_setting("channel_telegram_chat_id", "MOCK_CHAT_ID")
    
    # 2. Test NotificationService creation for this user
    print(f"Loading settings for user {test_user_id}...")
    all_s = settings_svc.get_all_settings()
    print(f"Retrieved Settings Keys: {list(all_s.keys())}")
    print(f"Telegram Enabled: {all_s.get('channel_telegram_enabled')}")
    
    service = NotificationService.create_with_settings(settings_service=settings_svc, user_id=test_user_id)
    
    adapters = service.adapters
    has_telegram = any(type(a).__name__ == "TelegramAdapter" for a in adapters)
    print(f"User specific NotificationService has Telegram adapter: {has_telegram}")
    
    if has_telegram:
        tg_adapter = next(a for a in adapters if type(a).__name__ == "TelegramAdapter")
        print(f"Telegram Bot Token: {tg_adapter.bot_token}")
        print(f"Telegram Chat ID: {tg_adapter.chat_id}")
        
    # 3. Test SYSTEM settings (should NOT have telegram if not enabled globally)
    system_svc = SettingsService(user_id=None)
    system_service = NotificationService.create_with_settings(settings_service=system_svc)
    system_has_telegram = any(type(a).__name__ == "TelegramAdapter" for a in system_service.adapters)
    print(f"System specific NotificationService has Telegram adapter (default): {system_has_telegram}")

async def verify_price_sanity():
    print("\n--- Verifying Price Sanity & Logging ---")
    market_service = MarketDataService()
    
    # Trigger a real fetch for AAPL/TSLA and observe logs (which we've added)
    print("Fetching current prices for AAPL, TSLA...")
    prices = market_service.get_current_prices(["AAPL", "TSLA"])
    print(f"Current Prices: {prices}")
    
    # Trigger a history fetch
    print("Fetching history for AAPL...")
    history = market_service.get_ohlcv("AAPL", days=2)
    print(f"History (2 days): {history}")

async def check_auto_trading():
    print("\n--- Checking Auto-Trading Configuration ---")
    settings_svc = SettingsService()
    trading_enabled = settings_svc.get_setting("SYSTEM", "ai_trading_enabled")
    threshold = settings_svc.get_setting("SYSTEM", "auto_trade_threshold")
    print(f"Global AI Trading Enabled: {trading_enabled}")
    print(f"Global Auto-Trade Threshold: {threshold}")
    
    from src.services.automated_trading_service import AutomatedTradingService
    auto_service = AutomatedTradingService()
    # Check if it can initialize
    print("AutomatedTradingService initialized successfully.")

async def main():
    # init_db() # Ensure schema is up to date
    await verify_telegram_routing()
    await verify_price_sanity()
    await check_auto_trading()

if __name__ == "__main__":
    asyncio.run(main())
