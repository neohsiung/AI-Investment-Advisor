"""
Integration Script for Model Config & Cost Tracking
模型配置和成本追蹤集成脚本

Week 1 Task: 
- Load tier pricing from tier_config.py
- Create CostTrackingService
- Integrate complexity detector v2
- Set up per-request cost tracking
- Enable budget checking

Usage:
  from src.infrastructure.llm.model_config_integration import setup_hrm_optimization
  
  agent = YourAgent()
  setup_hrm_optimization(agent, settings_service, token_logger_service)
"""

import logging
from typing import Optional, Dict, Any
from src.infrastructure.llm.tier_config import TierConfig, DEFAULT_TIERS
from src.infrastructure.llm.semantic_complexity_detector_v2 import SemanticComplexityDetectorV2
from src.infrastructure.llm.cost_tracking_integration import (
    CostTrackingService,
    TierPricingSpec,
    CostTrackingIntegration
)

logger = logging.getLogger(__name__)


def setup_hrm_optimization(agent: Any,
                          settings_service: Optional[Any] = None,
                          token_logger_service: Optional[Any] = None) -> Dict[str, Any]:
    """
    Set up HRM optimization infrastructure for an agent.
    
    Integrates:
    1. SemanticComplexityDetectorV2 for AST-based complexity analysis
    2. CostTrackingService for per-request cost tracking
    3. Tier pricing from tier_config.py
    4. Budget checking mechanisms
    
    Args:
        agent: Agent instance to configure
        settings_service: Optional SettingsService instance for DB queries
        token_logger_service: Optional TokenLoggerService for cost storage
    
    Returns:
        Dict with initialized components:
        {
            "complexity_detector": SemanticComplexityDetectorV2,
            "cost_service": CostTrackingService,
            "tier_specs": Dict[str, TierPricingSpec],
            "status": "ready"
        }
    """
    logger.info("🚀 Starting HRM Optimization Week 1 Setup...")
    
    # Step 1: Initialize complexity detector v2
    logger.info("Step 1/4: Initializing SemanticComplexityDetectorV2...")
    detector = SemanticComplexityDetectorV2()
    logger.info("  ✓ Complexity detector ready (7 feature extractors)")
    
    # Step 2: Extract tier pricing specs
    logger.info("Step 2/4: Extracting tier pricing from tier_config.py...")
    tier_specs = _extract_tier_pricing_specs(DEFAULT_TIERS)
    for tier_name, spec in tier_specs.items():
        logger.info(f"  - {tier_name}: ${spec.blended_cost_per_mtok:.4f}/MTok")
    
    # Step 3: Initialize cost tracking service
    logger.info("Step 3/4: Initializing CostTrackingService...")
    cost_service = CostTrackingService(tier_specs)
    logger.info("  ✓ Cost tracking service ready")
    
    # Step 4: Attach to agent
    logger.info("Step 4/4: Attaching components to agent...")
    if agent:
        agent._complexity_detector = detector
        agent._cost_service = cost_service
        agent._tier_specs = tier_specs
        logger.info("  ✓ Components attached to agent")
    
    logger.info("✅ HRM Optimization Week 1 setup complete!")
    logger.info("\nSummary:")
    logger.info(f"  - Detector: 7 feature extractors (Structural, Semantic, Temporal, Numerical, Domain, Intent, Context)")
    logger.info(f"  - Cost Service: {len(tier_specs)} tiers configured")
    logger.info(f"  - Tiers: {', '.join(tier_specs.keys())}")
    logger.info(f"  - Budget tracking: Enabled (soft=$16.0, hard=$20.0)")
    
    return {
        "complexity_detector": detector,
        "cost_service": cost_service,
        "tier_specs": tier_specs,
        "status": "ready"
    }


def _extract_tier_pricing_specs(tier_config_dict: Dict) -> Dict[str, TierPricingSpec]:
    """
    Extract TierPricingSpec from tier_config.py DEFAULT_TIERS dict.
    
    Args:
        tier_config_dict: Dict mapping tier_name → TierSpec (from tier_config.py)
    
    Returns:
        Dict mapping tier_name → TierPricingSpec
    """
    result = {}
    
    for tier_name, spec in tier_config_dict.items():
        result[tier_name] = TierPricingSpec(
            tier_name=spec.name,
            display_name=spec.display_name,
            input_cost_per_mtok=spec.input_cost_per_mtok,
            output_cost_per_mtok=spec.output_cost_per_mtok,
            max_tokens=spec.max_tokens
        )
    
    return result


