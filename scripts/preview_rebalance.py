#!/usr/bin/env bash
''':'
exec python3 "$0" "$@"
'''
"""
Autonomous Confidence Rebalance Dry-Run Tool
自主置信度再平衡試算與預覽工具

Usage:
    python scripts/preview_rebalance.py [--user-id <UUID>] [--json]
"""

import sys
import os
import argparse
import asyncio
import json
from decimal import Decimal

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.services.confidence_rebalance_service import ConfidenceRebalanceService
from src.config.owner import resolve_user_id


async def run_preview(user_id: str, json_mode: bool = False):
    resolved_uid = resolve_user_id(user_id)
    rbs = ConfidenceRebalanceService(user_id=resolved_uid)

    try:
        plan = await rbs.get_rebalance_plan()
    except Exception as e:
        print(f"❌ Error generating rebalance plan: {e}", file=sys.stderr)
        sys.exit(1)

    if not plan.get("success"):
        print(f"❌ Rebalance planning returned failure: {plan.get('message', 'Unknown error')}", file=sys.stderr)
        sys.exit(1)

    if json_mode:
        print(json.dumps(plan, indent=2, default=str))
        return

    summary = plan.get("summary", {})
    trades = plan.get("trades", {})
    sells = trades.get("sells", [])
    buys = trades.get("buys", [])

    print("=" * 70)
    print(" 📊 AI 投資組合自主再平衡預覽 (Confidence Rebalance Preview)")
    print("=" * 70)
    print(f" • 目標受託資本 (Tradable Capital) : ${summary.get('total_value', 0):,.2f} USD")
    print(f" • 帳戶當前現金比例 (Cash Weight)   : {plan.get('cash_weight', 0):.2f}%")
    print(f" • 預計執行交易總筆數              : {summary.get('total_trades', 0)} 筆")
    print(f" • 預計賣出標的數                  : {summary.get('sells', 0)} 檔 (預計釋放 ${summary.get('total_sell_amount', 0):,.2f} USD)")
    print(f" • 預計買入標的數                  : {summary.get('buys', 0)} 檔 (預計動用 ${summary.get('total_buy_amount', 0):,.2f} USD)")
    print(f" • 預估調倉後可用現金              : ${summary.get('available_cash', 0):,.2f} USD")
    print("-" * 70)

    if sells:
        print(" 🔻 [先賣後買] 待平倉 / 減持清單 (Sells to free up liquidity):")
        print(f"   {'標的':<8} {'當前權重':<12} {'目標權重':<12} {'調倉幅度':<12} {'預計賣出金額':<15}")
        print("   " + "-" * 62)
        for s in sells:
            t = s["ticker"]
            cw = f"{s['current_weight']:.2f}%"
            tw = f"{s['target_weight']:.2f}%"
            dw = f"{s['delta_weight']:+.2f}%"
            amt = f"${abs(s['delta_amount']):,.2f} USD"
            print(f"   {t:<8} {cw:<12} {tw:<12} {dw:<12} {amt:<15}")
    else:
        print(" 🔻 無需賣出或平倉之標的。")

    print("-" * 70)
    if buys:
        print(" 🔺 待建倉 / 增持清單 (Buys using freed cash):")
        print(f"   {'標的':<8} {'當前權重':<12} {'目標權重':<12} {'調倉幅度':<12} {'預計買入金額':<15}")
        print("   " + "-" * 62)
        for b in buys:
            t = b["ticker"]
            cw = f"{b['current_weight']:.2f}%"
            tw = f"{b['target_weight']:.2f}%"
            dw = f"{b['delta_weight']:+.2f}%"
            amt = f"${b['delta_amount']:,.2f} USD"
            print(f"   {t:<8} {cw:<12} {tw:<12} {dw:<12} {amt:<15}")
    else:
        print(" 🔺 無需買入之標的。")

    print("=" * 70)
    print(" ✅ 提示：本工具僅為試算預覽，未在券商端執行任何實際下單。")
    print("   如欲執行實盤調倉，請透過 API 或等待每週一 09:35 EST 定時任務自動觸發。")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Confidence Rebalance Dry-Run Tool")
    parser.add_argument("--user-id", default=None, help="Target user UUID (default: PRIMARY_USER_ID)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON plan")
    args = parser.parse_args()

    asyncio.run(run_preview(user_id=args.user_id, json_mode=args.json))


if __name__ == "__main__":
    main()
