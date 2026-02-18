#!/usr/bin/env python3
"""
eToro 資產同步到交易紀錄腳本
Sync eToro portfolio and history to transactions table
"""

import os
import logging
from datetime import datetime
from dotenv import load_dotenv
from src.services.etoro_service import EtoroService
from src.repositories.transaction_repository import SqliteTransactionRepository
from src.data.database import get_db_connection
from sqlalchemy import text

# Load environment variables
load_dotenv()

# Override DB_HOST for local development (PostgreSQL is on localhost, not 'postgres' hostname)
if os.getenv('DB_TYPE') == 'postgres' and os.getenv('DB_HOST') == 'postgres':
    os.environ['DB_HOST'] = 'localhost'

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """
    Main function to sync eToro portfolio and history to transactions table.
    主函式：同步 eToro 投資組合和歷史到交易紀錄表。
    """
    user_id = '90693c07-6177-42df-97d9-915f3ce7c573'
    
    logger.info("=" * 60)
    logger.info("eToro 資產同步工具")
    logger.info("=" * 60)
    
    # Initialize eToro service with user_id to load credentials from database
    # 使用 user_id 初始化 eToro 服務以從資料庫載入憑證
    etoro = EtoroService(user_id=user_id)
    
    # 1. Get current account status
    logger.info("\n[1] 獲取帳戶資訊...")
    account = etoro.get_account()
    if account:
        logger.info(f"  帳戶 ID: {account.account_id}")
        logger.info(f"  總權益: ${account.total_equity:,.2f}")
        logger.info(f"  現金: ${getattr(account, 'cash', 0):,.2f}")
        logger.info(f"  購買力: ${getattr(account, 'buying_power', 0):,.2f}")
    else:
        logger.warning("  無法獲取帳戶資訊")
    
    # 2. Get current positions
    logger.info("\n[2] 獲取持倉資訊...")
    positions = etoro.get_positions()
    logger.info(f"  持倉數量: {len(positions)}")
    
    total_mv = 0
    for pos in positions:
        # Position object uses open_price, not avg_price
        logger.info(f"  - {pos.symbol}: {pos.quantity:.6f} 股 @ ${pos.open_price:.2f} | 市值: ${pos.market_value:,.2f} | 損益: ${pos.unrealized_pnl:,.2f}")
        total_mv += pos.market_value
    
    if positions:
        logger.info(f"  總市值: ${total_mv:,.2f}")
    
    # 3. Get transaction history
    logger.info("\n[3] 獲取交易歷史...")
    history = etoro.get_history()
    logger.info(f"  歷史交易數量: {len(history)}")
    
    if history:
        logger.info("  最近 5 筆交易:")
        for i, trade in enumerate(history[:5]):
            ticker = trade.get('Instrument', trade.get('symbol', 'N/A'))
            date = trade.get('OpenDateTime', trade.get('open_date', 'N/A'))
            action = trade.get('Action', trade.get('action', 'N/A'))
            qty = trade.get('Amount', trade.get('quantity', 0))
            price = trade.get('OpenRate', trade.get('open_price', 0))
            logger.info(f"    {i+1}. {date} | {action} {ticker} | {qty} @ ${price}")
    
    # 4. Sync to transactions table
    logger.info("\n[4] 同步到交易紀錄...")
    logger.info("  執行初始同步（從 2024-01-01 開始）...")
    result = etoro.sync_history(user_id=user_id, initial_sync=True)
    logger.info(f"  新增: {result['added']} 筆")
    logger.info(f"  跳過: {result['skipped']} 筆")
    
    # 5. Verify transactions in DB
    logger.info("\n[5] 驗證資料庫中的交易紀錄...")
    conn = get_db_connection()
    try:
        result = conn.execute(text(
            "SELECT COUNT(*) as cnt FROM transactions WHERE user_id = :uid"
        ), {"uid": user_id}).fetchone()
        
        total_txs = result[0] if result else 0
        logger.info(f"  資料庫中總交易數: {total_txs}")
        
        # Show recent transactions
        recent = conn.execute(text(
            "SELECT ticker, trade_date, action, quantity, price, amount "
            "FROM transactions WHERE user_id = :uid "
            "ORDER BY trade_date DESC LIMIT 5"
        ), {"uid": user_id}).fetchall()
        
        if recent:
            logger.info("  最近 5 筆資料庫交易:")
            for i, tx in enumerate(recent):
                logger.info(f"    {i+1}. {tx[1]} | {tx[2]} {tx[0]} | {tx[3]} @ ${tx[4]:.2f} | 總額: ${tx[5]:.2f}")
        
    finally:
        conn.close()
    
    # 6. Calculate and add initial deposit
    logger.info("\n[6] 計算初始入金...")
    if account and total_txs > 0:
        # 計算公式：初始入金 = 當前總權益 + 所有賣出金額 - 所有買入金額 - 所有費用
        # Formula: Initial Deposit = Current Equity + All Sell Amounts - All Buy Amounts - All Fees
        conn = get_db_connection()
        try:
            # Get sum of all buy transactions
            buy_sum = conn.execute(text(
                "SELECT COALESCE(SUM(amount + fees), 0) FROM transactions WHERE user_id = :uid AND action = 'BUY'"
            ), {"uid": user_id}).scalar() or 0
            
            # Get sum of all sell transactions
            sell_sum = conn.execute(text(
                "SELECT COALESCE(SUM(amount - fees), 0) FROM transactions WHERE user_id = :uid AND action = 'SELL'"
            ), {"uid": user_id}).scalar() or 0
            
            # Calculate initial deposit
            # 初始入金 = 當前權益 + 已賣出收入 - 已買入支出
            initial_deposit = account.total_equity + buy_sum - sell_sum
            
            logger.info(f"  當前總權益: ${account.total_equity:,.2f}")
            logger.info(f"  累計買入支出: ${buy_sum:,.2f}")
            logger.info(f"  累計賣出收入: ${sell_sum:,.2f}")
            logger.info(f"  計算初始入金: ${initial_deposit:,.2f}")
            
            # Check if DEPOSIT already exists
            existing_deposit = conn.execute(text(
                "SELECT COUNT(*) FROM transactions WHERE user_id = :uid AND action = 'DEPOSIT'"
            ), {"uid": user_id}).scalar()
            
            if existing_deposit == 0 and initial_deposit > 0:
                # Add DEPOSIT transaction
                trans_repo = SqliteTransactionRepository()
                trans_repo.add(
                    user_id=user_id,
                    ticker='USD',
                    date='2024-01-01',
                    action='DEPOSIT',
                    quantity=initial_deposit,
                    price=1.0,
                    fees=0.0
                )
                logger.info(f"  ✓ 已新增初始入金記錄: ${initial_deposit:,.2f}")
            elif existing_deposit > 0:
                logger.info(f"  ℹ 已存在 DEPOSIT 記錄，跳過")
            else:
                logger.warning(f"  ⚠ 計算出的初始入金為負值或零，跳過")
                
        finally:
            conn.close()
    else:
        logger.warning("  無法計算初始入金（缺少帳戶資訊或交易記錄）")
    
    # 7. Dashboard comparison
    logger.info("\n[7] Dashboard 資料對比...")
    logger.info("  請在 Dashboard 中確認以下數據是否一致:")
    logger.info(f"  - 總權益: ${account.total_equity:,.2f}" if account else "  - 總權益: N/A")
    logger.info(f"  - 持倉數: {len(positions)}")
    logger.info(f"  - 持倉市值: ${total_mv:,.2f}")
    logger.info(f"  - 交易紀錄數: {total_txs}")
    
    logger.info("\n" + "=" * 60)
    logger.info("同步完成！")
    logger.info("=" * 60)

if __name__ == "__main__":
    main()