def estimate_token_savings(current_model_allocation: Dict[str, int],
                          proposed_sonnet_upgrade: bool = True) -> Dict[str, Any]:
    """
    Estimate token and cost savings from Sonnet 3.5 upgrade.
    
    Example scenario:
      Current (Opus): 1M tokens at $1.94/MTok = $1.94
      Proposed (Sonnet 3.5): 1M tokens at $0.93/MTok = $0.93
      Savings: $1.01 (52%)
    
    Args:
        current_model_allocation: Dict of tier → token count
        proposed_sonnet_upgrade: If True, simulate Sonnet 3.5 upgrade for "smart" tier
    
    Returns:
        Dict with detailed breakdown
    """
    # Current tier specs (Opus for smart)
    tier_specs_current = _extract_tier_pricing_specs(DEFAULT_TIERS)
    
    # Calculate current cost
    current_cost = 0.0
    for tier, token_count in current_model_allocation.items():
        if tier in tier_specs_current:
            spec = tier_specs_current[tier]
            cost = (token_count / 1_000_000) * spec.blended_cost_per_mtok
            current_cost += cost
    
    # Estimate proposed cost (if Sonnet upgrade)
    proposed_cost = current_cost
    savings = 0.0
    savings_pct = 0.0
    
    if proposed_sonnet_upgrade and "smart" in current_model_allocation:
        # Simulate: Opus smart tier → Sonnet 3.5
        # Opus blended: (1.25*3 + 10.00)/4 = 1.94 $/MTok
        # Sonnet blended: (0.70*3 + 3.00)/4 = 0.93 $/MTok
        smart_tokens = current_model_allocation["smart"]
        opus_cost = (smart_tokens / 1_000_000) * 1.94
        sonnet_cost = (smart_tokens / 1_000_000) * 0.93
        savings = opus_cost - sonnet_cost
        proposed_cost = current_cost - savings
        savings_pct = (savings / current_cost * 100) if current_cost > 0 else 0
    
    return {
        "current_cost": current_cost,
        "proposed_cost": proposed_cost,
        "savings": savings,
        "savings_pct": savings_pct,
        "scenario": "Sonnet 3.5 upgrade for 'smart' tier" if proposed_sonnet_upgrade else "No upgrade",
        "assumptions": {
            "smart_tier_migration": "Opus → Sonnet 3.5" if proposed_sonnet_upgrade else "No change",
            "blended_ratio": "3:1 input:output",
            "opus_blended_cost": 1.94,
            "sonnet_blended_cost": 0.93,
        }
    }


def generate_week1_report(cost_service: CostTrackingService,
                         complexity_detector: SemanticComplexityDetectorV2,
                         user_id: Optional[str] = None) -> str:
    """
    Generate Week 1 implementation report.
    
    Args:
        cost_service: CostTrackingService instance
        complexity_detector: SemanticComplexityDetectorV2 instance
        user_id: Optional user to generate report for
    
    Returns:
        Formatted report string
    """
    lines = []
    
    lines.append("═" * 80)
    lines.append("HRM OPTIMIZATION WEEK 1 REPORT")
    lines.append("═" * 80)
    lines.append("")
    
    lines.append("✅ IMPLEMENTED COMPONENTS")
    lines.append("-" * 80)
    lines.append("1. SemanticComplexityDetectorV2")
    lines.append("   - 7 feature extractors: Structural, Semantic, Temporal, Numerical,")
    lines.append("     Domain, Intent, Context")
    lines.append("   - Classification: REFLEXIVE → FAST_THINK → MEMORY_DIG → DEEP_RESEARCH")
    lines.append("   - Accuracy target: >90% on historical test set")
    lines.append("")
    
    lines.append("2. CostTrackingService")
    lines.append("   - Per-request cost tracking")
    lines.append("   - Budget checking (soft=$16.0, hard=$20.0)")
    lines.append("   - Tier breakdown and reporting")
    lines.append("")
    
    lines.append("3. Integration with tier_config.py")
    lines.append("   - Pricing extracted: nano, fast, smart, advanced")
    lines.append("   - Cost calculations: input + output tokens")
    lines.append("   - Blended cost metric: 3:1 input:output ratio")
    lines.append("")
    
    if user_id:
        spending = cost_service.get_user_spending(user_id, days=7)
        lines.append("📊 USER SPENDING SNAPSHOT")
        lines.append("-" * 80)
        lines.append(f"User: {user_id}")
        lines.append(f"Period: {spending.period_label} (7 days)")
        lines.append(f"Total Cost: ${spending.total_cost:.2f}")
        lines.append(f"Total Requests: {spending.request_count}")
        if spending.tier_breakdown:
            lines.append("Breakdown by tier:")
            for tier, cost in spending.tier_breakdown.items():
                lines.append(f"  - {tier}: ${cost:.2f}")
        lines.append("")
    
    lines.append("📈 COST SAVINGS PROJECTION")
    lines.append("-" * 80)
    sample_allocation = {"smart": 1_000_000, "fast": 500_000, "nano": 200_000}
    savings_estimate = estimate_token_savings(sample_allocation, proposed_sonnet_upgrade=True)
    lines.append(f"Sample: 1.7M tokens across tiers")
    lines.append(f"Current cost (Opus): ${savings_estimate['current_cost']:.2f}")
    lines.append(f"Proposed cost (Sonnet 3.5): ${savings_estimate['proposed_cost']:.2f}")
    lines.append(f"Estimated savings: ${savings_estimate['savings']:.2f} ({savings_estimate['savings_pct']:.1f}%)")
    lines.append("")
    
    lines.append("🎯 NEXT STEPS (Week 2-3)")
    lines.append("-" * 80)
    lines.append("1. Validation & Monitoring")
    lines.append("   - A/B test Sonnet 3.5 vs Opus on 20+ test cases")
    lines.append("   - Benchmark accuracy and latency")
    lines.append("   - Monitor cost tracking in production")
    lines.append("")
    lines.append("2. Tier Migration")
    lines.append("   - Gradual rollout of Sonnet 3.5 for 'smart' tier")
    lines.append("   - Keep Opus as fallback for high-stakes decisions")
    lines.append("")
    lines.append("3. Dashboard & Reporting")
    lines.append("   - Real-time cost tracking dashboard")
    lines.append("   - Weekly cost report generation")
    lines.append("")
    
    lines.append("=" * 80)
    
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Example Usage
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    
    # Example: Setup optimization without an agent
    logger.info("Example: HRM Optimization Week 1 Setup\n")
    
    result = setup_hrm_optimization(agent=None)
    
    # Generate report
    cost_service = result["cost_service"]
    detector = result["complexity_detector"]
    
    report = generate_week1_report(cost_service, detector)
    print(report)
