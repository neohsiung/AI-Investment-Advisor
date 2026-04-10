import asyncio
import json
import os
from src.services.sentinel_service import SentinelService
from src.services.workflow_service import DailyWorkflow
from src.repositories.settings_repository import AlchemySettingsRepository
from src.utils.logger import setup_logger

logger = setup_logger("Verification")

async def verify_cash_deployment_flow():
    user_id = "default"
    
    # 0. Ensure user exists
    from src.data.database import get_db_engine
    from sqlalchemy import text
    engine = get_db_engine()
    with engine.connect() as conn:
        res = conn.execute(text("SELECT id FROM users WHERE id = :uid"), {"uid": user_id}).fetchone()
        if not res:
            logger.info(f"Creating missing user '{user_id}'...")
            conn.execute(text("INSERT INTO users (id, email, name) VALUES (:uid, :email, :name)"), 
                         {"uid": user_id, "email": "default@example.com", "name": "Default User"})
            conn.commit()
            
        # unconditionally ensure high cash snapshot
        logger.info("Setting mock daily snapshot for ratio calculation...")
        conn.execute(text("DELETE FROM daily_snapshots WHERE user_id = :uid"), {"uid": user_id})
        conn.execute(text("""
            INSERT INTO daily_snapshots (date, user_id, account_id, total_nlv, cash_balance, invested_capital, pnl)
            VALUES (CURRENT_DATE, :uid, '', 10000.0, 9000.0, 1000.0, 0.0)
        """), {"uid": user_id})
        conn.commit()

    # 1. Setup - Ensure target_cash_ratio is low enough to trigger
    settings_repo = AlchemySettingsRepository()
    settings_repo.set(user_id, "target_cash_ratio", 0.10) # 10%
    logger.info(f"Target cash ratio set to 0.10 for user {user_id}")
    
    # 2. Trigger - Run Sentinel Tick
    sentinel = SentinelService(user_id=user_id)
    
    # Mock Market Data to avoid connection issues
    from unittest.mock import MagicMock
    mock_market = MagicMock()
    mock_market.get_current_prices.return_value = {"SPY": 500.0, "^VIX": 15.0}
    mock_market.get_technical_indicators.return_value = {
        "sma": {"sma_200": 450.0},
        "rsi": 60,
        "macd": "bullish"
    }
    mock_market.get_macro_data.return_value = {
        "market_indicators": {"^VIX": 15.0, "SPY": 500.0}
    }
    mock_market.get_ohlcv.return_value = {
        "close": [16.0, 15.5, 15.2, 14.8, 15.0] * 10 # 50 days of fake data
    }
    sentinel.market_service = mock_market
    
    logger.info("Running Sentinel tick...")
    await sentinel.process_tick()
    
    # 3. Verify Memory - Check if 'cash_deployment' type report was stored
    from src.services.memory_service import MemoryService
    from src.repositories.memory_repository import AlchemyMemoryRepository
    from src.infrastructure.agent_llm_provider import AgentLLMProvider
    
    memory_repo = AlchemyMemoryRepository()
    llm_provider = AgentLLMProvider(user_id=user_id)
    memory_service = MemoryService(repository=memory_repo, llm_provider=llm_provider)
    
    mem_ctx = memory_service.get_context(user_id, "cash_deployment")
    if mem_ctx and mem_ctx.recent_items:
        latest = mem_ctx.recent_items[0]
        logger.info(f"SUCCESS: Found cash deployment analysis in memory from {latest.report_date}")
        logger.info(f"Analysis summary: {latest.compressed_summary[:100]}...")
    else:
        logger.error("FAILURE: No cash deployment analysis found in memory.")
        return

    # 4. Verify Workflow Integration - Run Daily Synthesis (Dry Run)
    daily = DailyWorkflow(user_id=user_id)
    # We only need to test synthesis
    # We'll mock the necessary context
    daily.context['tickers'] = []
    daily.context['ticker_reports'] = {}
    daily.context['market_data'] = {}
    
    logger.info("Generating Daily Report synthesis...")
    # This will call CIO with the cash_deployment_context
    report = await daily.synthesize_results()
    
    if "[CAPITAL DEPLOYMENT OPPORTUNITY DETECTED" in report:
        logger.info("SUCCESS: Daily Report contains capital deployment context.")
        # Check if it contains the actual candidates
        if "VOO" in report or "QQQ" in report:
            logger.info("SUCCESS: Report contains specific ticker recommendations.")
    else:
        logger.error("FAILURE: Daily Report missing deployment context.")
        logger.debug(f"Report content: {report[:500]}...")

if __name__ == "__main__":
    asyncio.run(verify_cash_deployment_flow())
