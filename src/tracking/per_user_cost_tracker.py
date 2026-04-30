
# src/tracking/per_user_cost_tracker.py
"""Per-user 成本追蹤與預算管理"""

import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional, List
import sqlalchemy as sa
from sqlalchemy.orm import Session

class PerUserCostTracker:
    """追蹤每個用戶的成本使用"""
    
    def __init__(self, db_session: Session):
        self.db = db_session
    
    async def record_request_cost(self, user_id: str, request_data: Dict) -> str:
        """記錄單個請求成本"""
        cost_id = str(uuid.uuid4())
        
        cost_record = {
            'id': cost_id,
            'user_id': user_id,
            'request_id': request_data.get('request_id'),
            'tier': request_data.get('tier'),
            'model_provider': request_data.get('provider'),
            'model_name': request_data.get('model'),
            'fallback_used': request_data.get('fallback', False),
            'fallback_priority': request_data.get('fallback_priority'),
            'input_tokens': request_data.get('input_tokens', 0),
            'output_tokens': request_data.get('output_tokens', 0),
            'cost_usd': request_data.get('cost_usd', 0.0),
            'success': request_data.get('success', True),
            'latency_ms': request_data.get('latency_ms'),
            'quality_score': request_data.get('quality_score'),
            'created_at': datetime.utcnow()
        }
        
        # 插入DB
        query = """
        INSERT INTO request_costs 
        (id, user_id, request_id, tier, model_provider, model_name,
         fallback_used, fallback_priority, input_tokens, output_tokens,
         cost_usd, success, latency_ms, quality_score, created_at)
        VALUES (:id, :user_id, :request_id, :tier, :model_provider, :model_name,
                :fallback_used, :fallback_priority, :input_tokens, :output_tokens,
                :cost_usd, :success, :latency_ms, :quality_score, :created_at)
        """
        self.db.execute(sa.text(query), cost_record)
        self.db.commit()
        
        # 更新用戶預算
        await self._update_user_budget(user_id, request_data.get('cost_usd', 0.0))
        
        # 檢查預算告警
        await self._check_budget_alerts(user_id)
        
        return cost_id
    
    async def _update_user_budget(self, user_id: str, cost_usd: float):
        """更新用戶當週和當月成本"""
        query = """
        UPDATE user_budgets 
        SET current_week_spent_usd = current_week_spent_usd + :cost,
            current_month_spent_usd = current_month_spent_usd + :cost,
            updated_at = NOW()
        WHERE user_id = :user_id
        """
        self.db.execute(sa.text(query), {'user_id': user_id, 'cost': cost_usd})
        self.db.commit()
    
    async def _check_budget_alerts(self, user_id: str):
        """檢查預算告警條件"""
        query = """
        SELECT weekly_budget_usd, current_week_spent_usd, alert_threshold_pct, hard_limit_enabled
        FROM user_budgets
        WHERE user_id = :user_id
        """
        result = self.db.execute(sa.text(query), {'user_id': user_id}).fetchone()
        
        if not result:
            return
        
        weekly_budget, spent, threshold, hard_limit = result
        percentage = (spent / weekly_budget * 100) if weekly_budget > 0 else 0
        
        if percentage >= 100 and hard_limit:
            await self._trigger_hard_limit(user_id)
        elif percentage >= threshold:
            await self._trigger_alert(user_id, percentage)
    
    async def _trigger_hard_limit(self, user_id: str):
        """觸發硬限制 - 拒絕付費請求"""
        # 實現：後續請求只能使用免費模型 (Ollama, NIM)
        pass
    
    async def _trigger_alert(self, user_id: str, percentage: float):
        """發送預算告警"""
        # 實現：發送 Slack/Email 通知
        pass
    
    async def get_user_cost_summary(self, user_id: str, period: str = 'week') -> Dict:
        """获取用戶成本摘要"""
        if period == 'week':
            query = """
            SELECT 
                SUM(cost_usd) as total_cost,
                COUNT(*) as request_count,
                AVG(quality_score) as avg_quality,
                COUNT(CASE WHEN success = true THEN 1 END) / COUNT(*) * 100 as success_rate_pct,
                COUNT(CASE WHEN fallback_used = true THEN 1 END) as fallback_count,
                COUNT(CASE WHEN fallback_used = true THEN 1 END) / COUNT(*) * 100 as fallback_pct
            FROM request_costs
            WHERE user_id = :user_id
            AND created_at >= NOW() - INTERVAL '7 days'
            """
        else:  # month
            query = query.replace("7 days", "30 days")
        
        result = self.db.execute(sa.text(query), {'user_id': user_id}).fetchone()
        
        return {
            'period': period,
            'total_cost_usd': result[0] or 0.0,
            'request_count': result[1] or 0,
            'avg_quality_score': result[2] or 0.0,
            'success_rate_pct': result[3] or 0.0,
            'fallback_count': result[4] or 0,
            'fallback_frequency_pct': result[5] or 0.0
        }
    
    async def get_cost_by_tier(self, user_id: str, period: str = 'week') -> Dict[str, float]:
        """按層級獲取成本"""
        query = """
        SELECT tier, SUM(cost_usd) as total_cost
        FROM request_costs
        WHERE user_id = :user_id
        AND created_at >= NOW() - INTERVAL :days
        GROUP BY tier
        """
        
        days = 7 if period == 'week' else 30
        result = self.db.execute(
            sa.text(query), 
            {'user_id': user_id, 'days': f'{days} days'}
        ).fetchall()
        
        return {row[0]: row[1] for row in result}
    
    async def get_cost_by_provider(self, user_id: str, period: str = 'week') -> Dict[str, float]:
        """按提供商獲取成本"""
        query = """
        SELECT model_provider, SUM(cost_usd) as total_cost
        FROM request_costs
        WHERE user_id = :user_id
        AND created_at >= NOW() - INTERVAL :days
        GROUP BY model_provider
        """
        
        days = 7 if period == 'week' else 30
        result = self.db.execute(
            sa.text(query), 
            {'user_id': user_id, 'days': f'{days} days'}
        ).fetchall()
        
        return {row[0]: row[1] for row in result}
    
    async def initialize_user_budget(self, user_id: str, monthly_budget: float = 129.0):
        """初始化用戶預算追蹤"""
        budget_id = str(uuid.uuid4())
        
        query = """
        INSERT INTO user_budgets
        (id, user_id, monthly_budget_usd, weekly_budget_usd, tier_allocation)
        VALUES (:id, :user_id, :monthly, :weekly, :allocation)
        ON CONFLICT (user_id) DO NOTHING
        """
        
        tier_allocation = {
            'DeepResearch': monthly_budget * 0.40 / 4,
            'MemoryDig': monthly_budget * 0.35 / 4,
            'FastThink': monthly_budget * 0.20 / 4,
            'Reflexive': monthly_budget * 0.05 / 4
        }
        
        self.db.execute(sa.text(query), {
            'id': budget_id,
            'user_id': user_id,
            'monthly': monthly_budget,
            'weekly': monthly_budget / 4,
            'allocation': json.dumps(tier_allocation)
        })
        self.db.commit()
