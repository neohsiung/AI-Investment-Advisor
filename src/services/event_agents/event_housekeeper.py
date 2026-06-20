#!/usr/bin/env python3
"""
Housekeeper: Archive old events from event_queue.

Triggered by Hermes Cron daily at 02:00.
Archives events older than 72 hours to keep the queue lean.
"""
import sys
import os
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')
logger = logging.getLogger('housekeeper')


def main():
    from src.services.event_aggregator import EventAggregator
    aggregator = EventAggregator()
    archived = aggregator.repo.archive_old_events(older_than_hours=72)
    logger.info(f"Housekeeper: archived {archived} events")


if __name__ == "__main__":
    main()