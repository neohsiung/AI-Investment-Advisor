import asyncio
import logging
import sys
import os

# Ensure src is in path
sys.path.append(os.getcwd())

from unittest.mock import MagicMock, patch
from src.services.sentinel_service import SentinelService

# Configure Logging to stdout
logging.basicConfig(level=logging.INFO, format='%(name)s - %(levelname)s - %(message)s')

async def run_simulation():
    print(">>> Starting Sentinel Simulation (Adaptive Thresholds & RAG)...")
    
    # Mock Market Data Service
    with patch('src.services.sentinel_service.MarketDataService') as MockMarketService:
        # Instance Mock
        market_instance = MockMarketService.return_value
        
        # 1. Mock VIX History for Adaptive Threshold (MA=20, Sig=2, Threshold=23)
        # We need 60 mock closes. Let's make average 20, last one 28 (Spike!)
        mock_closes = [20.0] * 59 + [28.0] 
        market_instance.get_ohlcv.return_value = {"close": mock_closes}
        
        # Mock Council Service dependencies
        with patch('src.services.council_service.AgentFactory') as MockFactory:
            
            # Setup Mock Agent
            mock_agent = MagicMock()
            mock_agent.run.return_value = "I see the VIX spike. RAG told me to be cautious."
            mock_agent.name = "MockBot"
            MockFactory.create_momentum_agent.return_value = mock_agent
            MockFactory.create_fundamental_agent.return_value = mock_agent
            MockFactory.create_risk_agent.return_value = mock_agent
            MockFactory.create_sentiment_agent.return_value = mock_agent
            MockFactory.create_macro_agent.return_value = mock_agent
            MockFactory.create_cio_agent.return_value = mock_agent
            MockFactory.create_agent.return_value = mock_agent
            
            # Mock VectorRepo in Council
            with patch('src.services.council_service.VectorRepository') as MockRepo:
                # Mock LineAdapter to verify call
                with patch('src.services.sentinel_service.LineBotAdapter') as MockLineAdapter:
                    
                    # Instantiate Sentinel
                    sentinel = SentinelService()
                    
                    # RUN TICK
                    await sentinel.process_tick()
                    
                    # VERIFY
                    print("\n>>> Verification Results:")
                    
                    # Check VIX History fetch
                    if market_instance.get_ohlcv.called:
                        print("✅ Step 1: Sentinel fetched VIX history for Adaptive Logic.")
                    else:
                        print("❌ Step 1 Failed: Sentinel did not fetch history.")
                    
                    # Check Council Activation
                    if MockFactory.create_risk_agent.called:
                        print("✅ Step 2: Council Activated (Adaptive Alert Triggered).")
                    else:
                        print("❌ Step 2 Failed: Council not activated.")
                        
                    # Check RAG
                    if mock_agent.run.called:
                        print("✅ Step 3: Agents debated (RAG injection placeholder passed).")
                        
                    # Check LINE Alert
                    if sentinel.line_adapter.send_flex_alert.called:
                         print("✅ Step 4: LINE Alert Sent via Adapter.")
                    else:
                         print("❌ Step 4 Failed: LINE Alert NOT sent.")
                
    print("\n>>> Simulation Complete.")

if __name__ == "__main__":
    asyncio.run(run_simulation())
