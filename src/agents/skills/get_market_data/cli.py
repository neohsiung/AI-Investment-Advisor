import sys
import argparse
import logging
import os

# Add project root to sys.path so we can import src
sys.path.append(os.getcwd())

from src.services.market_data_service import MarketDataService
from src.utils.logger import setup_logger

logger = setup_logger("get_market_data_cli")

def main():
    parser = argparse.ArgumentParser(description="Fetch market data for a ticker.")
    parser.add_argument("--user_id", required=True, help="User ID context")
    parser.add_argument("--ticker", required=True, help="Ticker symbol (e.g., AAPL)")
    
    args = parser.parse_args()
    
    try:
        svc = MarketDataService(user_id=args.user_id)
        context = svc.get_market_context([args.ticker], enrich=False)
        
        if ticker_data := context.get(args.ticker):
            price_data = ticker_data.get("price_data", {})
            close_prices = price_data.get("close", [])
            price = close_prices[-1] if close_prices else "N/A"
            indicators = ticker_data.get("indicators", {})
            print(f"Price: {price}")
            print(f"Indicators: {indicators}")
        else:
            print(f"No data found for {args.ticker}.")
    except Exception as e:
        logger.error(f"CLI get_market_data failed: {e}")
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
