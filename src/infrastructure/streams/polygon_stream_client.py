import os
import asyncio
import json
import logging
import websockets
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, List, Callable, Dict, Any
from src.utils.logger import setup_logger
from src.services.settings_service import SettingsService

class PolygonStreamClient:
    """
    WebSocket client for Polygon.io real-time market data.
    Polygon.io 即時市場數據 WebSocket 客戶端。
    """
    def __init__(self, api_key: str = None, user_id: str = "system"):
        self.logger = setup_logger("PolygonStreamClient")
        self.user_id = user_id
        
        # Resolve Settings
        self.settings_service = SettingsService(user_id=user_id)
        settings = self.settings_service.get_all_settings()
        self.api_key = api_key or settings.get("source_polygon_api_key") or os.getenv("POLYGON_API_KEY")
        
        self.ws_url = "wss://delayed.polygon.io/stocks" # Use delayed for free tier unless specified
        self.uri = f"{self.ws_url}"
        
        self.running = False
        self.callbacks: List[Callable] = []

    def add_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Register a callback for incoming events."""
        self.callbacks.append(callback)

    async def connect(self, tickers: List[str] = ["*"]):
        """
        Connect to Polygon WebSocket and subscribe to tickers.
        連接至 Polygon WebSocket 並訂閱標的。
        """
        if not self.api_key:
            self.logger.error("No API key for Polygon WebSocket. Aborting.")
            return

        self.running = True
        while self.running:
            try:
                self.logger.info(f"Connecting to Polygon WebSocket: {self.uri}")
                async with websockets.connect(self.uri) as websocket:
                    # 1. Authentication
                    auth_msg = {"action": "auth", "params": self.api_key}
                    await websocket.send(json.dumps(auth_msg))
                    
                    # 2. Subscribe (Trades and Aggregates)
                    # For demo/default: Subscribe to all trades if tickers is ["*"]
                    sub_params = []
                    for t in tickers:
                        sub_params.append(f"T.{t}") # Trades
                        sub_params.append(f"A.{t}") # Second aggregates
                        
                    sub_msg = {"action": "subscribe", "params": ",".join(sub_params)}
                    await websocket.send(json.dumps(sub_msg))
                    self.logger.info(f"Subscribed to: {sub_params}")

                    # 3. Listen loop
                    async for message in websocket:
                        data = json.loads(message)
                        for event in data:
                            # Bridge to callbacks
                            for cb in self.callbacks:
                                if asyncio.iscoroutinefunction(cb):
                                    await cb(event)
                                else:
                                    cb(event)
                                    
            except websockets.exceptions.ConnectionClosed:
                self.logger.warning("WebSocket connection closed. Reconnecting in 5s...")
                await asyncio.sleep(5)
            except Exception as e:
                self.logger.error(f"WebSocket error: {e}. Retrying in 10s...")
                await asyncio.sleep(10)

    def stop(self):
        """Stop the streaming client."""
        self.running = False
