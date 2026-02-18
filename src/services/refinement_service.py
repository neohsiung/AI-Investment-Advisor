import logging
from datetime import datetime
from src.agents.engineer import SystemEngineerAgent
from src.services.performance_service import PerformanceService
from src.services.notification_service import NotificationService
from src.utils.logger import setup_logger

class RefinementService:
    """
    Service for monthly system refinement (HR Protocol).
    月度系統進化服務 (HR 協議)。
    """
    def __init__(self, user_id: str = None, settings_service: Any = None, notification_service: Optional[NotificationService] = None) -> None:
        """
        Initialize the refinement service.
        初始化進化服務。
        """
        self.logger = setup_logger("RefinementService")
        self.user_id = user_id
        self.perf_service = PerformanceService()
        self.engineer = SystemEngineerAgent(user_id=self.user_id)
        
        # Create notification service with user_id
        if notification_service:
            self.notification_service = notification_service
        else:
            if not settings_service:
                from src.services.settings_service import SettingsService
                settings_service = SettingsService(user_id=self.user_id)
            self.notification_service = NotificationService.create_with_settings(settings_service, user_id=self.user_id)

    async def run_monthly_refinement(self) -> bool:
        """
        Execute the monthly performance review and system optimization cycle asynchronously.
        執行月度效能回顧與系統優化週期（非同步）。
        """
        self.logger.info(f"Starting Monthly Refinement for {self.user_id}...")
        
        try:
            # 1. Performance Review
            stats = self.perf_service.get_agent_performance()
            
            # 2. Merge and Normalize Stats
            target_agents = ["CIO", "Momentum", "Fundamental", "Macro", "Sentiment"]
            merged_stats = self._merge_stats(stats, target_agents)
            
            # 3. Engineer Analysis (HR View)
            hr_context = {
                "cio_report": "HR_PROTOCOL_INITIATED",
                "performance_stats": merged_stats,
                "task": "Generate Monthly System Evolution Report"
            }
            optimizations = self.engineer.run(hr_context)
            
            # 4. Generate Report
            report_content = self._generate_report(merged_stats, optimizations, target_agents)
            
            # 5. Send Report via Unified Channels
            await self.notification_service.send_report("月度系統進化報告 (System Evolution Report)", report_content)
            self.logger.info("Monthly Refinement Report sent successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Monthly Refinement Failed: {e}")
            return False

    def _merge_stats(self, stats: dict, target_agents: list) -> dict:
        merged_stats = {agent: {"wins": 0, "count": 0} for agent in target_agents}
        if not isinstance(stats, dict):
            return merged_stats

        for agent, data in stats.items():
            match_key = None
            for target in target_agents:
                if target.lower() == agent.lower():
                    match_key = target
                    break
            
            if not match_key:
                match_key = agent.title()
                if match_key not in merged_stats:
                    merged_stats[match_key] = {"wins": 0, "count": 0}
            
            count = data.get('count', 0)
            win_rate = data.get('win_rate', 0.0)
            merged_stats[match_key]["count"] += count
            merged_stats[match_key]["wins"] += (win_rate * count)
            
        return merged_stats

    def _generate_report(self, merged_stats: dict, optimizations: list, target_agents: list) -> str:
        stats_md = "\n| Agent (分析師) | Win Rate (勝率) | Count (次數) | Status (狀態) |\n|---|---|---|---|\n"
        display_order = [a for a in target_agents if a in merged_stats] + [a for a in merged_stats if a not in target_agents]
        
        for agent in display_order:
            data = merged_stats[agent]
            count = data["count"]
            wins = data["wins"]
            win_rate = wins / count if count > 0 else 0.0
            
            if count < 5:
                status = "⚪️ 數據不足"
            elif win_rate >= 0.6:
                status = "🟢 優異"
            elif win_rate <= 0.4:
                status = "🔴 待優化"
            else:
                status = "🟡 正常"
            
            stats_md += f"| {agent} | {win_rate:.1%} | {count} | {status} |\n"

        report = f"""# 月度系統進化報告 (System Evolution Report)
日期: {datetime.now().strftime('%Y-%m-%d')}

## 1. 效能概覽 (Performance Overview)
{stats_md}

## 2. 優化行動 (APO Cycle)
"""
        if optimizations:
            for opt in optimizations:
                if "error" in opt:
                    report += f"- [錯誤] {opt['error']}\n"
                else:
                    report += f"- [已優化] {opt.get('target_agent', 'Unknown')}: {opt.get('reason', 'N/A')}\n"
        else:
            report += "- 系統運作正常，未觸發關鍵優化。\n"
            
        return report
