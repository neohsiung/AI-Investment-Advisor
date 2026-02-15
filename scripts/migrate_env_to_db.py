import os
from dotenv import load_dotenv
from src.services.settings_service import SettingsService
from src.data.database import get_db_connection
from sqlalchemy import text

def migrate():
    load_dotenv()
    user_id = "supermfb@gmail.com" # Primary email used in UI
    service = SettingsService(user_id=user_id)
    
    # Mapping: .env key -> DB key
    mapping = {
        "POLYGON_API_KEY": "source_polygon_api_key",
        "FMP_API_KEY": "source_fmp_api_key",
        "FRED_API_KEY": "source_fred_api_key",
        "TAVILY_API_KEY": "source_tavily_api_key", # Adding Tavily even if not in Matrix yet
        "FINNHUB_API_KEY": "source_finnhub_api_key",
        "TIINGO_API_KEY": "source_tiingo_api_key",
        "NEWS_API_KEY": "source_news_api_key",
        "CRYPTOPANIC_API_KEY": "source_cryptopanic_api_key",
        "WHALE_ALERT_API_KEY": "source_whale_alert_api_key",
        "GLASSNODE_API_KEY": "source_glassnode_api_key",
        "ALPHA_VANTAGE_API_KEY": "source_alpha_vantage_api_key",
    }
    
    # Enable sources if they have a key
    to_save = {}
    for env_key, db_key in mapping.items():
        val = os.getenv(env_key)
        if val:
            to_save[db_key] = val
            # Extract source_id from db_key (source_<sid>_api_key)
            sid = db_key.replace("source_", "").replace("_api_key", "")
            to_save[f"source_{sid}_enabled"] = "true"
            print(f"Migrated {env_key} -> {db_key} (and enabled)")

    if to_save:
        service.save_settings_bulk(to_save)
        print(f"Successfully migrated {len(to_save)} settings to DB for {user_id}")
    else:
        print("No settings to migrate.")

if __name__ == "__main__":
    migrate()
