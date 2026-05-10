"""
Per-request cost attribution and tracking framework.
Each request is tracked with its token usage, model, and calculated cost.
"""

from dataclasses import dataclass, asdict
from typing import Dict, Optional, List, Any
from datetime import datetime
import uuid
import logging
import json

logger = logging.getLogger("CostAttribution")


@dataclass
class RequestCostRecord:
    """Record of costs for a single LLM request."""
    
    request_id: str
    user_id: str
    agent_name: str
    cognitive_layer: str                    # "nano", "fast", "smart", "advanced"
    model_used: str                         # Actual model (e.g., "claude-3-sonnet")
    provider: str                           # "OpenRouter", "Anthropic", etc.
    input_tokens: int
    output_tokens: int
    total_tokens: int
    input_cost_usd: float
    output_cost_usd: float
    total_cost_usd: float
    request_text: str
    response_text: Optional[str]
    timestamp: datetime
    duration_seconds: float
    cache_hit: bool = False
    metadata: Optional[Dict] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "request_id": self.request_id,
            "user_id": self.user_id,
            "agent_name": self.agent_name,
            "cognitive_layer": self.cognitive_layer,
            "model_used": self.model_used,
            "provider": self.provider,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "input_cost_usd": self.input_cost_usd,
            "output_cost_usd": self.output_cost_usd,
            "total_cost_usd": self.total_cost_usd,
            "request_text": self.request_text[:2000],  # Truncate for storage
            "response_text": (self.response_text[:2000] if self.response_text else None),
            "timestamp": self.timestamp,
            "duration_seconds": self.duration_seconds,
            "cache_hit": self.cache_hit,
            "metadata": self.metadata or {}
        }


