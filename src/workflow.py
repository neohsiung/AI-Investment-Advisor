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
from src.database import init_db, get_db_connection
from src.utils.logger import setup_logger
from src.utils.time_utils import format_time
from sqlalchemy import text
from src.market_data import MarketDataService

logger = setup_logger("Workflow")

def run_workflow(mode="daily", dry_run=False, user_id=None):
    """
    執行完整投資建議流程
    mode: 'daily' (每日檢查) or 'weekly' (每週深入分析/報告) or 'demo'
    dry_run: True 不會發送 Email
    user_id: 針對特定使用者執行 (SaaS Mode)
    """
    print(f"[{format_time()}] Starting Workflow ({mode}) for User: {user_id or 'All'}...")
    logger.info(f"Starting AI Investment Advisor Workflow (Mode: {mode}, User: {user_id})...")

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
    logger.info(f"Active Tickers: {tickers}")
    
    market_service = MarketDataService()
    current_prices = market_service.get_current_prices(tickers)
    
    macro_report = "Skipped (Daily Mode)"
    momentum_reports = []
    fundamental_reports = []
    
    # 3. 執行分析
    # Momentum (Always run)
    logger.info("Running Momentum Agent...")
    has_significant_change = False
    
    for ticker in tickers:
        logger.info(f"Processing {ticker} with Momentum Agent...")
        price = current_prices.get(ticker, 0.0)
        
        # 獲取技術指標
        indicators = market_service.get_technical_indicators(ticker)
        
        # Momentum Agent Context Injection
        mom_ctx = {
            "ticker": ticker, 
            "price": price,
            "indicators": indicators
        } 
        mom_res = momentum_agent.run(mom_ctx)
        momentum_reports.append(f"{ticker}: {mom_res}")
        
        if "BUY" in mom_res or "SELL" in mom_res:
            has_significant_change = True

    # Macro & Fundamental (Weekly only)
    if mode == 'weekly':
        logger.info("Running Macro Agent...")
        # 獲取總經數據
        macro_data = market_service.get_macro_data()
        
        # Macro Agent Context Injection
        macro_context = {
            "macro_data": macro_data
        }
        macro_report = macro_agent.run(macro_context)
        
        logger.info("Running Fundamental Agent...")
        for ticker in tickers:
            logger.info(f"Processing {ticker} with Fundamental Agent...")
            # 獲取基本面與新聞
            financials = market_service.get_financials(ticker)
            news = market_service.get_news(ticker)
            
            # Fundamental Agent Context Injection
            fund_ctx = {
                "ticker": ticker,
                "financials": financials,
                "news": news
            }
            fund_res = fundamental_agent.run(fund_ctx)
            fundamental_reports.append(fund_res)
    
    # 4. 決定是否執行 CIO (Decide whether to run CIO Agent)
    should_run_cio = False
    if mode == 'weekly':
        should_run_cio = True
    elif mode == 'daily' and has_significant_change:
        logger.info("檢測到顯著動能變化，觸發 CIO Agent (Significant momentum change detected. Triggering CIO Agent).")
        should_run_cio = True
    
    if should_run_cio:
        logger.info("啟動 CIO Agent 進行最終決策... (Running CIO Agent...)")
        
        # 計算真實槓桿比率 (Need user specific cash balance for real leverage calc, currently simplified)
        # TODO: Inject cash balance for leverage calculation per user
        from src.analytics import LeverageCalculator
        calc = LeverageCalculator()
        
        # Leverage calc logic needs refinement for specific user but keeping baseline
        metrics = calc.calculate_metrics(current_prices, user_id=user_id) # Ensure calculate_metrics supports user_id
        leverage_ratio = metrics['leverage_ratio']
        
        # 構建 CIO Context，包含所有上游 Agent 的分析結果
        cio_context = {
            "macro_report": macro_report,
            "momentum_reports": momentum_reports,
            "fundamental_reports": fundamental_reports,
            "leverage_ratio": leverage_ratio
        }
        final_report = cio_agent.run(cio_context)
        
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
            notifier.send_report(f"Investment Advisory ({mode.capitalize()}) - {date_str[:10]}", final_report)
            logger.info("Report emailed.")
        else:
            logger.info("[Dry Run] Report generated but NOT saved to DB or emailed.")
        
        # 4.1 System Engineer
        if not dry_run:
            logger.info("Running System Engineer Agent for Optimization...")
            from src.agents.engineer import SystemEngineerAgent
            engineer_agent = SystemEngineerAgent()
            optimization_report = engineer_agent.run({
                "cio_report": final_report
            })
            logger.info(f"Engineer Agent Report: {optimization_report}")
            
    else:
        logger.info("No significant changes or weekly trigger. Skipping CIO Agent and Report.")

    # 5. 記錄每日快照 (Always run)
    if not dry_run:
        logger.info("Recording Daily Snapshot...")
        from src.analytics import LeverageCalculator, SnapshotRecorder
        calc = LeverageCalculator()
        metrics = calc.calculate_metrics(current_prices, user_id=user_id) # Pass user_id
        
        recorder = SnapshotRecorder()
        recorder.record_daily_snapshot(metrics['nlv'], metrics['cash_balance'], user_id=user_id)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mode", choices=['daily', 'weekly'], default='weekly', help="Execution mode")
    parser.add_argument("--user_id", type=str, default=None, help="Specific User ID for SaaS mode")
    args = parser.parse_args()
    
    run_workflow(mode=args.mode, dry_run=args.dry_run, user_id=args.user_id)
