
# src/alerts/cost_alert_system.py
"""成本告警系統"""

import asyncio
from typing import Dict, List
from datetime import datetime
from enum import Enum
import httpx

class AlertLevel(str, Enum):
    WARNING = "warning"      # 70%
    ALERT = "alert"          # 85%
    CRITICAL = "critical"    # 100%

class AlertChannel(str, Enum):
    SLACK = "slack"
    EMAIL = "email"
    WEBHOOK = "webhook"

class CostAlertSystem:
    def __init__(self, config: Dict):
        self.config = config
        self.alert_history = {}
    
    async def check_and_alert(self, user_id: str, budget_status: Dict):
        """檢查預算狀態並發送告警"""
        
        weekly_status = budget_status.get('weekly', {})
        weekly_pct = weekly_status.get('used_pct', 0)
        weekly_budget = weekly_status.get('budget_usd', 0)
        
        # 確定告警級別
        alert_level = None
        if weekly_pct >= 100:
            alert_level = AlertLevel.CRITICAL
        elif weekly_pct >= 85:
            alert_level = AlertLevel.ALERT
        elif weekly_pct >= 70:
            alert_level = AlertLevel.WARNING
        
        if alert_level:
            await self._send_alert(user_id, alert_level, budget_status)
    
    async def _send_alert(self, user_id: str, level: AlertLevel, budget_status: Dict):
        """發送告警到多個渠道"""
        alert_message = self._format_alert_message(user_id, level, budget_status)
        
        # 並行發送到所有配置的渠道
        tasks = []
        
        if 'slack' in self.config:
            tasks.append(self._send_slack_alert(alert_message, level))
        
        if 'email' in self.config:
            tasks.append(self._send_email_alert(alert_message, level, user_id))
        
        if 'webhook' in self.config:
            tasks.append(self._send_webhook_alert(alert_message, level))
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _send_slack_alert(self, message: Dict, level: AlertLevel):
        """發送到 Slack"""
        color_map = {
            AlertLevel.WARNING: '#FFA500',
            AlertLevel.ALERT: '#FF6B6B',
            AlertLevel.CRITICAL: '#FF0000'
        }
        
        emoji_map = {
            AlertLevel.WARNING: '⚠️',
            AlertLevel.ALERT: '🚨',
            AlertLevel.CRITICAL: '🆘'
        }
        
        payload = {
            'text': f"{emoji_map[level]} 成本預算告警",
            'attachments': [
                {
                    'color': color_map[level],
                    'title': message['title'],
                    'text': message['body'],
                    'fields': [
                        {'title': 'Weekly Budget', 'value': f"\${message['weekly_budget']:.2f}", 'short': True},
                        {'title': 'Current Spend', 'value': f"\${message['weekly_spent']:.2f}", 'short': True},
                        {'title': 'Usage', 'value': f"{message['usage_pct']:.1f}%", 'short': True},
                        {'title': 'Remaining', 'value': f"\${message['remaining']:.2f}", 'short': True}
                    ],
                    'ts': int(datetime.now().timestamp())
                }
            ]
        }
        
        async with httpx.AsyncClient() as client:
            await client.post(
                self.config['slack']['webhook_url'],
                json=payload
            )
    
    async def _send_email_alert(self, message: Dict, level: AlertLevel, user_id: str):
        """發送郵件告警"""
        # 實現：使用 SendGrid 或 SMTP
        pass
    
    async def _send_webhook_alert(self, message: Dict, level: AlertLevel):
        """發送到自定義 webhook"""
        async with httpx.AsyncClient() as client:
            await client.post(
                self.config['webhook']['url'],
                json={
                    'level': level.value,
                    'alert': message,
                    'timestamp': datetime.now().isoformat()
                }
            )
    
    def _format_alert_message(self, user_id: str, level: AlertLevel, budget_status: Dict) -> Dict:
        """格式化告警消息"""
        weekly = budget_status.get('weekly', {})
        level_name_map = {
            AlertLevel.WARNING: '警告',
            AlertLevel.ALERT: '嚴重',
            AlertLevel.CRITICAL: '嚴重 - 預算已超限'
        }
        
        return {
            'title': f"成本預算 {level_name_map[level]}",
            'body': f"用戶 {user_id} 本週預算已使用 {weekly.get('used_pct', 0):.1f}%",
            'weekly_budget': weekly.get('budget_usd', 0),
            'weekly_spent': weekly.get('spent_usd', 0),
            'usage_pct': weekly.get('used_pct', 0),
            'remaining': weekly.get('remaining_usd', 0),
            'level': level.value,
            'timestamp': datetime.now().isoformat()
        }
    
    async def send_weekly_report(self, user_id: str, review_data: Dict):
        """發送週期性成本審查報告"""
        report_message = self._format_weekly_report(user_id, review_data)
        
        async with httpx.AsyncClient() as client:
            await client.post(
                self.config['slack']['webhook_url'],
                json=report_message
            )
    
    def _format_weekly_report(self, user_id: str, review_data: Dict) -> Dict:
        """格式化週報告"""
        return {
            'text': '📊 HRM 每週成本審查報告',
            'attachments': [
                {
                    'color': '#36a64f',
                    'title': f"Week {review_data.get('review_week')} 成本審查",
                    'fields': [
                        {'title': '總請求', 'value': f"{review_data.get('total_requests', 0)}", 'short': True},
                        {'title': '總成本', 'value': f"\${review_data.get('total_cost_usd', 0):.2f}", 'short': True},
                        {'title': '成功率', 'value': f"{review_data.get('success_rate_pct', 0):.1f}%", 'short': True},
                        {'title': '質量分數', 'value': f"{review_data.get('avg_quality_score', 0):.1f}/10", 'short': True}
                    ]
                }
            ]
        }
