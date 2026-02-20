import argparse
import sys
import os
import json

# Ensure project path is accessible
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.services.settings_service import SettingsService
from src.services.supply_chain_service import SupplyChainService

def update_supply_chain_ticker(ticker, bottlenecks, suppliers):
    settings = SettingsService()
    sc = SupplyChainService(settings_service=settings)
    
    graph = sc.knowledge_graph
    
    graph[ticker] = {
        "bottlenecks": [b.strip() for b in bottlenecks.split(',')] if bottlenecks else [],
        "suppliers": [s.strip() for s in suppliers.split(',')] if suppliers else []
    }
    
    if sc.update_graph(graph):
        print(f"Successfully updated Supply Chain Knowledge graph for {ticker}.")
    else:
        print(f"Failed to update knowledge graph for {ticker}.")

def update_dynamic_tickers(key, tickers):
    settings = SettingsService()
    ticker_list = [t.strip().upper() for t in tickers.split(',')]
    success, msg = settings.save_setting(key, json.dumps(ticker_list))
    if success:
        print(f"Successfully updated {key} tracking list to: {ticker_list}")
    else:
        print(f"Failed to update {key}: {msg}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Update Dynamic Settings for AI Investment Advisor")
    
    subparsers = parser.add_subparsers(dest="command")
    
    # Update Supply Chain Graph
    sc_parser = subparsers.add_parser("supply", help="Update Supply Chain Knowledge Graph")
    sc_parser.add_argument("--ticker", required=True, help="Ticker to update (e.g. NVDA)")
    sc_parser.add_argument("--bottlenecks", required=False, default="", help="Comma separated bottlenecks (e.g. 'CoWoS,HBM3e')")
    sc_parser.add_argument("--suppliers", required=False, default="", help="Comma separated suppliers (e.g. 'TSM,MU')")
    
    # Update AI Energy Tickers
    energy_parser = subparsers.add_parser("energy", help="Update AI Energy Moat Tracking List")
    energy_parser.add_argument("--tickers", required=True, help="Comma separated tickers (e.g. 'CEG,VST,MSFT')")
    
    # Update Physical AI Tickers
    physical_parser = subparsers.add_parser("physical", help="Update Physical AI Tracking List")
    physical_parser.add_argument("--tickers", required=True, help="Comma separated tickers (e.g. 'TSLA,UBER')")
    
    args = parser.parse_args()
    
    if args.command == "supply":
        update_supply_chain_ticker(args.ticker, args.bottlenecks, args.suppliers)
    elif args.command == "energy":
        update_dynamic_tickers("ai_energy_tickers", args.tickers)
    elif args.command == "physical":
        update_dynamic_tickers("physical_ai_tickers", args.tickers)
    else:
        parser.print_help()
