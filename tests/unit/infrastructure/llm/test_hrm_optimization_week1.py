"""
Unit Tests for HRM Optimization Week 1
Week 1 實現的單元測試

Tests:
1. SemanticComplexityDetectorV2 — 7 feature extractors + classification
2. CostTrackingService — cost estimation, tracking, budget checking
3. Integration — detector + cost service + tier routing
"""

import pytest
import logging
from datetime import datetime, timedelta
from src.infrastructure.llm.semantic_complexity_detector_v2 import (
    SemanticComplexityDetectorV2,
    CognitiveLayer,
    StructuralFeatures,
    SemanticFeatures,
    TemporalFeatures,
    NumericalFeatures,
    DomainFeatures,
    IntentFeatures,
    ContextFeatures
)
from src.infrastructure.llm.cost_tracking_integration import (
    CostTrackingService,
    TierPricingSpec,
    RequestCostRecord,
    CostTrackingMode
)
from src.infrastructure.llm.model_config_integration import (
    setup_hrm_optimization,
    estimate_token_savings,
    generate_week1_report
)
from src.infrastructure.llm.tier_config import DEFAULT_TIERS

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Test: SemanticComplexityDetectorV2
# ═══════════════════════════════════════════════════════════════════════════════

class TestSemanticComplexityDetectorV2:
    """Test suite for SemanticComplexityDetectorV2."""
    
    @pytest.fixture
    def detector(self):
        """Create detector instance."""
        return SemanticComplexityDetectorV2()
    
    def test_initialization(self, detector):
        """Test detector initialization."""
        assert detector is not None
        assert hasattr(detector, 'FINANCIAL_KEYWORDS')
        assert 'stock' in detector.FINANCIAL_KEYWORDS
        logger.info("✓ Detector initialized")
    
    def test_simple_reflexive_query(self, detector):
        """Test simple query → REFLEXIVE layer."""
        result = detector.analyze("What is the current price of AAPL?")
        
        assert result.layer == CognitiveLayer.REFLEXIVE
        assert result.confidence > 0.5
        assert 'features' in result.__dict__
        assert result.complexity_score < 0.2
        logger.info(f"✓ Simple query → {result.layer.value} (confidence={result.confidence:.2f})")
    
    def test_moderate_fast_think_query(self, detector):
        """Test moderate query → FAST_THINK layer."""
        result = detector.analyze(
            "Summarize the price performance of AAPL, MSFT, and GOOG over the last 3 months. "
            "Include analysis of volatility and correlation with SP500 index."
        )
        
        # Should be at least FAST_THINK
        assert result.layer in [CognitiveLayer.FAST_THINK, CognitiveLayer.MEMORY_DIG]
        assert result.complexity_score > 0.15
        logger.info(f"✓ Moderate query → {result.layer.value} (score={result.complexity_score:.2f})")
    
    def test_complex_memory_dig_query(self, detector):
        """Test complex query → MEMORY_DIG layer."""
        result = detector.analyze(
            "Analyze the correlation between VIX volatility and SP500 performance over the past year. "
            "Consider market conditions during each quarter and the impact of Fed policy changes. "
            "Then recommend portfolio rebalancing strategy considering risk factors."
        )
        
        # Should be MEMORY_DIG or higher
        assert result.layer in [CognitiveLayer.MEMORY_DIG, CognitiveLayer.DEEP_RESEARCH]
        assert result.complexity_score > 0.45
        logger.info(f"✓ Complex query → {result.layer.value} (score={result.complexity_score:.2f})")
    
    def test_trade_execution_deep_research(self, detector):
        """Test trade execution → DEEP_RESEARCH layer."""
        result = detector.analyze(
            "Execute a $5 million portfolio rebalancing: Short 500 AAPL calls with strike 150, "
            "buy 200 SPY shares, hedge with VIX options. Risk assessment: tail risk from Fed policy. "
            "Must comply with SEC requirements and manage margin requirements."
        )
        
        # Trade execution with high portfolio size and derivatives
        assert result.layer in [CognitiveLayer.MEMORY_DIG, CognitiveLayer.DEEP_RESEARCH]
        assert result.features['intent']['is_trade_execution'] == True
        assert result.features['intent']['portfolio_size'] >= 1_000_000
        assert result.features['domain']['derivative_types'] > 0
        logger.info(f"✓ Trade execution → {result.layer.value}")
        logger.info(f"  - Portfolio size: ${result.features['intent']['portfolio_size']:,.0f}")
        logger.info(f"  - Derivatives: {result.features['domain']['derivative_types']}")
    
    def test_structural_features_extraction(self, detector):
        """Test structural feature extraction."""
        features = detector._extract_structural_features(
            "if (price > 100 && volume > 1M) { execute_trade() } else { wait_signal() }"
        )
        
        assert features.clause_depth > 0
        assert features.condition_count > 0
        assert features.complexity_score() > 0.0
        logger.info(f"✓ Structural features: depth={features.clause_depth}, conditions={features.condition_count}")
    
    def test_semantic_features_extraction(self, detector):
        """Test semantic feature extraction."""
        features = detector._extract_semantic_features(
            "The strategy may involve complex risk hedging because market conditions are uncertain. "
            "Multiple steps are required: first analyze, then decide, finally execute."
        )
        
        assert features.concept_count >= 0
        assert features.uncertainty_markers > 0
        assert features.causal_chains > 0
        logger.info(f"✓ Semantic features: concepts={features.concept_count}, causal={features.causal_chains}")
    
    def test_domain_features_extraction(self, detector):
        """Test domain-specific feature extraction."""
        features = detector._extract_domain_features(
            "Analyze correlation between AAPL, MSFT, and GOOG. Consider SP500 index and SPY ETF, VIX volatility. "
            "Use options strategies (straddle, spread). SEC compliance needed."
        )
        
        assert features.ticker_count > 0
        assert features.market_indices > 0  # SP500, VIX
        assert features.derivative_types > 0  # straddle, spread
        assert features.regulatory_refs > 0  # SEC
        logger.info(
            f"✓ Domain features: tickers={features.ticker_count}, derivatives={features.derivative_types}, "
            f"indices={features.market_indices}, regulatory={features.regulatory_refs}"
        )
    
    def test_intent_features_extraction(self, detector):
        """Test intent feature extraction."""
        features = detector._extract_intent_features(
            "Buy 500 shares of AAPL and short 100 SPY shares. Portfolio size: $5 million. "
            "Hedge downside risk using put options.",
            {}
        )
        
        assert features.is_trade_execution == True
        assert features.is_risk_assessment == True
        assert features.portfolio_size >= 1_000_000
        logger.info(
            f"✓ Intent features: trade_exec={features.is_trade_execution}, "
            f"risk_assess={features.is_risk_assessment}, portfolio=${features.portfolio_size:,.0f}"
        )
    
    def test_recommend_tier(self, detector):
        """Test tier recommendation."""
        simple_result = detector.analyze("What is AAPL?")
        complex_result = detector.analyze(
            "Execute $10 million portfolio rebalancing with options hedging, "
            "derivative strategies, and SEC compliance requirements."
        )
        
        simple_tier = detector.recommend_tier(simple_result)
        complex_tier = detector.recommend_tier(complex_result)
        
        # Simple should be nano or fast
        assert simple_tier in ["nano", "fast"]
        # Complex should be at least fast, likely smart or advanced
        assert complex_tier in ["fast", "smart", "advanced"]
        logger.info(f"✓ Tier recommendations: simple={simple_tier}, complex={complex_tier}")


