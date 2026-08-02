#!/usr/bin/env python3
"""
Agent: Rebalance Worker — Pull-based event processing for rebalancing.

Triggered by Hermes Cron every 15 minutes.
Pulls P0+P1 events from event_queue, evaluates if rebalancing is needed.
Generates a digest notification only when actionable decisions exist.
"""
import sys
import os
import asyncio
import logging
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')
logger = logging.getLogger('agent.rebalance')


async def main():
    user_id = os.environ.get("PAD_USER_ID") or os.environ.get("PRIMARY_USER_ID") or os.environ.get("USER_ID")
    if not user_id:
        from src.repositories.user_repository import AlchemyUserRepository
        user_id = AlchemyUserRepository().get_first_user_id()
    if not user_id:
        logger.error("RebalanceWorker: No user_id configured. Set PAD_USER_ID or PRIMARY_USER_ID env var.")
        return
    
    from src.services.event_aggregator import EventAggregator
    from src.services.settings_service import SettingsService
    from src.services.notification_service import NotificationService
    from src.data.models import EventQueue
    
    aggregator = EventAggregator()
    
    # 1. Check pending events
    summary = aggregator.get_pending_summary(user_id)
    if summary.get("total_pending", 0) == 0:
        logger.info("RebalanceWorker: No pending events — skipping cycle")
        return
    
    logger.info(f"RebalanceWorker: {summary['total_pending']} pending events — {summary['recommended_action']}")
    
    # 2. Pull batch (P0 first, then P1)
    events = aggregator.pull_multi_tier(
        user_id=user_id,
        tiers=[EventQueue.TIER_P0, EventQueue.TIER_P1, EventQueue.TIER_P2],
        max_total=200,
    )
    
    if not events:
        logger.info("RebalanceWorker: No unprocessed events found")
        return
    
    # 3. Check if any events need action
    actionable = [e for e in events 
                  if e.get("tier") in (EventQueue.TIER_P0, EventQueue.TIER_P1)
                  and e.get("content", {}).get("is_actionable")]
    
    has_p0 = any(e.get("tier") == EventQueue.TIER_P0 for e in events)
    event_ids = [e["id"] for e in events]
    
    if not actionable and not has_p0:
        logger.info(f"RebalanceWorker: {len(events)} events inspected, none actionable for rebalance. Leaving in queue for digest.")
        return
    
    # 4. Build digest for actionable events
    digest_lines = [f"🔄 再平衡週期 (Rebalance Cycle) — {datetime.now(timezone.utc).strftime('%H:%M UTC')}"]
    digest_lines.append(f"已處理 {len(events)} 件事件 ({summary['total_pending']} 件待處理)")
    
    for e in events:
        content = e.get("content", {})
        decision = content.get("decision", "")[:200]
        
        title = content.get('title') or content.get('topic') or e['event_type']
        if e["tier"] == EventQueue.TIER_P0:
            digest_lines.append(f"\n🔴 P0 (緊急): {title}")
        elif e["tier"] == EventQueue.TIER_P1:
            digest_lines.append(f"\n🟡 P1 (重要): {title}")
        else:
            digest_lines.append(f"\n⚪ P2 (例行): {title}")
        
        if decision:
            digest_lines.append(f"  {decision[:200].replace(chr(10), ' ')}")
    
    digest_text = "\n".join(digest_lines)
    
    # 5. Send digest notification (only if P0)
    if has_p0:
        try:
            settings_svc = SettingsService(user_id=user_id)
            notification_svc = NotificationService.create_with_settings(
                settings_service=settings_svc, user_id=user_id
            )
            await notification_svc.notify_all(
                user_id=user_id,
                title="🔴 P0 Event — Rebalance Required",
                content=digest_text,
                category="rebalance",
            )
            logger.info(f"RebalanceWorker: Digest sent")
        except Exception as e:
            logger.warning(f"RebalanceWorker: Failed to send digest: {e}")
    else:
        logger.info(f"RebalanceWorker: {len(events)} non-actionable events analyzed (no P0)")
    
    # 6. Mark only actionable/P0 events as analyzed
    actionable_ids = [e["id"] for e in actionable] if actionable else [e["id"] for e in events if e.get("tier") == EventQueue.TIER_P0]
    if actionable_ids:
        aggregator.mark_processed(actionable_ids)
        logger.info(f"RebalanceWorker: marked {len(actionable_ids)} actionable events as analyzed")


if __name__ == "__main__":
    asyncio.run(main())