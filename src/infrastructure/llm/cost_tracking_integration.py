"""
Cost Tracking & Budget Management Integration — Week 1
成本追蹤與預算管理集成 — Week 1

Per-request cost tracking with tier-based pricing from model_config.yaml (or tier_config.py).
Integrates with SettingsAwareModelRouter and BudgetAwareModelRouter.

Features:
- Extract pricing from tier specifications
- Calculate per-request cost based on tokens and tier
- Track cumulative costs per user (weekly/monthly)
- Budget check before request execution
- Cost attribution and logging
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Optional, Any, List
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class CostTrackingMode(Enum):
    """Mode for cost tracking."""
    ESTIMATED = "estimated"    # Pre-request estimate
    ACTUAL = "actual"          # Post-request actual
    PROJECTED = "projected"    # Based on partial data


@dataclass
class TierPricingSpec:
    """Pricing specification for a single tier."""
    tier_name: str
    display_name: str
    input_cost_per_mtok: float      # $/million input tokens
    output_cost_per_mtok: float     # $/million output tokens
    max_tokens: int
    
    @property
    def blended_cost_per_mtok(self) -> float:
        """Blended cost assuming 3:1 input:output ratio."""
        return (self.input_cost_per_mtok * 3 + self.output_cost_per_mtok) / 4
    
    def estimate_request_cost(self, input_tokens: int, output_tokens: int = 0) -> float:
        """
        Estimate cost for a single request.
        
        Args:
            input_tokens: Number of input tokens
            output_tokens: Estimated output tokens (default: 0 for pre-request estimate)
        
        Returns:
            Estimated cost in USD
        """
        input_cost = (input_tokens / 1_000_000) * self.input_cost_per_mtok
        output_cost = (output_tokens / 1_000_000) * self.output_cost_per_mtok
        return input_cost + output_cost


@dataclass
class RequestCostRecord:
    """Record of a single request's cost."""
    user_id: str
    tier: str
    timestamp: datetime
    request_id: str
    
    # Tokens
    input_tokens: int
    output_tokens: int
    
    # Cost
    estimated_cost: float = 0.0
    actual_cost: float = 0.0
    mode: CostTrackingMode = CostTrackingMode.ESTIMATED
    
    # Metadata
    agent_name: Optional[str] = None
    cognitive_layer: Optional[str] = None
    model_used: Optional[str] = None
    tags: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def total_cost(self) -> float:
        """Return actual cost if available, else estimated."""
        return self.actual_cost if self.actual_cost > 0 else self.estimated_cost


@dataclass
class UserSpendingSnapshot:
    """Snapshot of user spending in a time window."""
    user_id: str
    period_start: datetime
    period_end: datetime
    period_label: str              # "weekly", "monthly", "daily"
    
    total_cost: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    request_count: int = 0
    
    tier_breakdown: Dict[str, float] = field(default_factory=dict)
    layer_breakdown: Dict[str, float] = field(default_factory=dict)
    
    budget_limit: Optional[float] = None
    budget_remaining: Optional[float] = None
    budget_utilization_pct: float = 0.0


@dataclass
class CostEstimate:
    """Pre-request cost estimate."""
    tier: str
    estimated_input_tokens: int
    estimated_output_tokens: int = 2048  # Default estimate
    
    estimated_cost: float = 0.0
    confidence: float = 0.7              # 0.0-1.0
    
    # Budget check
    would_exceed_soft_limit: bool = False
    would_exceed_hard_limit: bool = False
    warning_message: Optional[str] = None