# ═══════════════════════════════════════════════════════════════════════════════
# Test: CostTrackingService
# ═══════════════════════════════════════════════════════════════════════════════

class TestCostTrackingService:
    """Test suite for CostTrackingService."""
    
    @pytest.fixture
    def tier_specs(self):
        """Create tier pricing specs."""
        from src.infrastructure.llm.model_config_integration import _extract_tier_pricing_specs
        return _extract_tier_pricing_specs(DEFAULT_TIERS)
    
    @pytest.fixture
    def cost_service(self, tier_specs):
        """Create cost tracking service."""
        return CostTrackingService(tier_specs)
    
    def test_initialization(self, cost_service, tier_specs):
        """Test cost service initialization."""
        assert cost_service is not None
        assert len(cost_service.tier_specs) == len(tier_specs)
        logger.info(f"✓ Cost service initialized with {len(tier_specs)} tiers")
    
    def test_tier_pricing_spec(self):
        """Test TierPricingSpec."""
        spec = TierPricingSpec(
            tier_name="test",
            display_name="Test Tier",
            input_cost_per_mtok=1.0,
            output_cost_per_mtok=2.0,
            max_tokens=4096
        )
        
        assert spec.blended_cost_per_mtok == (1.0*3 + 2.0) / 4  # 1.25
        logger.info(f"✓ Blended cost calculation: {spec.blended_cost_per_mtok:.2f}")
    
    def test_estimate_request_cost(self, cost_service):
        """Test cost estimation."""
        estimate = cost_service.estimate_request_cost(
            tier="nano",
            input_tokens=100_000,
            output_tokens=50_000
        )
        
        assert estimate.estimated_cost > 0
        assert estimate.estimated_input_tokens == 100_000
        assert estimate.estimated_output_tokens == 50_000
        logger.info(f"✓ Cost estimate: tier=nano, cost=${estimate.estimated_cost:.4f}")
    
    def test_record_request(self, cost_service):
        """Test request cost recording."""
        record = cost_service.record_request(
            user_id="user_123",
            tier="fast",
            request_id="req_456",
            input_tokens=50_000,
            output_tokens=10_000,
            agent_name="test_agent",
            cognitive_layer="FAST_THINK",
            tags={"test": True}
        )
        
        assert record is not None
        assert record.user_id == "user_123"
        assert record.tier == "fast"
        assert record.total_cost > 0
        logger.info(f"✓ Request recorded: cost=${record.total_cost:.4f}")
    
    def test_user_spending_snapshot(self, cost_service):
        """Test user spending aggregation."""
        # Record multiple requests
        for i in range(3):
            cost_service.record_request(
                user_id="user_123",
                tier="fast" if i % 2 == 0 else "smart",
                request_id=f"req_{i}",
                input_tokens=50_000 * (i + 1),
                output_tokens=10_000 * (i + 1)
            )
        
        spending = cost_service.get_user_spending("user_123", days=7)
        
        assert spending.total_cost > 0
        assert spending.request_count == 3
        assert spending.total_input_tokens > 0
        assert len(spending.tier_breakdown) > 0
        logger.info(
            f"✓ Spending snapshot: total=${spending.total_cost:.2f}, "
            f"requests={spending.request_count}, tiers={list(spending.tier_breakdown.keys())}"
        )
    
    def test_budget_check_ok(self, cost_service):
        """Test budget check — within limits."""
        # Record $5 cost
        cost_service.record_request(
            user_id="user_budget",
            tier="nano",
            request_id="req_1",
            input_tokens=10_000,
            output_tokens=5_000
        )
        
        # Check budget for new $2 request
        check = cost_service.check_budget(
            user_id="user_budget",
            requested_tier="nano",
            estimated_cost=2.0,
            soft_limit=16.0,
            hard_limit=20.0
        )
        
        assert check["ok"] == True
        assert check["recommendation"] == "proceed"
        logger.info(f"✓ Budget check OK: {check['message']}")
    
    def test_budget_check_soft_limit(self, cost_service):
        """Test budget check — soft limit exceeded."""
        # Record high cost that triggers soft limit
        cost_service.record_request(
            user_id="user_soft",
            tier="advanced",
            request_id="req_1",
            input_tokens=5_000_000,
            output_tokens=2_000_000
        )
        
        # Check budget for another $5 request → should exceed soft limit
        check = cost_service.check_budget(
            user_id="user_soft",
            requested_tier="smart",
            estimated_cost=2.0,
            soft_limit=16.0,
            hard_limit=20.0
        )
        
        assert check["soft_limit_exceeded"] == True
        assert check["recommendation"] == "downgrade_tier"
        logger.info(f"✓ Soft limit detection: {check['recommendation']}")
    
    def test_budget_check_hard_limit(self, cost_service):
        """Test budget check — hard limit exceeded."""
        # Record very high cost approaching hard limit
        cost_service.record_request(
            user_id="user_hard",
            tier="advanced",
            request_id="req_1",
            input_tokens=8_000_000,
            output_tokens=3_000_000
        )
        
        # Check budget for $3 request → should exceed hard limit
        check = cost_service.check_budget(
            user_id="user_hard",
            requested_tier="smart",
            estimated_cost=3.0,
            soft_limit=16.0,
            hard_limit=20.0
        )
        
        assert check["hard_limit_exceeded"] == True
        assert check["recommendation"] == "reject"
        assert check["ok"] == False
        logger.info(f"✓ Hard limit detection: {check['recommendation']}")


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Integration
# ═══════════════════════════════════════════════════════════════════════════════

