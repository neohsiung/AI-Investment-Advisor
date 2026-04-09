import sys
import argparse
import logging
import os
import json

# Add project root to sys.path so we can import src
sys.path.append(os.getcwd())

from src.data.providers.fmp_provider import FMPProvider
from src.utils.logger import setup_logger

logger = setup_logger("fmp_cli")

def main():
    parser = argparse.ArgumentParser(description="Query Financial Modeling Prep data.")
    parser.add_argument("--action", required=True, choices=["sector_performance", "peers", "profile"], help="Data action")
    parser.add_argument("--ticker", help="Ticker symbol (for peers/profile)")
    
    args = parser.parse_args()
    
    try:
        provider = FMPProvider()
        
        if args.action == "sector_performance":
            data = provider.fetch_sector_performance()
            if not data:
                print("No data available.")
                return
            lines = ["**Sector Performance**:"]
            for item in data:
                sec = item.get('sector', 'Unknown')
                chg = item.get('changesPercentage', '0%')
                lines.append(f"- {sec}: {chg}")
            print("\n".join(lines))
            
        elif args.action == "peers":
            if not args.ticker:
                print("Error: --ticker is required for peers action.")
                sys.exit(1)
            peers = provider.fetch_stock_peers(args.ticker)
            if not peers:
                print(f"No peers found for {args.ticker}.")
            else:
                print(f"Peers for {args.ticker}: {', '.join(peers)}")
                
        elif args.action == "profile":
            if not args.ticker:
                print("Error: --ticker is required for profile action.")
                sys.exit(1)
            info = provider.fetch_info(args.ticker)
            if not info:
                 print(f"No info found for {args.ticker}.")
            else:
                print(f"**{args.ticker} Profile**:")
                print(f"- Sector: {info.get('sector')}")
                print(f"- Industry: {info.get('industry')}")
                print(f"- Market Cap: {info.get('market_cap')}")
                print(f"- CEO: {info.get('ceo')}")
            
    except Exception as e:
        logger.error(f"CLI fmp failed: {e}")
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
