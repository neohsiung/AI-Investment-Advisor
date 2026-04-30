
# src/api/cost_dashboard_api.py
"""成本儀表板 API 端點"""

from fastapi import APIRouter, Depends, Query
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import sqlalchemy as sa

router = APIRouter(prefix="/api/v1/costs", tags=["cost-dashboard"])

class CostDashboardAPI:
    def __init__(self, db_session):
        self.db = db_session
    
    @router.get("/summary")
    async def get_cost_summary(
        self,
        user_id: str,
        period: str = Query("week", regex="^(week|month)$")
    ) -> Dict:
        """獲取成本摘要"""
        query = """
        SELECT 
            COUNT(*) as total_requests,
            SUM(cost_usd) as total_cost,
            AVG(quality_score) as avg_quality,
            COUNT(CASE WHEN success = true THEN 1 END)::float / COUNT(*) * 100 as success_rate,
            COUNT(CASE WHEN fallback_used = true THEN 1 END)::float / COUNT(*) * 100 as fallback_rate,
            MIN(created_at) as period_start,
            MAX(created_at) as period_end
        FROM request_costs
        WHERE user_id = :user_id
        AND created_at >= NOW() - INTERVAL :days
        """
        
        days = 7 if period == 'week' else 30
        result = self.db.execute(
            sa.text(query),
            {'user_id': user_id, 'days': f'{days} days'}
        ).fetchone()
        
        return {
            'period': period,
            'total_requests': result[0] or 0,
            'total_cost_usd': float(result[1] or 0),
            'avg_quality_score': float(result[2] or 0),
            'success_rate_pct': float(result[3] or 0),
            'fallback_rate_pct': float(result[4] or 0),
            'period_start': result[5],
            'period_end': result[6]
        }
    
    @router.get("/by-tier")
    async def get_cost_by_tier(
        self,
        user_id: str,
        period: str = Query("week", regex="^(week|month)$")
    ) -> Dict[str, float]:
        """按層級獲取成本分佈"""
        query = """
        SELECT tier, SUM(cost_usd) as total, COUNT(*) as count
        FROM request_costs
        WHERE user_id = :user_id
        AND created_at >= NOW() - INTERVAL :days
        GROUP BY tier
        ORDER BY total DESC
        """
        
        days = 7 if period == 'week' else 30
        results = self.db.execute(
            sa.text(query),
            {'user_id': user_id, 'days': f'{days} days'}
        ).fetchall()
        
        return {
            'period': period,
            'breakdown': [
                {
                    'tier': r[0],
                    'cost_usd': float(r[1] or 0),
                    'request_count': r[2],
                    'cost_per_request': float((r[1] or 0) / (r[2] or 1))
                }
                for r in results
            ]
        }
    
    @router.get("/by-provider")
    async def get_cost_by_provider(
        self,
        user_id: str,
        period: str = Query("week", regex="^(week|month)$")
    ) -> Dict:
        """按提供商獲取成本分佈"""
        query = """
        SELECT model_provider, SUM(cost_usd) as total, COUNT(*) as count,
               COUNT(CASE WHEN success = true THEN 1 END)::float / COUNT(*) * 100 as success_rate
        FROM request_costs
        WHERE user_id = :user_id
        AND created_at >= NOW() - INTERVAL :days
        GROUP BY model_provider
        ORDER BY total DESC
        """
        
        days = 7 if period == 'week' else 30
        results = self.db.execute(
            sa.text(query),
            {'user_id': user_id, 'days': f'{days} days'}
        ).fetchall()
        
        return {
            'period': period,
            'breakdown': [
                {
                    'provider': r[0],
                    'cost_usd': float(r[1] or 0),
                    'request_count': r[2],
                    'success_rate_pct': float(r[3] or 0)
                }
                for r in results
            ]
        }
    
    @router.get("/budget-status")
    async def get_budget_status(self, user_id: str) -> Dict:
        """獲取預算狀態"""
        query = """
        SELECT 
            monthly_budget_usd,
            weekly_budget_usd,
            current_week_spent_usd,
            current_month_spent_usd,
            alert_threshold_pct
        FROM user_budgets
        WHERE user_id = :user_id
        """
        
        result = self.db.execute(sa.text(query), {'user_id': user_id}).fetchone()
        
        if not result:
            return {'error': 'User budget not configured'}
        
        monthly_budget, weekly_budget, week_spent, month_spent, alert_threshold = result
        
        return {
            'weekly': {
                'budget_usd': float(weekly_budget),
                'spent_usd': float(week_spent),
                'remaining_usd': float(weekly_budget - week_spent),
                'used_pct': (week_spent / weekly_budget * 100) if weekly_budget > 0 else 0,
                'status': self._get_status(week_spent / weekly_budget * 100, alert_threshold)
            },
            'monthly': {
                'budget_usd': float(monthly_budget),
                'spent_usd': float(month_spent),
                'remaining_usd': float(monthly_budget - month_spent),
                'used_pct': (month_spent / monthly_budget * 100) if monthly_budget > 0 else 0,
                'status': self._get_status(month_spent / monthly_budget * 100, alert_threshold)
            }
        }
    
    @router.get("/trending")
    async def get_cost_trending(
        self,
        user_id: str,
        days: int = Query(30, ge=7, le=90)
    ) -> Dict:
        """獲取成本趨勢 (日粒度)"""
        query = """
        SELECT DATE(created_at) as date,
               SUM(cost_usd) as daily_cost,
               COUNT(*) as request_count,
               AVG(quality_score) as avg_quality
        FROM request_costs
        WHERE user_id = :user_id
        AND created_at >= NOW() - INTERVAL :days
        GROUP BY DATE(created_at)
        ORDER BY date DESC
        """
        
        results = self.db.execute(
            sa.text(query),
            {'user_id': user_id, 'days': f'{days} days'}
        ).fetchall()
        
        return {
            'period_days': days,
            'data': [
                {
                    'date': str(r[0]),
                    'cost_usd': float(r[1] or 0),
                    'request_count': r[2],
                    'avg_quality': float(r[3] or 0)
                }
                for r in results
            ]
        }
    
    @router.get("/model-performance")
    async def get_model_performance(self, user_id: str) -> Dict:
        """獲取模型性能對比"""
        query = """
        SELECT model_provider, model_name, tier,
               COUNT(*) as usage_count,
               AVG(quality_score) as avg_quality,
               COUNT(CASE WHEN success = true THEN 1 END)::float / COUNT(*) * 100 as success_rate,
               AVG(latency_ms) as avg_latency,
               AVG(cost_usd) as avg_cost_per_request
        FROM request_costs
        WHERE user_id = :user_id
        AND created_at >= NOW() - INTERVAL '30 days'
        GROUP BY model_provider, model_name, tier
        ORDER BY usage_count DESC
        """
        
        results = self.db.execute(sa.text(query), {'user_id': user_id}).fetchall()
        
        return {
            'models': [
                {
                    'provider': r[0],
                    'model': r[1],
                    'tier': r[2],
                    'usage_count': r[3],
                    'avg_quality': float(r[4] or 0),
                    'success_rate_pct': float(r[5] or 0),
                    'avg_latency_ms': float(r[6] or 0),
                    'avg_cost_per_request': float(r[7] or 0)
                }
                for r in results
            ]
        }
    
    def _get_status(self, percentage: float, threshold: int) -> str:
        if percentage >= 100:
            return 'critical'
        elif percentage >= threshold:
            return 'alert'
        elif percentage >= 70:
            return 'warning'
        else:
            return 'ok'
