import sys
import os
import logging

# Add project root to path
sys.path.append(os.getcwd())

from src.services.market_data_service import MarketDataService

# Setup basic logging to console
logging.basicConfig(level=logging.INFO)

def test_providers():
    print(">>> Initializing MarketDataService...")
    service = MarketDataService()
    
    print("\n[Test 1] Fetch Current Prices (Failover Test)")
    # AAPL is a good test case
    tickers = ["AAPL", "GOOGL"]
    prices = service.get_current_prices(tickers)
    print(f"Prices fetched: {prices}")
    
    if prices:
        print("✅ Fetch Prices Passed")
    else:
        print("❌ Fetch Prices Failed (Check Internet or Rate Limits)")

    print("\n[Test 2] Fetch News")
    news = service.get_news("AAPL")
    print(f"News fetched ({len(news)}):")
    for n in news:
        print(f" - {n}")
        
    if news:
        print("✅ Fetch News Passed")
    else:
        print("⚠️ Fetch News Empty (Might be expected if no keys)")

    print("\n[Test 3] Fetch Financials (Fundamental)")
    info = service.get_financials("AAPL")
    print(f"Financials fetched: Market Cap={info.get('market_cap')}, PE={info.get('trailing_pe')}")
    
    if info:
        print("✅ Fetch Financials Passed")
    else:
        print("❌ Fetch Financials Failed")

    print("\n[Test 4] Market Context (OHLCV + Indicators)")
    context = service.get_market_context(["AAPL"])
    aapl_ctx = context.get("AAPL", {})
    price_data = aapl_ctx.get("price_data", {})
    indicators = aapl_ctx.get("indicators", {})
    
    print(f"OHLCV Data Points: {len(price_data.get('close', []))}")
    print(f"RSI: {indicators.get('rsi')}")
    
    if len(price_data.get('close', [])) > 0:
         print("✅ Market Context Passed")
    else:
         print("❌ Market Context Failed")

if __name__ == "__main__":
    test_providers()
