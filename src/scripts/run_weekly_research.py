#!/usr/bin/env python3
"""
Weekly Research Automation — CLI entry point for cron jobs.
Runs full research cycle on all active tickers via ResearchAutomationService.

Usage:
    python3 src/scripts/run_weekly_research.py --user_id <UUID>

This is called by SchedulerService.job_weekly_research() every Sunday at 09:00.
"""

import sys
import os
import asyncio
import argparse
import logging

# Ensure project root is in sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.services.research_automation_service import ResearchAutomationService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_weekly_research")


async def main():
    parser = argparse.ArgumentParser(description="Run weekly ticker research")
    parser.add_argument("--user_id", required=True, help="User UUID")
    parser.add_argument("--ticker", help="Optional single ticker (skip full cycle)")
    args = parser.parse_args()

    svc = ResearchAutomationService(user_id=args.user_id)

    if args.ticker:
        logger.info(f"🔬 Running research on single ticker: {args.ticker}")
        result = await svc.run_ticker_research(args.ticker)
        print(f"Result: {result}")
        return

    logger.info("🚀 Starting weekly research cycle...")
    result = await svc.run_weekly_research(parallel=2)

    total = result["total"]
    researched = result["researched"]
    errors = result["errors"]
    candidates = result["removal_candidates"]

    logger.info(f"✅ Research cycle complete: {researched}/{total} tickers, {errors} errors")
    logger.info(f"⚠️  Removal candidates: {len(candidates)}")

    for c in candidates:
        logger.warning(f"  ⛔ {c['ticker']}: {c['reason']} — {c.get('detail', '')}")

    # Return structured output for Hermes cron delivery
    summary = (
        f"Weekly Research Cycle Results:\n"
        f"• Researched: {researched}/{total} tickers\n"
        f"• Errors: {errors}\n"
        f"• Removal candidates: {len(candidates)}\n"
    )
    if candidates:
        summary += "\nRemoval candidates:\n"
        for c in candidates:
            summary += f"  • {c['ticker']}: {c['reason']}\n"

    print(f"\n{summary}")
    return summary


if __name__ == "__main__":
    summary = asyncio.run(main())
    print(summary)
