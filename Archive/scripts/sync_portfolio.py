import os
import sys
import logging
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from dotenv import load_dotenv
from sqlalchemy import text

# Load environment variables first
load_dotenv()

# Override DB_HOST for local development (after load_dotenv)
if os.getenv('DB_TYPE') == 'postgres' and os.getenv('DB_HOST') == 'postgres':
    os.environ['DB_HOST'] = 'localhost'

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.services.etoro_service import EtoroService
from src.repositories.settings_repository import SqliteSettingsRepository
from src.repositories.transaction_repository import SqliteTransactionRepository
from src.data.database import get_db_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PortfolioFix")

def main():
    """
    Main function to sync portfolio positions and history.
    主函式：同步投資組合持倉和歷史。
    """
    # v4.1: Use UUID instead of email
    # v4.1: 使用 UUID 而非 email
    user_id = "90693c07-6177-42df-97d9-915f3ce7c573"
    
    # --- PART 1: SYNC POSITIONS ---
    logger.info("🚀 STARTING: Sync Positions (Full Restore)...")
    
    repo = SqliteSettingsRepository()
    api_key = repo.get(user_id, "etoro_api_key") or os.getenv("ETORO_API_KEY")
    user_key = repo.get(user_id, "etoro_user_key") or os.getenv("ETORO_USER_KEY")
    mode = repo.get(user_id, "etoro_mode") or "real"
    
    etoro = EtoroService(mode=mode, api_key=api_key, user_key=user_key)
    positions = etoro.get_positions()
    logger.info(f"✅ Found {len(positions)} valid positions.")
    
    trans_repo = SqliteTransactionRepository()
    
    with get_db_connection() as conn:
        logger.info("🧹 Clearing old transactions...")
        conn.execute(text("DELETE FROM transactions WHERE user_id = :uid"), {"uid": user_id})
        conn.execute(text("DELETE FROM daily_snapshots WHERE user_id = :uid"), {"uid": user_id})
        conn.commit()
        
    logger.info("💾 Inserting corrected transactions...")
    for p in positions:
        date_str = p.open_date.strftime('%Y-%m-%d')
        trans_repo.add(
            user_id=user_id,
            ticker=p.symbol,
            date=date_str,
            action="BUY",
            quantity=p.quantity,
            price=p.open_price,
            fees=0.0
        )

    # --- PART 2: BACKFILL HISTORY ---
    logger.info("🚀 STARTING: Backfill History...")
    
    with get_db_connection() as conn:
        # PostgreSQL uses %(uid)s for pandas.read_sql, not :uid
        # PostgreSQL 在 pandas.read_sql 中使用 %(uid)s 而非 :uid
        txns = pd.read_sql("SELECT * FROM transactions WHERE user_id = %(uid)s ORDER BY trade_date ASC", conn, params={"uid": user_id})
        cfs = pd.read_sql("SELECT * FROM cash_flows WHERE user_id = %(uid)s ORDER BY date ASC", conn, params={"uid": user_id})
        
    if txns.empty:
        logger.warning("No transactions to backfill.")
        return

    # Normalize Dates
    txns['trade_date'] = pd.to_datetime(txns['trade_date']).dt.date
    cfs['date'] = pd.to_datetime(cfs['date']).dt.date
    
    # Update Cash Flow Date (Deposit) to match first txn if needed
    start_date = txns['trade_date'].min()
    logger.info(f"📅 Start Date: {start_date}")
    
    # Ensure Deposit is backdated
    with get_db_connection() as conn:
        conn.execute(text("UPDATE cash_flows SET date = :d WHERE user_id = :uid AND type='DEPOSIT'"), {"d": start_date, "uid": user_id})
        conn.commit()
        # Reload CFs
        cfs = pd.read_sql("SELECT * FROM cash_flows WHERE user_id = :uid ORDER BY date ASC", conn, params={"uid": user_id})
        cfs['date'] = pd.to_datetime(cfs['date']).dt.date

    end_date = datetime.now().date()
    
    # Hist Data
    tickers = txns['ticker'].unique().tolist()
    logger.info(f"🔍 Tickers: {tickers}")
    yf_data = yf.download(tickers, start=start_date - timedelta(days=5), end=end_date + timedelta(days=1), progress=False, group_by='ticker')
    
    def get_price(tkr, d):
        try:
            ts = pd.Timestamp(d)
            if len(tickers) == 1:
                series = yf_data['Close']
            else:
                if tkr not in yf_data.columns.levels[0]: return 0
                series = yf_data[tkr]['Close']
            idx = series.index.get_indexer([ts], method='pad')[0]
            if idx >= 0:
                val = series.iloc[idx]
                return float(val) if pd.notna(val) else 0.0
        except: return 0.0
        return 0.0

    snapshots = []
    curr = start_date
    while curr <= end_date:
        # Filter
        day_txns = txns[txns['trade_date'] <= curr]
        day_cfs = cfs[cfs['date'] <= curr]
        
        invested = 0.0
        for _, cf in day_cfs.iterrows():
            if cf['type'] == 'DEPOSIT': invested += float(cf['amount'])
            elif cf['type'] == 'WITHDRAWAL': invested -= float(cf['amount'])
            
        holdings = {}
        trade_cash_impact = 0.0
        
        for _, t in day_txns.iterrows():
            qty = float(t['quantity']); amt = float(t['amount']); act = t['action'].upper(); tkr = t['ticker']
            if act == 'BUY':
                holdings[tkr] = holdings.get(tkr, 0) + qty
                trade_cash_impact -= amt
            elif act == 'SELL':
                holdings[tkr] = holdings.get(tkr, 0) - qty
                trade_cash_impact += amt
                
        # With restored positions but user claiming lower Invested figure ($674),
        # we have a mismatch in user perception vs DB reality ($974).
        # But we MUST trust the transactions if they are real.
        # User Invested $992 total (Cash $318 + Pos $674). 
        # But our DB has Pos $974 + Cash $318 = $1292 Invested? No.
        # If DB has Pos $974, and Cash is $318.
        # Then Total Equity = $1292 + P&L. 
        # But user says Equity is $1182.
        # Differences = $110? 
        # Let's see what happens.
        
        cash_balance = invested + trade_cash_impact
        
        mv = 0.0
        tnv = 0.0
        for tkr, qty in holdings.items():
            if qty > 0.0001:
                px = get_price(tkr, curr)
                val = qty * px
                mv += val
                tnv += abs(val)
                
        nlv = cash_balance + mv
        pnl = nlv - invested
        lev = tnv / nlv if nlv > 0 else 0
        
        snapshots.append({
            "user_id": user_id, "date": curr.strftime('%Y-%m-%d'),
            "total_nlv": nlv, "cash_balance": cash_balance, "invested_capital": invested,
            "pnl": pnl, "total_tnv": tnv, "leverage_ratio": lev
        })
        curr += timedelta(days=1)
        
    with get_db_connection() as conn:
        stmt = text("INSERT INTO daily_snapshots (user_id, date, total_nlv, cash_balance, invested_capital, pnl, total_tnv, leverage_ratio) VALUES (:user_id, :date, :total_nlv, :cash_balance, :invested_capital, :pnl, :total_tnv, :leverage_ratio)")
        for s in snapshots:
            conn.execute(stmt, s)
        conn.commit()
        
    logger.info(f"✅ Backfill Complete: {len(snapshots)} snapshots.")
    last = snapshots[-1]
    logger.info(f"🏁 Final State: NLV=${last['total_nlv']:.2f}, Invested=${last['invested_capital']:.2f}, P&L=${last['pnl']:.2f}")

if __name__ == "__main__":
    main()