class CostAttributionService:
    """
    Service for tracking per-request costs and generating optimization insights.
    
    Responsibilities:
    - Record each LLM request with token counts and calculated costs
    - Store records to database for historical analysis
    - Generate weekly/monthly cost breakdowns
    - Identify optimization opportunities
    """
    
    def __init__(self, engine=None, tier_config=None):
        """
        Initialize attribution service.
        
        Args:
            engine: SQLAlchemy engine (optional, uses default if None)
            tier_config: TierConfig instance (optional, uses default if None)
        """
        if engine is None:
            from src.data.database import get_db_engine
            engine = get_db_engine()
        if tier_config is None:
            from src.infrastructure.llm.tier_config import TierConfig
            tier_config = TierConfig()
        
        self.engine = engine
        self.tier_config = tier_config
    
    def record_request(
        self,
        user_id: str,
        agent_name: str,
        cognitive_layer: str,
        model_used: str,
        provider: str,
        input_tokens: int,
        output_tokens: int,
        request_text: str,
        response_text: Optional[str] = None,
        duration_seconds: float = 0.0,
        cache_hit: bool = False,
        metadata: Optional[Dict] = None,
    ) -> RequestCostRecord:
        """
        Record a completed LLM request with cost calculation.
        
        Args:
            user_id: User identifier
            agent_name: Agent making the call
            cognitive_layer: Assigned layer (nano, fast, smart, advanced)
            model_used: Actual model name
            provider: LLM provider
            input_tokens: Prompt tokens
            output_tokens: Completion tokens
            request_text: Original user request
            response_text: LLM response (optional)
            duration_seconds: Request latency
            cache_hit: Whether cached
            metadata: Additional context
        
        Returns:
            RequestCostRecord with calculated costs
        """
        # Calculate costs based on tier pricing
        spec = self.tier_config.get_spec(cognitive_layer)
        input_cost = 0.0
        output_cost = 0.0
        
        if spec:
            input_cost = (input_tokens / 1_000_000) * spec.input_cost_per_mtok
            output_cost = (output_tokens / 1_000_000) * spec.output_cost_per_mtok
        else:
            logger.warning(f"Unknown tier '{cognitive_layer}', cost logged as 0.0")
        
        total_cost = input_cost + output_cost
        
        # Create record
        record = RequestCostRecord(
            request_id=str(uuid.uuid4()),
            user_id=user_id,
            agent_name=agent_name,
            cognitive_layer=cognitive_layer,
            model_used=model_used,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            input_cost_usd=input_cost,
            output_cost_usd=output_cost,
            total_cost_usd=total_cost,
            request_text=request_text,
            response_text=response_text,
            timestamp=datetime.utcnow(),
            duration_seconds=duration_seconds,
            cache_hit=cache_hit,
            metadata=metadata or {}
        )
        
        # Persist to database
        success = self._persist_record(record)
        
        if success:
            logger.info(
                f"Recorded request {record.request_id}: "
                f"{cognitive_layer} ({model_used}) = ${total_cost:.4f} "
                f"({input_tokens + output_tokens} tokens)"
            )
        else:
            logger.warning(f"Failed to persist request {record.request_id}")
        
        return record
    
    def _persist_record(self, record: RequestCostRecord) -> bool:
        """Persist cost record to database."""
        try:
            from sqlalchemy import text
            
            query = text("""
                INSERT INTO cost_attribution_logs (
                    request_id, user_id, agent_name, cognitive_layer,
                    model_used, provider, input_tokens, output_tokens,
                    total_tokens, input_cost_usd, output_cost_usd, total_cost_usd,
                    request_text, response_text, timestamp, duration_seconds,
                    cache_hit, metadata
                ) VALUES (
                    :request_id, :user_id, :agent_name, :cognitive_layer,
                    :model_used, :provider, :input_tokens, :output_tokens,
                    :total_tokens, :input_cost_usd, :output_cost_usd, :total_cost_usd,
                    :request_text, :response_text, :timestamp, :duration_seconds,
                    :cache_hit, :metadata
                )
            """)
            
            data = record.to_dict()
            data["metadata"] = json.dumps(data["metadata"])
            
            with self.engine.begin() as conn:
                conn.execute(query, data)
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to persist cost record: {e}", exc_info=True)
            return False
    
    def get_weekly_breakdown(self, user_id: str, days: int = 7) -> Dict:
        """
        Get weekly cost breakdown by cognitive layer.
        
        Returns:
            {
                "period_days": 7,
                "total_cost_usd": 1.23,
                "by_layer": {
                    "nano": {...},
                    "fast": {...},
                    ...
                }
            }
        """
        try:
            from sqlalchemy import text
            
            # PostgreSQL query
            query = text("""
                SELECT 
                    cognitive_layer,
                    COUNT(*) as request_count,
                    SUM(input_tokens) as total_input,
                    SUM(output_tokens) as total_output,
                    SUM(total_cost_usd) as total_cost,
                    AVG(duration_seconds) as avg_latency,
                    COUNT(*) FILTER (WHERE cache_hit = true) as cache_hits
                FROM cost_attribution_logs
                WHERE user_id = :user_id 
                  AND timestamp >= NOW() - (CAST(:days AS INTEGER) * INTERVAL '1 day')
                GROUP BY cognitive_layer
                ORDER BY total_cost DESC
            """)
            
            with self.engine.connect() as conn:
                result = conn.execute(query, {"user_id": user_id, "days": days})
                rows = result.fetchall()
            
            breakdown = {}
            total_cost = 0.0
            
            for row in rows:
                layer = row.cognitive_layer or "unknown"
                layer_cost = float(row.total_cost or 0.0)
                
                breakdown[layer] = {
                    "request_count": int(row.request_count or 0),
                    "input_tokens": int(row.total_input or 0),
                    "output_tokens": int(row.total_output or 0),
                    "total_tokens": int((row.total_input or 0) + (row.total_output or 0)),
                    "total_cost_usd": layer_cost,
                    "avg_latency_seconds": float(row.avg_latency or 0.0),
                    "cache_hits": int(row.cache_hits or 0),
                    "pct_of_total": 0.0  # Will update below
                }
                total_cost += layer_cost
            
            # Calculate percentages
            for layer, data in breakdown.items():
                if total_cost > 0:
                    data["pct_of_total"] = data["total_cost_usd"] / total_cost * 100
            
            return {
                "period_days": days,
                "total_cost_usd": total_cost,
                "by_layer": breakdown,
                "timestamp": datetime.utcnow().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Failed to generate weekly breakdown: {e}")
            return {
                "error": str(e),
                "period_days": days,
                "total_cost_usd": 0.0,
                "by_layer": {}
            }
    
    def get_optimization_recommendations(self, user_id: str) -> List[Dict]:
        """
        Analyze usage patterns and recommend optimizations.
        
        Returns:
            List of recommendation dictionaries with type, severity, message, savings
        """
        breakdown = self.get_weekly_breakdown(user_id)
        recommendations = []
        
        if "error" in breakdown:
            return []
        
        by_layer = breakdown.get("by_layer", {})
        total_cost = breakdown.get("total_cost_usd", 0.0)
        
        # Recommendation 1: Overuse of advanced tier
        advanced_data = by_layer.get("advanced", {})
        advanced_cost = advanced_data.get("total_cost_usd", 0.0)
        advanced_count = advanced_data.get("request_count", 0)
        
        if advanced_count > 0 and advanced_cost > 3.0:
            recommendations.append({
                "type": "REDUCE_ADVANCED",
                "severity": "HIGH",
                "message": (
                    f"Advanced tier used {advanced_count} times, costing ${advanced_cost:.2f}. "
                    "Consider using smart tier for 50% cost savings."
                ),
                "potential_savings": advanced_cost * 0.5
            })
        
        # Recommendation 2: Underuse of nano tier
        nano_count = by_layer.get("nano", {}).get("request_count", 0)
        fast_count = by_layer.get("fast", {}).get("request_count", 0)
        
        if fast_count > 5 and nano_count == 0:
            estimated_nano_cost = fast_count * 0.002
            recommendations.append({
                "type": "INCREASE_NANO",
                "severity": "MEDIUM",
                "message": (
                    f"No nano tier usage detected. "
                    f"{fast_count} fast-tier requests could be classification tasks. "
                    f"Estimated savings: ${estimated_nano_cost:.2f}."
                ),
                "potential_savings": estimated_nano_cost
            })
        
        # Recommendation 3: Cache effectiveness
        total_cache_hits = sum(d.get("cache_hits", 0) for d in by_layer.values())
        total_requests = sum(d.get("request_count", 0) for d in by_layer.values())
        
        if total_requests > 0:
            cache_hit_rate = (total_cache_hits / total_requests * 100)
            
            if cache_hit_rate < 10:
                potential_savings = total_cost * 0.075  # 7.5% potential
                recommendations.append({
                    "type": "IMPROVE_CACHING",
                    "severity": "MEDIUM",
                    "message": (
                        f"Cache hit rate is {cache_hit_rate:.1f}%. "
                        "Improved caching strategy could save 5-10% of costs."
                    ),
                    "potential_savings": potential_savings
                })
        
        # Recommendation 4: High-latency requests
        high_latency_threshold = 3.0  # seconds
        slow_requests = 0
        for layer_data in by_layer.values():
            if layer_data.get("avg_latency_seconds", 0) > high_latency_threshold:
                slow_requests += 1
        
        if slow_requests > 0:
            recommendations.append({
                "type": "OPTIMIZE_LATENCY",
                "severity": "LOW",
                "message": f"{slow_requests} layers have high latency. Consider request batching or pruning.",
                "potential_savings": 0.0  # Indirect savings
            })
        
        return sorted(recommendations, key=lambda x: x["potential_savings"], reverse=True)
