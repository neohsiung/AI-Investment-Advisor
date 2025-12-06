import argparse
import json
import sys
import os

# Ensure project root is in sys.path
sys.path.append(os.getcwd())

from src.agents.momentum import MomentumAgent
from src.agents.fundamental import FundamentalAgent
from src.agents.macro import MacroAgent
from src.agents.cio import CIOAgent
from src.database import init_db
from src.utils.logger import setup_logger

logger = setup_logger("Workflow")

def run_workflow(mode='weekly', dry_run=False, force=False):
    logger.info(f"Starting AI Investment Advisor Workflow (Mode: {mode}, Force: {force})...")
    
    # Ensure DB is initialized
    init_db()
    logger.info("Database initialized.")
    
    # 1. 初始化 Agents
    use_cache = not force
    momentum_agent = MomentumAgent(use_cache=use_cache)
    fundamental_agent = FundamentalAgent(use_cache=use_cache)
    macro_agent = MacroAgent(use_cache=use_cache)
    cio_agent = CIOAgent(use_cache=use_cache)


    
    # 2. 獲取數據 (Real)
    from src.database import get_db_connection
    import pandas as pd
    from src.market_data import MarketDataService
    
    conn = get_db_connection()
    # 查詢活躍持倉
    query = """
        SELECT ticker, SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END) as net_qty 
        FROM transactions 
        GROUP BY ticker 
        HAVING net_qty > 0.0001
    """
    df = pd.read_sql(query, conn)
    conn.close()
    
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
    
    # 4. 決定是否執行 CIO
    should_run_cio = False
    if mode == 'weekly':
        should_run_cio = True
    elif mode == 'daily' and has_significant_change:
        logger.info("Significant momentum change detected. Triggering CIO Agent.")
        should_run_cio = True
    
    if should_run_cio:
        logger.info("Running CIO Agent...")
        
        # 計算真實槓桿比率
        from src.analytics import LeverageCalculator
        calc = LeverageCalculator()
        metrics = calc.calculate_metrics(current_prices)
        leverage_ratio = metrics['leverage_ratio']
        
        cio_context = {
            "macro_report": macro_report,
            "momentum_reports": momentum_reports,
            "fundamental_reports": fundamental_reports,
            "leverage_ratio": leverage_ratio
        }
        final_report = cio_agent.run(cio_context)
        
        logger.info("\n=== Final Report ===\n")
        logger.info(final_report)
        
        # 儲存與發送報告 (Dry Run 不寄信，但可存檔或僅顯示)
        if not dry_run:
            # 1. Save to File
            with open(f"{mode}_report.md", "w") as f:
                f.write(final_report)
            logger.info(f"Report saved to {mode}_report.md")
            
            # 2. Save to Database
            from src.database import get_db_connection
            import uuid
            from src.utils.time_utils import format_time
            
            conn = get_db_connection()
            cursor = conn.cursor()
            report_id = str(uuid.uuid4())
            date_str = format_time()
            cursor.execute("INSERT INTO reports (id, date, content, summary) VALUES (?, ?, ?, ?)", 
                           (report_id, date_str, final_report, f"{mode.capitalize()} Advisory"))
            conn.commit()
            conn.close()
            logger.info("Report saved to database.")
            
            # 3. Send Email
            from src.notifier import EmailNotifier
            notifier = EmailNotifier()
            notifier.send_report(f"Investment Advisory ({mode.capitalize()}) - {date_str[:10]}", final_report)
            logger.info("[Dry Run] Report generated but NOT saved to DB or emailed.")
        
        # 4.1 執行系統工程師代理人 System Engineer Process
        # 不論 Dry Run 是否開啟，只要有 CIO 報告，我們都可以嘗試優化，
        # 但為了安全，如果 Dry Run 開啟，我們也只在 Log 顯示優化結果而不寫入? 
        # 其實 Engineer Agent 預設就會寫 DB 和檔案，如果是 Dry Run，我們可以傳遞參數讓它不要寫
        # 但這裡簡化流程，假設 Dry Run 就完全不執行 Engineer
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
        
        # 使用真實價格
        calc = LeverageCalculator()
        metrics = calc.calculate_metrics(current_prices)
        
        recorder = SnapshotRecorder()
        recorder.record_daily_snapshot(metrics['nlv'], metrics['cash_balance'])

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mode", choices=['daily', 'weekly'], default='weekly', help="Execution mode")
    args = parser.parse_args()
    
    run_workflow(mode=args.mode, dry_run=args.dry_run)
