
# src/scheduler/weekly_cost_review_db.py
"""週期性成本審查 - DB 集成版本"""

from datetime import datetime, timedelta
import json
from typing import Dict, List

class WeeklyCostReviewDB:
    """基於 DB 的週期性成本審查"""
    
    def __init__(self, db_session, router, cost_tracker):
        self.db = db_session
        self.router = router
        self.tracker = cost_tracker
    
    async def run_weekly_review(self, user_id: str):
        """執行用戶的週期性審查"""
        week_num = datetime.now().isocalendar()[1]
        year = datetime.now().year
        
        # 1. 收集本週數據
        cost_summary = await self.tracker.get_user_cost_summary(user_id, 'week')
        cost_by_tier = await self.tracker.get_cost_by_tier(user_id, 'week')
        cost_by_provider = await self.tracker.get_cost_by_provider(user_id, 'week')
        
        # 2. 生成建議
        recommendations = self._generate_recommendations(
            cost_summary, cost_by_tier, cost_by_provider
        )
        
        # 3. 確定預算狀態
        budget_status = self._check_budget_status(user_id, cost_summary['total_cost_usd'])
        
        # 4. 插入審查日誌
        review_id = str(uuid.uuid4())
        query = """
        INSERT INTO cost_review_logs
        (id, user_id, review_week, review_year, total_requests, total_cost_usd,
         cost_by_tier, cost_by_provider, fallback_frequency_pct, success_rate_pct,
         avg_quality_score, recommendations, budget_status)
        VALUES (:id, :user_id, :week, :year, :requests, :cost,
                :tier_costs, :provider_costs, :fallback, :success,
                :quality, :recommendations, :status)
        """
        
        self.db.execute(sa.text(query), {
            'id': review_id,
            'user_id': user_id,
            'week': week_num,
            'year': year,
            'requests': cost_summary['request_count'],
            'cost': cost_summary['total_cost_usd'],
            'tier_costs': json.dumps(cost_by_tier),
            'provider_costs': json.dumps(cost_by_provider),
            'fallback': cost_summary['fallback_frequency_pct'],
            'success': cost_summary['success_rate_pct'],
            'quality': cost_summary['avg_quality_score'],
            'recommendations': json.dumps(recommendations),
            'status': budget_status
        })
        self.db.commit()
        
        # 5. 嘗試應用優化
        if recommendations.get('update_recommended'):
            await self._apply_optimizations(user_id, recommendations)
        
        return review_id
    
    def _generate_recommendations(self, summary: Dict, by_tier: Dict, by_provider: Dict) -> Dict:
        """生成成本優化建議"""
        recommendations = {
            'update_recommended': False,
            'changes': [],
            'optimization_potential': 0.0
        }
        
        # 分析 Fallback 使用
        if summary['fallback_frequency_pct'] > 20:
            recommendations['changes'].append({
                'type': 'high_fallback_usage',
                'detail': f"Fallback 使用頻率 {summary['fallback_frequency_pct']:.1f}% (閾值 20%)",
                'action': '檢查主模型可用性或增加速率限制'
            })
        
        # 分析按層成本分佈
        total_cost = summary['total_cost_usd']
        for tier, cost in by_tier.items():
            pct = (cost / total_cost * 100) if total_cost > 0 else 0
            # 如果某層超過預算，建議調整
            if pct > 50:
                recommendations['changes'].append({
                    'type': 'tier_overallocation',
                    'tier': tier,
                    'percentage': pct,
                    'action': f"考慮為 {tier} 使用更便宜的模型"
                })
        
        # 分析提供商成本
        free_cost = by_provider.get('ollama', 0) + by_provider.get('nvidia_nim', 0)
        paid_cost = by_provider.get('openrouter', 0)
        free_pct = (free_cost / (free_cost + paid_cost) * 100) if (free_cost + paid_cost) > 0 else 0
        
        if free_pct < 50:
            recommendations['changes'].append({
                'type': 'low_free_model_usage',
                'detail': f"免費模型使用率 {free_pct:.1f}% (目標 60%)",
                'action': '增加 Ollama 和 NIM 使用，減少 OpenRouter 依賴'
            })
            recommendations['optimization_potential'] = (60 - free_pct) * paid_cost / 100
        
        if recommendations['changes']:
            recommendations['update_recommended'] = len(recommendations['changes']) > 0
        
        return recommendations
    
    def _check_budget_status(self, user_id: str, total_cost: float) -> str:
        """檢查預算狀態"""
        query = """
        SELECT weekly_budget_usd FROM user_budgets WHERE user_id = :user_id
        """
        result = self.db.execute(sa.text(query), {'user_id': user_id}).fetchone()
        
        if not result:
            return 'unknown'
        
        weekly_budget = result[0]
        pct = (total_cost / weekly_budget * 100) if weekly_budget > 0 else 0
        
        if pct >= 100:
            return 'critical'
        elif pct >= 85:
            return 'alert'
        elif pct >= 70:
            return 'warning'
        else:
            return 'ok'
    
    async def _apply_optimizations(self, user_id: str, recommendations: Dict):
        """應用推薦的優化"""
        # 實現：更新 model_routing 配置
        pass