class CostTrackingService:
    """
    Service for tracking request costs and checking budgets.
    
    Integrates with:
    - TierPricingSpec (from tier_config.py)
    - BudgetAwareModelRouter (budget checking)
    - TokenLoggerService (cost storage)
    """
    
    def __init__(self, tier_pricing_specs: Dict[str, TierPricingSpec]):
        """
        Initialize with tier pricing specifications.
        
        Args:
            tier_pricing_specs: Dict mapping tier names to TierPricingSpec
        """
        self.tier_specs = tier_pricing_specs
        self.cost_records: List[RequestCostRecord] = []
    
    def estimate_request_cost(self,
                             tier: str,
                             input_tokens: int,
                             output_tokens: int = 2048) -> CostEstimate:
        """
        Estimate cost for a request.
        
        Args:
            tier: Tier name ("nano", "fast", "smart", "advanced")
            input_tokens: Input token count
            output_tokens: Estimated output tokens
        
        Returns:
            CostEstimate object
        """
        if tier not in self.tier_specs:
            logger.warning(f"Tier {tier} not found in pricing specs")
            return CostEstimate(
                tier=tier,
                estimated_input_tokens=input_tokens,
                estimated_output_tokens=output_tokens,
                estimated_cost=0.0,
                warning_message=f"Unknown tier: {tier}"
            )
        
        spec = self.tier_specs[tier]
        estimated_cost = spec.estimate_request_cost(input_tokens, output_tokens)
        
        return CostEstimate(
            tier=tier,
            estimated_input_tokens=input_tokens,
            estimated_output_tokens=output_tokens,
            estimated_cost=estimated_cost,
            confidence=0.8
        )
    
    def record_request(self,
                      user_id: str,
                      tier: str,
                      request_id: str,
                      input_tokens: int,
                      output_tokens: int,
                      actual_cost: Optional[float] = None,
                      agent_name: Optional[str] = None,
                      cognitive_layer: Optional[str] = None,
                      model_used: Optional[str] = None,
                      tags: Optional[Dict] = None) -> RequestCostRecord:
        """
        Record a request's cost.
        
        Args:
            user_id: User ID
            tier: Tier used
            request_id: Unique request ID
            input_tokens: Actual input tokens
            output_tokens: Actual output tokens
            actual_cost: Actual cost (from API response). If None, estimate.
            agent_name: Name of agent that made request
            cognitive_layer: Cognitive layer (REFLEXIVE, FAST_THINK, MEMORY_DIG, DEEP_RESEARCH)
            model_used: Model ID that was used
            tags: Additional metadata tags
        
        Returns:
            RequestCostRecord
        """
        spec = self.tier_specs.get(tier)
        if not spec:
            logger.error(f"Tier {tier} not in specs")
            return None
        
        estimated_cost = spec.estimate_request_cost(input_tokens, output_tokens)
        
        record = RequestCostRecord(
            user_id=user_id,
            tier=tier,
            timestamp=datetime.utcnow(),
            request_id=request_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost=estimated_cost,
            actual_cost=actual_cost or estimated_cost,
            mode=CostTrackingMode.ACTUAL if actual_cost else CostTrackingMode.ESTIMATED,
            agent_name=agent_name,
            cognitive_layer=cognitive_layer,
            model_used=model_used,
            tags=tags or {}
        )
        
        self.cost_records.append(record)
        logger.info(f"Cost recorded: user={user_id} tier={tier} cost=${record.total_cost:.4f}")
        
        return record
    
    def get_user_spending(self,
                         user_id: str,
                         days: int = 7,
                         period_label: str = "weekly") -> UserSpendingSnapshot:
        """
        Get user spending summary for a time window.
        
        Args:
            user_id: User ID
            days: Number of days to look back
            period_label: Label for the period ("weekly", "monthly", "daily")
        
        Returns:
            UserSpendingSnapshot
        """
        now = datetime.utcnow()
        period_start = now - timedelta(days=days)
        
        # Filter records for this user and period
        relevant_records = [
            r for r in self.cost_records
            if r.user_id == user_id and period_start <= r.timestamp <= now
        ]
        
        # Aggregate
        total_cost = sum(r.total_cost for r in relevant_records)
        total_input = sum(r.input_tokens for r in relevant_records)
        total_output = sum(r.output_tokens for r in relevant_records)
        
        # Breakdown by tier
        tier_breakdown = {}
        for r in relevant_records:
            tier_breakdown[r.tier] = tier_breakdown.get(r.tier, 0.0) + r.total_cost
        
        # Breakdown by layer
        layer_breakdown = {}
        for r in relevant_records:
            if r.cognitive_layer:
                layer_breakdown[r.cognitive_layer] = layer_breakdown.get(r.cognitive_layer, 0.0) + r.total_cost
        
        return UserSpendingSnapshot(
            user_id=user_id,
            period_start=period_start,
            period_end=now,
            period_label=period_label,
            total_cost=total_cost,
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            request_count=len(relevant_records),
            tier_breakdown=tier_breakdown,
            layer_breakdown=layer_breakdown
        )
    
    def check_budget(self,
                    user_id: str,
                    requested_tier: str,
                    estimated_cost: float,
                    soft_limit: float = 16.0,
                    hard_limit: float = 20.0,
                    days: int = 7) -> Dict[str, Any]:
        """
        Check if request fits within budget.
        
        Args:
            user_id: User ID
            requested_tier: Requested tier
            estimated_cost: Estimated cost of request
            soft_limit: Soft limit (80% of budget) in USD
            hard_limit: Hard limit (100% of budget) in USD
            days: Days to look back for spending
        
        Returns:
            Dict with:
            - "ok": bool — request is OK to proceed
            - "current_spend": float
            - "projected_spend": float
            - "soft_limit_exceeded": bool
            - "hard_limit_exceeded": bool
            - "recommendation": str
        """
        spending = self.get_user_spending(user_id, days=days)
        current_spend = spending.total_cost
        projected_spend = current_spend + estimated_cost
        
        soft_exceeded = projected_spend > soft_limit
        hard_exceeded = projected_spend > hard_limit
        
        ok = not hard_exceeded
        
        recommendation = "proceed"
        if hard_exceeded:
            recommendation = "reject"
        elif soft_exceeded:
            recommendation = "downgrade_tier"
        
        return {
            "ok": ok,
            "current_spend": current_spend,
            "projected_spend": projected_spend,
            "soft_limit": soft_limit,
            "hard_limit": hard_limit,
            "soft_limit_exceeded": soft_exceeded,
            "hard_limit_exceeded": hard_exceeded,
            "recommendation": recommendation,
            "message": f"Current: ${current_spend:.2f}, Projected: ${projected_spend:.2f} (limit: ${hard_limit:.2f})"
        }
    
    def estimate_token_savings(self,
                              current_tier_usage: Dict[str, int],
                              proposed_tier_migration: Dict[str, str]) -> Dict[str, Any]:
        """
        Estimate token and cost savings from tier migration.
        
        Example:
            current_tier_usage = {
                "smart": 1000000,   # 1M tokens on Opus
                "fast": 500000,     # 500K tokens on Sonnet
                "nano": 200000      # 200K tokens on Haiku
            }
            proposed_tier_migration = {
                "smart": "sonnet-3.5"  # Migrate smart from Opus to Sonnet 3.5
            }
        
        Args:
            current_tier_usage: Dict of tier → token count
            proposed_tier_migration: Dict of tier → proposed model
        
        Returns:
            Dict with current/proposed costs and savings
        """
        current_cost = 0.0
        proposed_cost = 0.0
        
        for tier, token_count in current_tier_usage.items():
            if tier not in self.tier_specs:
                continue
            
            spec = self.tier_specs[tier]
            tier_cost = (token_count / 1_000_000) * spec.blended_cost_per_mtok
            current_cost += tier_cost
        
        # For proposed, we'd need to update tier_specs temporarily
        # For now, just log the analysis
        
        return {
            "current_cost": current_cost,
            "proposed_cost": proposed_cost,
            "savings": current_cost - proposed_cost,
            "savings_pct": (current_cost - proposed_cost) / current_cost * 100 if current_cost > 0 else 0,
        }


