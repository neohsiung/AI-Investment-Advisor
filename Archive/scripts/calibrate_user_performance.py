import os
from sqlalchemy import text
from datetime import datetime, timedelta
from src.data.database import get_db_engine
from src.repositories.transaction_repository import AlchemyTransactionRepository
from src.services.analytics_service import update_daily_snapshot

def calibrate(user_id, target_profit, target_cash):
    os.environ['DB_HOST'] = 'localhost'
    engine = get_db_engine()
    repo = AlchemyTransactionRepository()
    
    # 1. Trigger fresh snapshot to get base NLV
    print("Triggering fresh snapshot to get current NLV...")
    update_daily_snapshot(os.getenv('DB_PATH'), user_id=user_id, force=True)
    
    with engine.connect() as conn:
        snap = conn.execute(text("SELECT total_nlv FROM daily_snapshots WHERE user_id = :uid ORDER BY date DESC LIMIT 1"), {"uid": user_id}).fetchone()
        current_nlv = float(snap[0]) if snap else 0.0
    
    # 2. Calculate required 'Invested Capital' to yield target profit
    # Profit = NLV - Invested => Invested = NLV - Profit
    target_invested = current_nlv - target_profit
    print(f"Current NLV: {current_nlv:.2f}, Target Profit: {target_profit:.2f} => Required Invested: {target_invested:.2f}")
    
    # 3. Clear all previous capital flows to ensure fresh accounting
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM transactions WHERE user_id = :uid AND (action = 'DEPOSIT' OR action = 'WITHDRAWAL' OR ticker = 'CASH_GHOST')"), {"uid": user_id})

    # 4. Adjust Invested Capital (Inflow)
    repo.add(user_id=user_id, ticker='USD', date='2024-01-01', action='DEPOSIT', quantity=target_invested, price=1.0, fees=0.0)
    print(f"Added fresh base DEPOSIT of {target_invested:.2f}")

    # 5. Adjust Cash Balance (without touching Invested Capital)
    # Cash = (Deposits - Withdrawals) + (Sells - Buys)
    current_cash = repo.get_cash_balance(user_id)
    diff_cash = target_cash - current_cash
    if abs(diff_cash) > 0.01:
        # To INCREASE cash without increasing Invested Capital: Add a phantom SELL
        # To DECREASE cash without decreasing Invested Capital: Add a phantom BUY
        action = 'SELL' if diff_cash > 0 else 'BUY'
        print(f"Adjusting Cash Balance by {diff_cash:+.2f} using ghost {action}")
        repo.add(user_id=user_id, ticker='CASH_GHOST', date='2026-02-18', action=action, quantity=abs(diff_cash), price=1.0, fees=0.0)

    # 4. Create Yesterday Anchor Bookmark
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    print(f"Seeding yesterday snapshot ({yesterday}) for charts...")
    with engine.begin() as conn:
        # Clone today's snapshot as starting point for yesterday
        conn.execute(text("""
            INSERT INTO daily_snapshots (date, user_id, total_nlv, cash_balance, invested_capital, pnl, total_tnv, leverage_ratio)
            SELECT :yest, user_id, total_nlv * 0.98, cash_balance, invested_capital, pnl * 0.9, total_tnv, leverage_ratio 
            FROM daily_snapshots 
            WHERE user_id = :uid AND date = :today
            ON CONFLICT (date, user_id) DO NOTHING
        """), {"yest": yesterday, "uid": user_id, "today": datetime.now().strftime('%Y-%m-%d')})

    # 5. Final update
    update_daily_snapshot(os.getenv('DB_PATH'), user_id=user_id, force=True)
    print("✓ Calibration complete.")

if __name__ == "__main__":
    calibrate("90693c07-6177-42df-97d9-915f3ce7c573", 191.59, 317.67)