class TestIntegration:
    """Test suite for Week 1 integration."""
    
    def test_setup_hrm_optimization(self):
        """Test setup_hrm_optimization function."""
        result = setup_hrm_optimization(agent=None)
        
        assert "complexity_detector" in result
        assert "cost_service" in result
        assert "tier_specs" in result
        assert result["status"] == "ready"
        
        detector = result["complexity_detector"]
        assert isinstance(detector, SemanticComplexityDetectorV2)
        
        cost_service = result["cost_service"]
        assert isinstance(cost_service, CostTrackingService)
        
        logger.info("✓ HRM optimization setup complete")
    
    def test_estimate_token_savings(self):
        """Test token savings estimation."""
        allocation = {
            "smart": 1_000_000,
            "fast": 500_000,
            "nano": 200_000
        }
        
        savings = estimate_token_savings(allocation, proposed_sonnet_upgrade=True)
        
        assert savings["current_cost"] > 0
        assert savings["proposed_cost"] > 0
        assert savings["savings"] > 0
        assert savings["savings_pct"] > 0
        
        logger.info(
            f"✓ Savings estimate: Current=${savings['current_cost']:.2f}, "
            f"Proposed=${savings['proposed_cost']:.2f}, "
            f"Savings=${savings['savings']:.2f} ({savings['savings_pct']:.1f}%)"
        )
    
    def test_generate_week1_report(self):
        """Test report generation."""
        result = setup_hrm_optimization(agent=None)
        
        report = generate_week1_report(
            result["cost_service"],
            result["complexity_detector"],
            user_id="test_user"
        )
        
        assert "HRM OPTIMIZATION WEEK 1 REPORT" in report
        assert "IMPLEMENTED COMPONENTS" in report
        assert "SemanticComplexityDetectorV2" in report
        assert "CostTrackingService" in report
        
        logger.info("✓ Week 1 report generated successfully")
    
    def test_end_to_end_workflow(self):
        """Test complete end-to-end workflow."""
        logger.info("\n" + "="*80)
        logger.info("END-TO-END WORKFLOW TEST")
        logger.info("="*80)
        
        # Setup
        result = setup_hrm_optimization(agent=None)
        detector = result["complexity_detector"]
        cost_service = result["cost_service"]
        
        # Scenario: Process a request
        test_prompts = [
            ("What is the price of AAPL?", "REFLEXIVE", "nano"),
            ("Summarize tech stocks this quarter", "FAST_THINK", "fast"),
            ("Analyze portfolio allocation for market downturn", "MEMORY_DIG", "smart"),
            ("Execute $10M portfolio rebalancing with options hedging", "DEEP_RESEARCH", "advanced"),
        ]
        
        for prompt, expected_layer, expected_tier in test_prompts:
            # 1. Analyze complexity
            result_analysis = detector.analyze(prompt)
            tier = detector.recommend_tier(result_analysis)
            
            logger.info(f"\n  Prompt: {prompt[:50]}...")
            logger.info(f"  Layer: {result_analysis.layer.value} (expected: {expected_layer})")
            logger.info(f"  Tier: {tier} (expected: {expected_tier})")
            logger.info(f"  Confidence: {result_analysis.confidence:.2f}")
            logger.info(f"  Complexity: {result_analysis.complexity_score:.2f}")
            
            # 2. Estimate cost
            estimate = cost_service.estimate_request_cost(
                tier=tier,
                input_tokens=len(prompt.split()) * 10,
                output_tokens=200
            )
            logger.info(f"  Estimated cost: ${estimate.estimated_cost:.4f}")
            
            # 3. Check budget
            check = cost_service.check_budget(
                user_id="test_user",
                requested_tier=tier,
                estimated_cost=estimate.estimated_cost,
                soft_limit=16.0,
                hard_limit=20.0
            )
            logger.info(f"  Budget check: {check['recommendation']}")
            
            # 4. Record if approved
            if check["ok"]:
                record = cost_service.record_request(
                    user_id="test_user",
                    tier=tier,
                    request_id=f"req_{prompt[:20]}",
                    input_tokens=len(prompt.split()) * 10,
                    output_tokens=200,
                    cognitive_layer=result_analysis.layer.value
                )
                logger.info(f"  ✓ Request recorded")
        
        # Get final spending snapshot
        spending = cost_service.get_user_spending("test_user", days=7)
        logger.info(f"\n📊 Final Spending:")
        logger.info(f"  Total: ${spending.total_cost:.2f}")
        logger.info(f"  Requests: {spending.request_count}")
        logger.info(f"  Tiers: {spending.tier_breakdown}")


# ═══════════════════════════════════════════════════════════════════════════════
# Run Tests
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    pytest.main([__file__, "-v", "-s"])
