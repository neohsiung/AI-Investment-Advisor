#!/usr/bin/env python3
"""
Agent: Report Digest Worker — Generates daily digest from accumulated events.

Triggered by Hermes Cron daily at 09:00.
Pulls all pending events, generates a summary digest, updates knowledge base.
"""
import sys
import os
import asyncio
import logging
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')
logger = logging.getLogger('agent.daily_digest')


async def main():
    user_id = os.environ.get("PAD_USER_ID", "00000000-0000-4000-a000-000000000001")
    
    from src.services.event_aggregator import EventAggregator
    from src.services.settings_service import SettingsService
    from src.services.notification_service import NotificationService
    from src.data.models import EventQueue
    
    aggregator = EventAggregator()
    
    # 1. Pull all pending events from all tiers
    all_tiers = [EventQueue.TIER_P0, EventQueue.TIER_P1, EventQueue.TIER_P2, EventQueue.TIER_P3]
    events = aggregator.pull_multi_tier(
        user_id=user_id, tiers=all_tiers, max_total=200
    )
    
    logger.info(f"DigestWorker: Pulled {len(events)} events for daily digest")
    
    if not events:
        try:
            settings_svc = SettingsService(user_id=user_id)
            notification_svc = NotificationService.create_with_settings(
                settings_service=settings_svc, user_id=user_id
            )
            await notification_svc.notify_all(
                user_id=user_id,
                title="📋 Daily Digest — No Events",
                content="No significant events to report for today.",
                category="daily_digest",
            )
        except Exception as e:
            logger.warning(f"DigestWorker: Failed to send empty digest: {e}")
        return
    
    # 2. Generate daily digest
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    
    p0_events = [e for e in events if e.get("tier") == EventQueue.TIER_P0]
    p1_events = [e for e in events if e.get("tier") == EventQueue.TIER_P1]
    p2_events = [e for e in events if e.get("tier") == EventQueue.TIER_P2]
    p3_events = [e for e in events if e.get("tier") == EventQueue.TIER_P3]
    
    lines = [
        f"📋 Daily Digest — {today}",
        f"━━━━━━━━━━━━━━━━━━━━━",
        f"Events processed: {len(events)} total",
        f"  • P0 Critical: {len(p0_events)}",
        f"  • P1 Important: {len(p1_events)}",
        f"  • P2 Routine: {len(p2_events)}",
        f"  • P3 Reference: {len(p3_events)}",
    ]
    
    if p0_events:
        lines.append(f"\n🔴 Critical Events:")
        for e in p0_events:
            content = e.get("content", {})
            lines.append(f"  • {content.get('source', '?')}: {content.get('topic', '')[:80]}")
    
    if p1_events:
        lines.append(f"\n🟡 Important Events:")
        for e in p1_events:
            content = e.get("content", {})
            decision = content.get("decision", "")[:150]
            lines.append(f"  • {content.get('source', '?')}: {decision}")
    
    if p2_events:
        lines.append(f"\n⚪ Routine:")
        for e in p2_events:
            content = e.get("content", {})
            lines.append(f"  • {content.get('topic', e['event_type'])[:80]}")
    
    digest_text = "\n".join(lines)
    
    # 3. Send daily digest notification
    try:
        settings_svc = SettingsService(user_id=user_id)
        notification_svc = NotificationService.create_with_settings(
            settings_service=settings_svc, user_id=user_id
        )
        await notification_svc.notify_all(
            user_id=user_id,
            title=f"📋 Daily Portfolio Digest — {today}",
            content=digest_text,
            category="daily_digest",
        )
        logger.info(f"DigestWorker: Daily digest sent — {len(events)} events")
    except Exception as e:
        logger.warning(f"DigestWorker: Failed to send digest: {e}")
    
    # 4. Mark all as analyzed
    event_ids = [e["id"] for e in events]
    aggregator.mark_processed(event_ids)
    logger.info(f"DigestWorker: marked {len(event_ids)} events as analyzed")


if __name__ == "__main__":
    asyncio.run(main())