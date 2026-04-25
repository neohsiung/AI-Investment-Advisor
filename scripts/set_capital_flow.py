#!/usr/bin/env python3
"""
scripts/set_capital_flow.py
────────────────────────────────────────────────────────────────────────────────
P0 Fix: Record real capital inflows as entry_category='capital_flow'.

Usage (one-time bootstrap):
  python scripts/set_capital_flow.py --amount 1500.00 --date 2026-01-01

Usage (replace the existing capital_flow record):
  python scripts/set_capital_flow.py --amount 1750.00 --date 2026-01-01 --replace

Why this exists:
  eToro's public API does not expose cumulative real-money deposits.
  ROI = (NLV - invested_capital) / invested_capital requires a valid
  baseline. This script lets you set that baseline once from your eToro
  "Portfolio" → "Deposits" total shown in the web UI.

  The record is tagged source_file='MANUAL_CAPITAL' so it is clearly
  distinguishable from sync or trade entries.
────────────────────────────────────────────────────────────────────────────────
"""
import argparse
import sys
import os
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from src.data.database import get_db_engine
from src.repositories.transaction_repository import (
    AlchemyTransactionRepository,
    ENTRY_CATEGORY_CAPITAL_FLOW,
)

SOURCE_FILE = "MANUAL_CAPITAL"


def get_primary_user_id(engine) -> str:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT id FROM users ORDER BY created_at ASC LIMIT 1")).fetchone()
        if not row:
            raise RuntimeError("No users found in database.")
        return str(row[0])


def current_capital_flow(engine, user_id: str) -> list:
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT id, trade_date, action, amount, source_file
                FROM transactions
                WHERE user_id = :uid AND entry_category = 'capital_flow'
                ORDER BY trade_date ASC
            """),
            {"uid": user_id},
        ).fetchall()
    return rows


def delete_manual_records(engine, user_id: str) -> int:
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                DELETE FROM transactions
                WHERE user_id = :uid
                  AND entry_category = 'capital_flow'
                  AND source_file = :src
            """),
            {"uid": user_id, "src": SOURCE_FILE},
        )
        return result.rowcount


def main():
    parser = argparse.ArgumentParser(
        description="Set the real invested capital (capital_flow) for ROI calculation."
    )
    parser.add_argument(
        "--amount",
        type=float,
        required=True,
        help="Total real money deposited (USD). Get this from eToro web UI → Portfolio → Deposits.",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Date of the capital injection (YYYY-MM-DD). Defaults to today.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Delete existing MANUAL_CAPITAL records before inserting the new one.",
    )
    parser.add_argument(
        "--user-id",
        type=str,
        default=None,
        help="Target user UUID (defaults to the primary user in the DB).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would happen without making any changes.",
    )
    args = parser.parse_args()

    from datetime import date as date_cls

    deposit_date = args.date or date_cls.today().isoformat()

    engine = get_db_engine()
    user_id = args.user_id or get_primary_user_id(engine)

    print(f"\n{'='*60}")
    print(f"  Capital Flow Setup")
    print(f"{'='*60}")
    print(f"  User        : {user_id}")
    print(f"  Amount      : ${args.amount:,.2f}")
    print(f"  Date        : {deposit_date}")
    print(f"  Replace     : {args.replace}")
    print(f"  Dry-run     : {args.dry_run}")
    print(f"{'='*60}")

    # Show existing records
    existing = current_capital_flow(engine, user_id)
    if existing:
        print(f"\nExisting capital_flow records ({len(existing)} total):")
        for r in existing:
            tag = " ← MANUAL" if r[4] == SOURCE_FILE else ""
            print(f"  [{r[0][:8]}...] {r[1]}  {r[2]:12s}  ${float(r[3]):,.2f}{tag}")
        total = sum(float(r[3]) if r[2] == "DEPOSIT" else -float(r[3]) for r in existing)
        print(f"  Net capital_flow total: ${total:,.2f}")
    else:
        print("\n  No capital_flow records found yet.")

    if args.dry_run:
        print("\n[DRY-RUN] No changes made.")
        return

    # Optionally delete previous MANUAL_CAPITAL records
    if args.replace:
        deleted = delete_manual_records(engine, user_id)
        print(f"\n  Deleted {deleted} existing MANUAL_CAPITAL record(s).")

    # Insert the new capital_flow record
    tx_repo = AlchemyTransactionRepository(engine)
    tx_repo.add(
        user_id=user_id,
        ticker="USD",
        date=deposit_date,
        action="DEPOSIT",
        quantity=1.0,
        price=args.amount,
        fees=0.0,
        leverage=1.0,
        source_file=SOURCE_FILE,
        entry_category=ENTRY_CATEGORY_CAPITAL_FLOW,
        amount=args.amount,
    )

    # Verify
    updated = current_capital_flow(engine, user_id)
    total = sum(float(r[3]) if r[2] == "DEPOSIT" else -float(r[3]) for r in updated)

    print(f"\n✓ Recorded capital_flow: DEPOSIT ${args.amount:,.2f} on {deposit_date}")
    print(f"  Net invested capital (calculate_net_invested_capital): ${total:,.2f}")
    print()
    print("  ROI will now be calculated as:")
    print(f"    ROI = (NLV - ${total:,.2f}) / ${total:,.2f} × 100")
    print()
    print("  To update later: python scripts/set_capital_flow.py --amount <NEW> --replace")


if __name__ == "__main__":
    main()
