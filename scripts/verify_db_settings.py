import os
from src.services.market_data_service import MarketDataService
from src.services.settings_service import SettingsService

def verify():
    user_id = "supermfb@gmail.com"
    service = MarketDataService(user_id=user_id)
    
    print(f"--- Verification for {user_id} ---")
    
    # Check Polygon
    polygon_key = service.polygon.api_key
    print(f"Polygon Key in Service: {polygon_key[:5]}...{polygon_key[-5:] if polygon_key else ''}")
    
    # Check FMP
    fmp_key = service.fmp.api_key
    print(f"FMP Key in Service: {fmp_key[:5]}...{fmp_key[-5:] if fmp_key else ''}")
    
    # Check FRED
    fred_key = service.fred.api_key
    print(f"FRED Key in Service: {fred_key[:5]}...{fred_key[-5:] if fred_key else ''}")
    
    # Check Search
    search_key = service.search_service.settings_service.get_setting("source_tavily_api_key")
    print(f"Tavily Key resolved: {search_key[:5]}...{search_key[-5:] if search_key else ''}")

    # Functional Test (Light)
    try:
        # Just check if we can get a price without crashing, using the key
        price = service.get_current_prices(["AAPL"])
        print(f"Price Fetch Test: {price}")
    except Exception as e:
        print(f"Price Fetch Test Failed: {e}")

if __name__ == "__main__":
    verify()
