#!/usr/bin/env python3
"""
scripts/backfill_position_lots.py
==================================
One-time script to seed the ``position_lots`` table from existing transaction
history for all users (or a specific user).

Usage:
    # Backfill all users
    python scripts/backfill_position_lots.py

    # Backfill a specific user
    python scripts/backfill_position_lots.py --user-id <user_id>

    # Dry-run (show count without writing)
    python scripts/backfill_position_lots.py --dry-run

This script is idempotent: it deletes existing lots for the target user(s)
before re-seeding, so it is safe to run multiple times.
"""
import argparse
import sys
import os

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.database import get_db_engine
from src.repositories.position_lot_repository import AlchemyPositionLotRepository
from src.utils.logger import setup_logger
from sqlalchemy import text

logger = setup_logger("backfill_position_lots")


def get_all_user_ids(engine) -> list:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id FROM users ORDER BY id")).fetchall()
    return [r[0] for r in rows]


def backfill(user_id: str, lot_repo: AlchemyPositionLotRepository, dry_run: bool = False) -> int:
    """Return number of open lots that were (or would be) created."""
    if dry_run:
        # Run backfill logic but rollback via a dedicated in-memory count
        from src.repositories.transaction_repository import AlchemyTransactionRepository
        tx_repo = AlchemyTransactionRepository(lot_repo.engine)
        transactions = list(reversed(list(tx_repo.get_all_by_user(user_id))))

        SYNTHETIC_PREFIXES = ("STABILIZE", "__ANCHOR_", "NLV_")
        SYNTHETIC_TICKERS = {"CASH", "STABILIZE_CASH", "STABILIZE_CAP", "ETORO_SYNC"}
        open_lots: dict = {}

        for row in transactions:
            ticker = row.ticker
            action = row.action
            qty = float(row.quantity)

            if ticker in SYNTHETIC_TICKERS:
                continue
            if any(ticker.startswith(p) for p in SYNTHETIC_PREFIXES):
                continue

            if action == "BUY":
                open_lots.setdefault(ticker, []).append({"qty": qty})
            elif action == "SELL":
                remaining = qty
                if ticker not in open_lots:
                    continue
                while remaining > 0.0001 and open_lots[ticker]:
                    lot = open_lots[ticker][0]
                    if lot["qty"] <= remaining + 0.0001:
                        remaining -= lot["qty"]
                        open_lots[ticker].pop(0)
                    else:
                        lot["qty"] -= remaining
                        remaining = 0.0

        count = sum(1 for lots in open_lots.values() for l in lots if l["qty"] > 0.0001)
        return count
    else:
        return lot_repo.backfill_from_transactions(user_id)


def main():
    parser = argparse.ArgumentParser(description="Backfill position_lots from transactions.")
    parser.add_argument("--user-id", help="Backfill a specific user only.")
    parser.add_argument("--dry-run", action="store_true", help="Count lots without writing.")
    args = parser.parse_args()

    engine = get_db_engine()
    lot_repo = AlchemyPositionLotRepository(engine)

    if args.user_id:
        user_ids = [args.user_id]
    else:
        user_ids = get_all_user_ids(engine)
        logger.info(f"Found {len(user_ids)} user(s) to backfill.")

    total_lots = 0
    for uid in user_ids:
        count = backfill(uid, lot_repo, dry_run=args.dry_run)
        total_lots += count
        mode = "DRY-RUN" if args.dry_run else "WRITTEN"
        logger.info(f"  user={uid}: {count} open lot(s) [{mode}]")

    suffix = " (dry-run, nothing written)" if args.dry_run else ""
    logger.info(f"Done. Total open lots: {total_lots}{suffix}")


if __name__ == "__main__":
    main()
