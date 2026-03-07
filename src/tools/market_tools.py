import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
from src.tools.mcp_server import McpTool, McpServer
from src.services.market_data_service import MarketDataService

class MarketTools:
    def __init__(self, market_service: MarketDataService):
        self.service = market_service

    def get_tools(self) -> List[McpTool]:
        return [
            McpTool(
                name="get_current_price",
                description="Get current price for a ticker or list of tickers.",
                func=self._get_price_wrapper
            ),
            McpTool(
                name="get_news",
                description="Get recent news for a specific ticker.",
                func=self.service.get_news
            ),
            McpTool(
                name="get_financials",
                description="Get fundamental financial data for a ticker.",
                func=self.service.get_financials
            ),
             McpTool(
                name="get_technical_indicators",
                description="Get technical indicators (RSI, MACD, SMA) for a ticker.",
                func=self.service.get_technical_indicators
            )
        ]

    def _get_price_wrapper(self, ticker: str):
        # Wrapper to handle single ticker string vs list
        # Agents might pass "AAPL" or ["AAPL"]
        if isinstance(ticker, str):
            tickers = [ticker]
        else:
            tickers = ticker
            
        return self.service.get_current_prices(tickers)

def create_market_server(market_service=None) -> McpServer:
    server = McpServer(name="MarketData")
    service = market_service or MarketDataService()
    market_tools = MarketTools(service)
    
    for tool in market_tools.get_tools():
        server.register_tool(tool)
        
    return server
