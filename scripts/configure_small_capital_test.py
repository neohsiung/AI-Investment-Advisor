#!/usr/bin/env python3
"""
Configure the settings for the $100 live test. Idempotent, prints a diff.
設定 $100 實測所需的參數；具冪等性並列出前後差異。

Run:
    python scripts/configure_small_capital_test.py            # dry run
    python scripts/configure_small_capital_test.py --apply    # write

Why a script rather than SQL / why these values
───────────────────────────────────────────────
eToro's minimum order is $10. Against $100 of tradable capital that is only
ten units of resolution, and the interaction with the defaults is a trap:

  max_single_position_pct defaults to 0.10 (automated_trading_service.py)
  → every position caps at $100 x 0.10 = $10
  → which is EXACTLY min_trade_amount ($10)
  → so any downward clamp (available cash, rounding to 2dp) lands below $10
  → and the order is skipped entirely: "Amount $X below minimum"

The system would evaluate signals, pass every threshold, and then quietly
place nothing. Raising the cap to 0.20 gives a $20 target with 2x of clamp
headroom, and 4 positions x $20 = $80 sits correctly alongside the existing
target_cash_ratio of 0.2 ($20 cash).

eToro 最小單為 $10，相對 $100 只有十格解析度，而預設值會構成陷阱：
max_single_position_pct 預設 0.10 → 每筆上限剛好 $10 = 最小單，任何往下鉗制
都會跌破門檻而整筆略過。系統會評估、過門檻、然後安靜地什麼都不下。
改為 0.20（每筆 $20）留兩倍餘裕，4 x $20 = $80，與現有 20% 現金水位相符。
"""
import argparse
import sys
from pathlib import Path

# `scripts/` is not bind-mounted into the containers (only src/ and prompts/),
# and the DB host `postgres` only resolves on the docker network — so this is
# normally run by piping it in:
#   docker exec -i advisor_prod_worker_1 python - --apply < this_file
# In that mode there is no __file__, and cwd (/workspace) is already on the
# path, so the repo-root insert is skipped rather than crashing.
# scripts/ 未掛載進容器（只有 src/ 與 prompts/），且 DB 主機名 postgres 僅在
# docker 網路內可解析，故通常以管道方式執行；該模式下沒有 __file__，而 cwd
# 已在路徑上，因此跳過而非拋錯。
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
except NameError:
    pass

# key -> (value, why this value)
TARGET_SETTINGS = {
    "tradable_capital_usd": (
        100,
        "Hard ceiling on what the loop may deploy. Account NLV is ~$1,048; "
        "this is the only number to change when scaling up.",
    ),
    "max_single_position_pct": (
        0.20,
        "$20 per position. MUST be above 0.10 — at 0.10 the cap equals eToro's "
        "$10 minimum and every clamped order gets skipped.",
    ),
    "min_trade_amount": (
        10,
        "eToro's minimum order size. Stated explicitly so it is not an "
        "invisible code default during a live-money test.",
    ),
    "auto_trade_threshold_sell": (
        60,
        "6.0/10 auto-executes a SELL, vs 7.5 for BUY. Not buying only costs "
        "upside; not selling can compound a loss.",
    ),
    "small_test_capital_usd": (
        100,
        "At or below this tradable capital the backtest gate is waived. "
        "Raising tradable_capital_usd past it re-arms the gate automatically.",
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    parser.add_argument("--user-id", default=None, help="target user id (default: first user)")
    args = parser.parse_args()

    from src.repositories.settings_repository import AlchemySettingsRepository
    from sqlalchemy import text

    repo = AlchemySettingsRepository()

    user_id = args.user_id
    if not user_id:
        with repo.engine.connect() as conn:
            row = conn.execute(
                text("SELECT id FROM users ORDER BY created_at ASC LIMIT 1")
            ).fetchone()
        if not row:
            print("No users found; cannot configure settings.", file=sys.stderr)
            return 1
        user_id = str(row[0])

    print(f"user_id: {user_id}")
    print(f"mode   : {'APPLY' if args.apply else 'DRY RUN (use --apply to write)'}\n")

    changes = []
    for key, (want, why) in TARGET_SETTINGS.items():
        try:
            current = repo.get(user_id, key)
        except Exception as e:
            print(f"  ! {key}: read failed ({e})")
            continue

        same = current is not None and str(current) == str(want)
        marker = "=" if same else ">"
        print(f"  {marker} {key}: {current!r} -> {want!r}")
        print(f"      {why}")
        if not same:
            changes.append((key, want))

    if not changes:
        print("\nNothing to change; already configured.")
        return 0

    if not args.apply:
        print(f"\n{len(changes)} setting(s) would change. Re-run with --apply to write.")
        return 0

    for key, want in changes:
        repo.set(user_id, key, want)
    print(f"\nWrote {len(changes)} setting(s).")

    print("\nVerifying:")
    for key, (want, _) in TARGET_SETTINGS.items():
        print(f"  {key} = {repo.get(user_id, key)!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