class CostTrackingIntegration:
    """
    Integration layer between CostTrackingService and existing routers.
    
    Provides methods to integrate cost tracking into:
    - SettingsAwareModelRouter
    - BudgetAwareModelRouter
    - ResilientLLMPipeline
    """
    
    @staticmethod
    def initialize_from_tier_config(tier_config) -> Dict[str, TierPricingSpec]:
        """
        Initialize TierPricingSpec dict from tier_config.py TierSpec objects.
        
        Args:
            tier_config: TierConfig or dict of tier_name → TierSpec
        
        Returns:
            Dict of tier_name → TierPricingSpec
        """
        result = {}
        
        # Handle TierConfig object
        if hasattr(tier_config, 'TIERS'):
            for tier_name, spec in tier_config.TIERS.items():
                result[tier_name] = TierPricingSpec(
                    tier_name=spec.name,
                    display_name=spec.display_name,
                    input_cost_per_mtok=spec.input_cost_per_mtok,
                    output_cost_per_mtok=spec.output_cost_per_mtok,
                    max_tokens=spec.max_tokens
                )
        
        # Handle dict
        elif isinstance(tier_config, dict):
            for tier_name, spec in tier_config.items():
                result[tier_name] = TierPricingSpec(
                    tier_name=tier_name,
                    display_name=getattr(spec, 'display_name', tier_name),
                    input_cost_per_mtok=spec.input_cost_per_mtok,
                    output_cost_per_mtok=spec.output_cost_per_mtok,
                    max_tokens=spec.max_tokens
                )
        
        return result
    
    @staticmethod
    def inject_cost_tracking(router, cost_service: CostTrackingService):
        """
        Inject cost tracking into a router or gateway.
        
        Args:
            router: Router object (SettingsAwareModelRouter, BudgetAwareModelRouter, etc.)
            cost_service: CostTrackingService instance
        """
        router._cost_service = cost_service
        
        # Monkey-patch cost recording into get_config if it exists
        if hasattr(router, 'get_config'):
            original_get_config = router.get_config
            
            def wrapped_get_config(*args, **kwargs):
                config = original_get_config(*args, **kwargs)
                # Attach cost service to config
                if config:
                    config._cost_service = cost_service
                return config
            
            router.get_config = wrapped_get_config
        
        logger.info("Cost tracking injected into router")
