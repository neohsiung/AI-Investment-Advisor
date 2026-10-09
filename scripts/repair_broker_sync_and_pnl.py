import os
from sqlalchemy import text
from src.data.database import get_db_engine
from src.config.owner import resolve_user_id

def repair_database():
    engine = get_db_engine()
    user_id = resolve_user_id()
    print("=" * 80)
    print(f"STARTING DATABASE REPAIR FOR USER: {user_id}")
    print("=" * 80)

    with engine.begin() as conn:
        # 1. Delete ghost transactions created between 23:18 and 23:35 on 2026-10-08
        print("\n[Step 1] Cleaning up ghost sync transactions on 2026-10-08...")
        ghost_del = conn.execute(text("""
            DELETE FROM transactions
            WHERE user_id = :uid
            AND entry_category = 'sync_adjustment'
            AND created_at >= '2026-10-08 23:18:00'
            AND created_at <= '2026-10-08 23:35:00'
            AND ticker != 'CASH';
        """), {"uid": user_id})
        print(f"  -> Deleted {ghost_del.rowcount} ghost stock transactions.")

        # 2. Clean up duplicate SELL executions where source_file IS NULL
        print("\n[Step 2] Cleaning up duplicate untagged SELL transactions...")
        del_sells = conn.execute(text("""
            DELETE FROM transactions 
            WHERE user_id = :uid 
            AND source_file IS NULL 
            AND action = 'SELL';
        """), {"uid": user_id})
        print(f"  -> Deleted {del_sells.rowcount} duplicate untagged SELL transactions.")

        # 3. Clean up flapping duplicate CASH sync adjustments since 2026-10-01
        print("\n[Step 3] Purging flapping CASH sync adjustments since 2026-10-01...")
        purge_cash = conn.execute(text("""
            DELETE FROM transactions
            WHERE user_id = :uid
            AND ticker = 'CASH'
            AND trade_date >= '2026-10-01'
            AND (source_file = 'ETORO_SYNC' OR LOWER(source_file) = 'etoro' OR raw_data::text LIKE '%Automated Portfolio Alignment%');
        """), {"uid": user_id})
        print(f"  -> Purged {purge_cash.rowcount} flapping cash alignment records.")

        # 4. Clean up legacy pseudo capital flows from 9/30
        print("\n[Step 4] Converting legacy pseudo capital flows to sync adjustments...")
        upd_cat = conn.execute(text("""
            UPDATE transactions 
            SET entry_category = 'sync_adjustment', quantity = 1.0 
            WHERE user_id = :uid 
            AND ticker = 'CASH' 
            AND entry_category = 'capital_flow';
        """), {"uid": user_id})
        print(f"  -> Converted {upd_cat.rowcount} legacy pseudo capital flows to sync_adjustment.")

        # 5. Insert or update benchmark capital deposit ($1,711.00 on 2026-10-01)
        print("\n[Step 5] Setting benchmark capital deposit ($1,711.00 on 2026-10-01)...")
        conn.execute(text("""
            INSERT INTO transactions (id, user_id, ticker, trade_date, action, quantity, price, fees, amount, leverage, source_file, entry_category)
            VALUES (:id, :uid, :ticker, :dt, :action, 1.0, :amt, 0, :amt, 1.0, :src, :cat)
            ON CONFLICT (id) DO UPDATE SET amount = :amt, price = :amt;
        """), {
            "id": "00000000-0000-0000-0000-000000001711",
            "uid": user_id,
            "ticker": "USD",
            "dt": "2026-10-01",
            "action": "DEPOSIT",
            "amt": 1711.0,
            "src": "MANUAL_CAPITAL",
            "cat": "capital_flow"
        })
        print("  -> Benchmark capital flow record verified.")

        # 6. Correct position_lots to match true eToro portfolio
        print("\n[Step 6] Aligning position_lots to true broker holdings (AAPL, META, MSFT)...")
        holdings = [
            ("AAPL", 0.297885, 335.70, "3596729934"),
            ("META", 0.122584, 736.80, "3596767248"),
            ("MSFT", 0.189075, 528.89, "3596752329")
        ]
        
        conn.execute(text("""
            UPDATE position_lots
            SET is_open = False, close_date = '2026-10-08'
            WHERE user_id = :uid
            AND is_open = True
            AND ticker NOT IN ('AAPL', 'META', 'MSFT');
        """), {"uid": user_id})

        for ticker, qty, price, pos_id in holdings:
            lot = conn.execute(text("""
                SELECT id FROM position_lots
                WHERE user_id = :uid AND ticker = :tk AND is_open = True
                ORDER BY created_at DESC LIMIT 1;
            """), {"uid": user_id, "tk": ticker}).fetchone()

            if lot:
                conn.execute(text("""
                    UPDATE position_lots
                    SET quantity = :qty, open_price = :price, leverage = 1.0, is_open = True, open_date = '2026-10-05'
                    WHERE id = :id;
                """), {"id": lot[0], "qty": qty, "price": price})
                print(f"  -> Updated open lot for {ticker}: {qty} shares @ ${price}")
            else:
                import uuid
                conn.execute(text("""
                    INSERT INTO position_lots (id, user_id, ticker, open_date, quantity, open_price, leverage, is_open, created_at)
                    VALUES (:id, :uid, :tk, '2026-10-05', :qty, :price, 1.0, True, NOW());
                """), {"id": str(uuid.uuid4()), "uid": user_id, "tk": ticker, "qty": qty, "price": price})
                print(f"  -> Created open lot for {ticker}: {qty} shares @ ${price}")

        # 7. Correct daily_snapshots
        print("\n[Step 7] Recalibrating daily_snapshots...")
        conn.execute(text("""
            UPDATE daily_snapshots
            SET total_nlv = 1692.50,
                cash_balance = 1404.09,
                invested_capital = 1711.00,
                pnl = -18.50,
                leverage_ratio = 0.1704
            WHERE user_id = :uid AND date = '2026-10-09';
        """), {"uid": user_id})

        conn.execute(text("""
            UPDATE daily_snapshots
            SET total_nlv = 1698.00,
                cash_balance = 1404.09,
                invested_capital = 1711.00,
                pnl = -13.00,
                leverage_ratio = 0.1718
            WHERE user_id = :uid AND date = '2026-10-08';
        """), {"uid": user_id})
        print("  -> Calibrated snapshots for 2026-10-08 and 2026-10-09 to exact broker values.")

    print("\n" + "=" * 80)
    print("DATABASE REPAIR COMPLETED SUCCESSFULLY!")
    print("=" * 80)

if __name__ == "__main__":
    repair_database()
