from src.repositories.snapshot_repository import SqliteSnapshotRepository
from src.analytics import PnLCalculator, update_daily_snapshot

class AnalyticsService:
    def __init__(self, db_path="data/portfolio.db", user_id=None, repository=None):
        self.db_path = db_path
        self.user_id = user_id
        self.snapshot_repo = repository or SqliteSnapshotRepository(db_path)
        self.pnl_calculator = PnLCalculator(db_path)

    def trigger_snapshot_update(self):
        """Manually trigger a snapshot update."""
        if self.user_id:
            update_daily_snapshot(self.db_path, self.user_id)

    def get_pnl_breakdown(self, current_prices):
        """Calculate PnL Breakdown."""
        if not self.user_id:
            return None
        return self.pnl_calculator.calculate_breakdown(current_prices, self.user_id)

    def get_performance_history(self):
        """Get historical performance data (snapshots)."""
        if not self.user_id:
            return None
        return self.snapshot_repo.get_history_by_user(self.user_id)

    def get_latest_performance(self):
        """Get latest performance data."""
        if not self.user_id:
            return None
        return self.snapshot_repo.get_latest_by_user(self.user_id)
