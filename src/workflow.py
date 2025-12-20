import argparse
import json
import sys
import os
import pandas as pd
from datetime import datetime

# Ensure project root is in sys.path
sys.path.append(os.getcwd())

from src.agents.momentum import MomentumAgent
from src.agents.fundamental import FundamentalAgent
from src.agents.macro import MacroAgent
from src.agents.cio import CIOAgent
from src.data.database import init_db, get_db_connection
from src.utils.logger import setup_logger
from src.utils.time_utils import format_time
from sqlalchemy import text
from src.market_data import MarketDataService
from src.services.fred_service import FredService

logger = setup_logger("Workflow")

def run_workflow(mode="daily", dry_run=False, user_id=None, force_report=False):
    """
    執行完整投資建議流程
    mode: 'daily' (每日檢查) or 'weekly' (每週深入分析/報告) or 'demo'
    dry_run: True 不會發送 Email
    user_id: 針對特定使用者執行 (SaaS Mode)
    force_report: True 強制生成報告 (即使無顯著變化)
    """
    print(f"[{format_time()}] Starting Workflow ({mode}) for User: {user_id or 'All'} [Force: {force_report}]...")
    logger.info(f"Starting AI Investment Advisor Workflow (Mode: {mode}, User: {user_id}, Force: {force_report})...")

    # Ensure DB is initialized
    init_db()
    logger.info("Database initialized.")

    # 1. 初始化 Agents (Initialize Agents)
    use_cache = True
    # TODO: In real SaaS, pass user_id to Agents for personalized context/memory
    momentum_agent = MomentumAgent(use_cache=use_cache)
    fundamental_agent = FundamentalAgent(use_cache=use_cache)
    macro_agent = MacroAgent(use_cache=use_cache)
    cio_agent = CIOAgent(use_cache=use_cache)

    # 2. 獲取數據 (Real)
    conn = get_db_connection()

    # Base query for active tickers
    base_query = """
        SELECT ticker, SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END) as net_qty
        FROM transactions
    """
    params = {}

    # Filter by user_id if provided
    if user_id:
        base_query += " WHERE user_id = :user_id "
        params['user_id'] = user_id

    base_query += """
        GROUP BY ticker
        HAVING net_qty > 0.0001
    """

    df = pd.read_sql(base_query, conn, params=params)
    conn.close()

    # ... [Rest of logic remains largely same, just verify downstream usage] ...
    # Wait, need to check if we replaced too much context.
    # The tool 'replace_file_content' replaces checks of code.
    # I should be careful. I will use a larger block or multiple edits if needed.
    # But since I'm changing the function signature and the initial query logic, I'll replace the block from start of function to end of query.

    tickers = df['ticker'].tolist() if not df.empty else []
    logger.info(f"Active Holdings: {tickers}")

    market_service = MarketDataService()
    current_prices = market_service.get_current_prices(tickers)

    macro_report = "Skipped (Daily Mode)"
    momentum_reports = []
    fundamental_reports = []

    # Determine Report Focus
    report_focus = "Daily Tactical (短期戰術)" if mode == 'daily' else "Weekly Strategic (長期戰略)"
    logger.info(f"Report Focus: {report_focus}")

    # 3. 執行分析
    # Old simple loop removed. Now using Multi-stage Step 3.
    # The 'combined_tickers' logic is also handled in Step 2.

    # 3. 執行分析 (Execution Phase)
    
    # --- Step 1: Global Context (Macro) ---
    logger.info("Step 1: Analyzing Macro Environment...")
    fred_service = FredService()
    fred_data = fred_service.get_macro_indicators()
    market_macro = market_service.get_macro_data()
    macro_data = {**fred_data, **market_macro}
    
    macro_context = {"macro_data": macro_data}
    is_fresh, curr_hash, last_out = macro_agent.check_freshness(macro_context, state_key=None)
    
    if is_fresh or force_report:
        logger.info("Macro Data changed or forced. Running Macro Agent...")
        macro_report = macro_agent.run(macro_context)
        macro_agent.update_state(curr_hash, macro_report, state_key=None)
    else:
        logger.info("Macro Data unchanged. Using cached Macro Report.")
        macro_report = last_out

    # --- Step 2: Strategy & Screening (CIO) ---
    logger.info("Step 2: Developing Sector Strategy & Screening Candidates...")
    # Prepare Strategy Context
    strategy_ctx = {
        "user_id": user_id,
        "macro_report": macro_report
    }
    
    # Run CIO in 'strategy' mode
    # Note: Strategy output is JSON, so we handle it differently or assume run returns dict
    strategy_data = cio_agent.run(strategy_ctx, mode='strategy')
    
    sector_strategy = strategy_data.get("sector_strategy", {})
    raw_candidates = strategy_data.get("candidates", [])
    
    # Normalize tickers for Yahoo Finance (e.g., BRK.B -> BRK-B)
    candidates = [c.replace('.', '-') for c in raw_candidates]
    
    logger.info(f"Sector Strategy: {json.dumps(sector_strategy, ensure_ascii=False)}")
    logger.info(f"Screened Candidates (No ETFs): {candidates}")
    
    # Combine Scope: Holdings + Screened Candidates
    current_holdings = df['ticker'].tolist() if not df.empty else []
    # Deduplicate and merge
    target_tickers = list(set(current_holdings + candidates))
    
    logger.info(f"Analysis Scope: Holdings({len(current_holdings)}) + Candidates({len(candidates)}) = Total {len(target_tickers)}")
    
    # --- Step 3: Deep Research (Momentum & Fundamental) ---
    logger.info("Step 3: Conducting Deep Research on Target Tickers...")
    
    # Refresh Prices for ALL targets
    target_prices = market_service.get_current_prices(target_tickers)
    
    momentum_reports = []
    fundamental_reports = []
    
    for ticker in target_tickers:
        # logger.info(f"Researching {ticker}...")
        price = target_prices.get(ticker, 0.0)
        
        # A. Momentum
        indicators = market_service.get_technical_indicators(ticker)
        mom_ctx = { 
            "ticker": ticker, 
            "price_data": {"current_price": price}, 
            "indicators": indicators 
        }
        
        is_fresh, curr_hash, last_out = momentum_agent.check_freshness(mom_ctx, state_key=ticker)
        if is_fresh or force_report:
            # logger.info(f"[{ticker}] Running Momentum...")
            mom_res = momentum_agent.run(mom_ctx)
            momentum_agent.update_state(curr_hash, mom_res, state_key=ticker)
        else:
            mom_res = last_out
        momentum_reports.append(f"### {ticker}\n{mom_res}")
        
        # B. Fundamental (Weekly or Forced) - Daily mode usually skips FM for non-holdings to save cost?
        # User requested deep research, so we run it.
        if mode == 'weekly' or force_report:
            financials = market_service.get_financials(ticker)
            news = market_service.get_news(ticker)
            fund_ctx = {
                "ticker": ticker,
                "financials": financials,
                "news": news
            }
            
            is_fresh, curr_hash, last_out = fundamental_agent.check_freshness(fund_ctx, state_key=ticker)
            if is_fresh or force_report:
                # logger.info(f"[{ticker}] Running Fundamental...")
                fund_res = fundamental_agent.run(fund_ctx)
                fundamental_agent.update_state(curr_hash, fund_res, state_key=ticker)
            else:
                fund_res = last_out
            fundamental_reports.append(fund_res)

    # --- Step 4: Final Decision & Reporting (CIO) ---
    logger.info("Step 4: Generating Final Investment Report...")
    
    should_run_cio = True # Always run if we went this far in new workflow
    
    if should_run_cio:
        # Calculate Leverage (based on holdings only)
        # We need prices for holdings to calc NAV
        # target_prices contains all we need
        from src.analytics import LeverageCalculator
        calc = LeverageCalculator()
        metrics = calc.calculate_metrics(target_prices, user_id=user_id) 
        leverage_ratio = metrics['leverage_ratio']

        # Agent Status
        agent_status_str = "Unknown" 
        # ... (keep existing status fetch logic if needed or simplify) ...

        cio_context = {
            "user_id": user_id,
            "report_focus": report_focus,
            "agent_status": agent_status_str,
            "macro_report": macro_report,
            "momentum_reports": "\n".join(momentum_reports),
            "fundamental_reports": "\n".join(fundamental_reports),
            "leverage_ratio": leverage_ratio,
            "sector_strategy": json.dumps(sector_strategy, ensure_ascii=False) # Inject strategy
        }
        
        # Run CIO in 'report' mode
        is_fresh, curr_hash, last_out = cio_agent.check_freshness(cio_context, state_key=user_id)
        
        if is_fresh or force_report:
            logger.info("Generating NEW CIO Report...")
            final_report = cio_agent.run(cio_context, mode='report')
            cio_agent.update_state(curr_hash, final_report, state_key=user_id)
        else:
            logger.info("Using cached CIO Report.")
            final_report = last_out
            
        logger.info("\n=== Final Report ===\n")
        logger.info(final_report)

        # 儲存與發送報告
        if not dry_run:
            # 1. Save to File
            filename = f"{mode}_report_{user_id or 'all'}.md"
            with open(filename, "w") as f:
                f.write(final_report)
            logger.info(f"Report saved to {filename}")

            # 2. Save to Database
            import uuid
            conn = get_db_connection()
            report_id = str(uuid.uuid4())
            date_str = format_time()
            conn.execute(text("INSERT INTO reports (id, user_id, date, content, summary) VALUES (:id, :user_id, :date, :content, :summary)"), {
                "id": report_id,
                "user_id": user_id,
                "date": date_str,
                "content": final_report,
                "summary": f"{mode.capitalize()} Advisory"
            })
            conn.commit()
            conn.close()
            logger.info("Report saved to database.")

            # 3. Send Email
            from src.notifier import EmailNotifier
            notifier = EmailNotifier()
            # user_id is the email in this system
            notifier.send_report(f"Investment Advisory ({mode.capitalize()}) - {date_str[:10]}", final_report, to_email=user_id)
            logger.info("Report emailed.")
        else:
            logger.info("[Dry Run] Report generated but NOT saved to DB or emailed.")

        # 4.1 System Engineer (Optimization)
        if not dry_run and mode == 'weekly': # Optimization usually runs weekly
            logger.info("Running System Engineer Agent for Optimization Loop...")
            try:
                from src.agents.engineer import SystemEngineerAgent
                engineer = SystemEngineerAgent()
                
                # SystemEngineerAgent.run() expects {"cio_report": final_report}
                # It contains internal logic to parse feedback from the CIO report
                optimization_results = engineer.run({
                    "cio_report": final_report
                })

                logger.info(f"System Engineer Report:\n{optimization_results}")

                # Log to file as well
                log_entry = f"\n\n--- Optimization {date_str} ---\n{optimization_results}"
                with open("logs/optimization_log.txt", "a") as logf:
                    logf.write(log_entry)

            except Exception as e:
                logger.error(f"System Engineer Agent failed: {e}")

    else:
        logger.info("No significant changes or weekly trigger. Skipping CIO Agent and Report.")

    # 5. 記錄每日快照 (Always run)
    if not dry_run:
        logger.info("Recording Daily Snapshot...")
        from src.analytics import LeverageCalculator, SnapshotRecorder
        calc = LeverageCalculator()
        metrics = calc.calculate_metrics(current_prices, user_id=user_id) # Pass user_id

        recorder = SnapshotRecorder()
        recorder.record_daily_snapshot(metrics['nlv'], metrics['cash_balance'], user_id=user_id, total_tnv=metrics.get('tnv', 0), leverage_ratio=metrics.get('leverage_ratio', 0))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mode", choices=['daily', 'weekly'], default='weekly', help="Execution mode")
    parser.add_argument("--user_id", type=str, default=None, help="Specific User ID for SaaS mode")
    parser.add_argument("--force-report", action="store_true", help="Force generate report even if no significant changes")
    args = parser.parse_args()

    run_workflow(mode=args.mode, dry_run=args.dry_run, user_id=args.user_id, force_report=args.force_report)
