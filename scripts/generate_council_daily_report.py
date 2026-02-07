import asyncio
import logging
import sys
import os
from unittest.mock import MagicMock, patch

# Ensure src is in path
sys.path.append(os.getcwd())

from src.services.council_service import CouncilService

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(name)s - %(message)s')
logger = logging.getLogger("DailyReportGenerator")

async def generate_daily_report():
    print(">>> Generating Daily Council Report (Simulation)...")
    
    # Mock Dependencies to avoid real LLM costs for this verification
    # But we want to see the 'Debate structure'. 
    # Ideally we use 'FAST' tier LLM or mocks with realistic text.
    # For this verification, let's use Mocks that return distinct personas to prove the 'Council' concept.
    
    with patch('src.services.council_service.AgentFactory') as MockFactory:
        # 1. Setup Persona Mocks
        fundamental = MagicMock(); fundamental.name = "Fundamental"; fundamental.run.return_value = "NVDA earnings look strong, PEG is 1.2. Recommending BUY."
        momentum = MagicMock(); momentum.name = "Momentum"; momentum.run.return_value = "RSI is 75 (Overbought). MACD bearish crossover. Recommending HOLD/SELL."
        risk = MagicMock(); risk.name = "Risk"; risk.run.return_value = "VIX is rising (18.5). Portfolio Beta is high. Suggest reducing leverage."
        macro = MagicMock(); macro.name = "Macro"; macro.run.return_value = "Fed likely to hold rates. inflation sticky. Neutral outlook."
        sentiment = MagicMock(); sentiment.name = "Sentiment"; sentiment.run.return_value = "Retail sentiment is Euphoric. Contrarian signal: Caution."
        
        # Chairperson
        cio = MagicMock(); cio.name = "Chairperson (CIO)"; cio.run.return_value = "CONSENSUS: HOLD. \nReasoning: Fundamental is strong but Momentum and Sentiment suggest overheating. We will wait for a dip."
        
        MockFactory.create_fundamental_agent.return_value = fundamental
        MockFactory.create_momentum_agent.return_value = momentum
        MockFactory.create_risk_agent.return_value = risk
        MockFactory.create_macro_agent.return_value = macro
        MockFactory.create_sentiment_agent.return_value = sentiment
        MockFactory.create_cio_agent.return_value = cio
        MockFactory.create_agent.return_value = cio # Fallback
        
        # Mock Router and VectorRepo
        with patch('src.services.council_service.DynamicModelRouter') as MockRouter:
            MockRouter.return_value.select_tier.return_value = "flash"
            
            with patch('src.services.council_service.VectorRepository'):
                
                service = CouncilService()
                
                # 2. Trigger Session for Daily Report
                topic = "Daily Market Analysis: 2026-02-03"
                context = {
                    "source": "Scheduler",
                    "market_data": {"vix": 18.5, "spy": 430.0}
                }
                
                result = service.start_session(topic, context)
                
                # 3. Output Minutes
                print("\n" + "="*40)
                print(f"📄 COUNCIL MINUTES: {topic}")
                print("="*40)
                
                # In a real run, transcript would be in valid format.
                # Here we reconstruct based on our mock flows or result.
                # Since start_session logic logs it, we can't easily capture logs without stream handler.
                # But we can print what the decision was.
                
                print(f"\n[PARTICIPANTS]: Fundamental, Momentum, Risk, Macro, Sentiment")
                print(f"\n[DEBATE HIGHLIGHTS]:")
                print(f"- Fundamental: {fundamental.run.return_value}")
                print(f"- Momentum: {momentum.run.return_value}")
                print(f"- Risk: {risk.run.return_value}")
                print(f"- Macro: {macro.run.return_value}")
                print(f"- Sentiment: {sentiment.run.return_value}")
                
                print("\n[FINAL DECISION (CIO)]:")
                print(result.get('consensus'))
                print("="*40)
                
                # Save to file for user review
                with open("council_report_output.txt", "w") as f:
                    f.write(f"COUNCIL MINUTES: {topic}\n")
                    f.write(f"DECISION: {result.get('consensus')}\n")

if __name__ == "__main__":
    asyncio.run(generate_daily_report())
