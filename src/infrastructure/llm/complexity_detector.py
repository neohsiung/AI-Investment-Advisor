"""
AST-based semantic complexity detection for intelligent tier routing.
用戶請求的語義複雜度分析，用於智能層級路由。

Classifies user requests into cognitive layers:
- REFLEXIVE (nano): Simple factual queries
- FAST_THINK (fast): Moderate analysis tasks
- MEMORY_DIG (smart): Complex reasoning
- DEEP_RESEARCH (advanced): Strategic decisions
"""

import re
import logging
from dataclasses import dataclass
from typing import Dict, Optional, Any
from enum import Enum

logger = logging.getLogger("ComplexityDetector")


class CognitiveLayer(Enum):
    """Cognitive layers mapped to LLM tiers."""
    REFLEXIVE = "reflexive"              # nano: classification, routing
    FAST_THINK = "fast_think"            # fast: summarization, extraction
    MEMORY_DIG = "memory_dig"            # smart: analysis, reasoning
    DEEP_RESEARCH = "deep_research"      # advanced: strategy, CIO decisions


@dataclass
class ComplexityResult:
    """Result of complexity analysis."""
    layer: CognitiveLayer
    confidence: float  # 0.0-1.0
    base_layer: CognitiveLayer
    adjustments: Dict[str, float]
    features: Dict[str, Any]
    reasoning: str


class SemanticComplexityDetector:
    """
    Analyzes user requests to classify cognitive load and assign appropriate LLM tier.
    
    Features analyzed:
    - Request length (character count)
    - Keyword presence (domain-specific scoring)
    - Entity extraction (tickers, dates, numbers)
    - Structure complexity (JSON depth, nesting)
    - Temporal patterns (date ranges, time series)
    - Numerical operations (comparisons, calculations)
    """
    
    # Keywords that escalate complexity
    ESCALATING_KEYWORDS = {
        "strategy": 2, "complex": 2, "analyze": 2, "evaluate": 1,
        "compare": 1, "predict": 2, "recommend": 2, "decide": 3,
        "risk": 2, "tradeoff": 1, "optimization": 2, "explain": 1,
        "reasoning": 2, "deep": 1, "comprehensive": 1
    }
    
    # Keywords that reduce complexity
    DEESCALATING_KEYWORDS = {
        "price": -2, "what": -1, "when": -1, "where": -1,
        "which": -1, "how much": -2, "list": -1, "show": -1,
        "current": -1, "latest": -1, "quick": -1
    }
    
    def __init__(self):
        """Initialize detector with keyword patterns."""
        self.keyword_pattern = self._compile_keyword_patterns()
    
    def analyze(self, request: str, context: Optional[Dict] = None) -> ComplexityResult:
        """
        Analyze request complexity and assign cognitive layer.
        
        Args:
            request: User input text
            context: Optional contextual metadata (agent_name, user_id, etc.)
        
        Returns:
            ComplexityResult with layer assignment and detailed analysis
        """
        if not request:
            return ComplexityResult(
                layer=CognitiveLayer.REFLEXIVE,
                confidence=0.5,
                base_layer=CognitiveLayer.REFLEXIVE,
                adjustments={},
                features={"length": 0},
                reasoning="Empty request → reflexive"
            )
        
        # Step 1: Length-based baseline classification
        base_layer = self._classify_by_length(request)
        
        # Step 2: Extract semantic features
        features = self._extract_features(request)
        
        # Step 3: Keyword scoring and adjustments
        keyword_score = self._score_keywords(request)
        adjustments = {"keyword_adjustment": keyword_score}
        
        # Step 4: Apply all adjustments
        final_layer = self._apply_adjustments(
            base_layer,
            keyword_score,
            features.get("json_depth", 0),
            features.get("has_temporal", False),
            features.get("has_numerical", False),
            features.get("entity_count", 0)
        )
        
        # Step 5: Compute confidence score
        confidence = self._compute_confidence(base_layer, final_layer, features)
        
        # Step 6: Generate reasoning explanation
        reasoning = self._generate_reasoning(
            base_layer, final_layer, features, adjustments, confidence
        )
        
        return ComplexityResult(
            layer=final_layer,
            confidence=confidence,
            base_layer=base_layer,
            adjustments=adjustments,
            features=features,
            reasoning=reasoning
        )
    
    def _classify_by_length(self, request: str) -> CognitiveLayer:
        """Base classification by character length."""
        length = len(request)
        if length < 50:
            return CognitiveLayer.REFLEXIVE
        elif length < 200:
            return CognitiveLayer.FAST_THINK
        elif length < 500:
            return CognitiveLayer.MEMORY_DIG
        else:
            return CognitiveLayer.DEEP_RESEARCH
    
    def _extract_features(self, request: str) -> Dict[str, Any]:
        """Extract semantic features from request."""
        return {
            "length": len(request),
            "word_count": len(request.split()),
            "entity_count": self._extract_entity_count(request),
            "json_depth": self._detect_json_depth(request),
            "has_temporal": self._detect_temporal_patterns(request),
            "has_numerical": self._detect_numerical_comparisons(request),
        }
    
    def _extract_entity_count(self, request: str) -> int:
        """
        Count named entities (tickers, dates, numbers, etc.).
        Simple regex-based extraction.
        """
        # Ticker symbols (e.g., AAPL, MSFT)
        ticker_pattern = r'\b[A-Z]{1,5}\b'
        tickers = re.findall(ticker_pattern, request)
        
        # Dates (e.g., 01/15/2024, 2024-01-15)
        date_pattern = r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{1,2}-\d{1,2}'
        dates = re.findall(date_pattern, request)
        
        # Percentages (e.g., 15%, 0.5%)
        pct_pattern = r'\d+\.?\d*%'
        percentages = re.findall(pct_pattern, request)
        
        # Monetary amounts (e.g., $100, USD 50)
        money_pattern = r'[$£€]\s*\d+\.?\d*|USD\s+\d+\.?\d*'
        amounts = re.findall(money_pattern, request)
        
        # Count unique entities
        return len(set(tickers + dates + percentages + amounts))
    
    def _detect_json_depth(self, request: str) -> int:
        """Detect maximum nesting depth of JSON-like structures."""
        max_depth = 0
        current_depth = 0
        for char in request:
            if char in '{[':
                current_depth += 1
                max_depth = max(max_depth, current_depth)
            elif char in '}]':
                current_depth = max(0, current_depth - 1)
        return max_depth
    
    def _detect_temporal_patterns(self, request: str) -> bool:
        """Detect time series, date ranges, or temporal references."""
        patterns = [
            r'\b(last|past|year|month|week|day|quarter|fiscal)\b',
            r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}',
            r'\b(from|to|between|since|until)\b',
            r'\b(historical|trend|evolution|over time)\b'
        ]
        for pattern in patterns:
            if re.search(pattern, request, re.IGNORECASE):
                return True
        return False
    
    def _detect_numerical_comparisons(self, request: str) -> bool:
        """Detect numerical comparisons or calculations."""
        patterns = [
            r'(>|<|>=|<=|=|vs\.)',
            r'\b(more than|less than|greater than|between|ratio|percentage)\b',
            r'\d+\s*(vs|,|;)\s*\d+'  # Multiple numbers
        ]
        return any(re.search(p, request, re.IGNORECASE) for p in patterns)
    
    def _score_keywords(self, request: str) -> float:
        """
        Score keywords for complexity adjustment.
        Returns a score in range [-3, 3].
        """
        score = 0.0
        request_lower = request.lower()
        
        # Escalating keywords
        for keyword, weight in self.ESCALATING_KEYWORDS.items():
            if keyword in request_lower:
                score += weight
        
        # Deescalating keywords
        for keyword, weight in self.DEESCALATING_KEYWORDS.items():
            if keyword in request_lower:
                score += weight
        
        # Clamp to reasonable range
        return max(-3, min(3, score))
    
    def _apply_adjustments(
        self,
        base_layer: CognitiveLayer,
        keyword_score: float,
        json_depth: int,
        has_temporal: bool,
        has_numerical: bool,
        entity_count: int
    ) -> CognitiveLayer:
        """Apply all adjustments to determine final cognitive layer."""
        adjustment = 0
        
        # Keyword adjustment (primary)
        adjustment += int(keyword_score)
        
        # Structure-based adjustments
        if json_depth > 3:
            adjustment += 1
        if entity_count > 5:
            adjustment += 1
        if has_temporal:
            adjustment += 1
        if has_numerical:
            adjustment += 0.5
        
        # Convert to integer adjustment
        adjustment = int(round(adjustment))
        
        # Map layer to numeric level
        layer_levels = {
            CognitiveLayer.REFLEXIVE: 0,
            CognitiveLayer.FAST_THINK: 1,
            CognitiveLayer.MEMORY_DIG: 2,
            CognitiveLayer.DEEP_RESEARCH: 3,
        }
        
        # Calculate final level
        level = layer_levels[base_layer] + adjustment
        level = max(0, min(3, level))  # Clamp to [0, 3]
        
        # Map back to layer
        reverse_mapping = {
            0: CognitiveLayer.REFLEXIVE,
            1: CognitiveLayer.FAST_THINK,
            2: CognitiveLayer.MEMORY_DIG,
            3: CognitiveLayer.DEEP_RESEARCH,
        }
        
        return reverse_mapping[level]
    
    def _compute_confidence(
        self,
        base_layer: CognitiveLayer,
        final_layer: CognitiveLayer,
        features: Dict
    ) -> float:
        """
        Compute confidence score in the classification.
        Range: [0.0, 1.0]
        """
        base_confidence = 0.5
        
        # High confidence if no adjustments were needed
        if base_layer == final_layer:
            base_confidence += 0.3
        
        # Clear length signals
        length = features.get("length", 0)
        if length < 50 or length > 1000:
            base_confidence += 0.15
        
        # Clear semantic signals
        signal_count = sum([
            features.get("has_temporal", False),
            features.get("has_numerical", False),
            features.get("entity_count", 0) > 3
        ])
        base_confidence += signal_count * 0.05
        
        return min(1.0, base_confidence)
    
    def _generate_reasoning(
        self,
        base_layer: CognitiveLayer,
        final_layer: CognitiveLayer,
        features: Dict,
        adjustments: Dict,
        confidence: float
    ) -> str:
        """Generate human-readable reasoning for the classification."""
        parts = [
            f"Base: {base_layer.value}",
            f"Entities: {features.get('entity_count', 0)}",
            f"Temporal: {features.get('has_temporal', False)}",
            f"Keyword adj: {adjustments.get('keyword_adjustment', 0):+.1f}",
            f"Final: {final_layer.value}",
            f"Confidence: {confidence:.0%}"
        ]
        return " | ".join(parts)
    
    def _compile_keyword_patterns(self):
        """Compile regex patterns for keyword matching."""
        # For future optimization if needed
        pass
    
    def recommend_tier(self, result: ComplexityResult) -> str:
        """
        Convert complexity result to tier name for LLM configuration.
        
        Returns:
            One of: "nano", "fast", "smart", "advanced"
        """
        layer_to_tier = {
            CognitiveLayer.REFLEXIVE: "nano",
            CognitiveLayer.FAST_THINK: "fast",
            CognitiveLayer.MEMORY_DIG: "smart",
            CognitiveLayer.DEEP_RESEARCH: "advanced",
        }
        
        tier = layer_to_tier[result.layer]
        
        # Low confidence → fallback to smart (safeguard)
        if result.confidence < 0.6:
            tier = "smart"
            logger.warning(
                f"Low confidence ({result.confidence:.0%}) classification, "
                f"falling back to 'smart' tier"
            )
        
        return tier


# Testing & Validation
if __name__ == "__main__":
    detector = SemanticComplexityDetector()
    
    test_cases = [
        ("What's AAPL price?", CognitiveLayer.REFLEXIVE),
        ("Show my portfolio", CognitiveLayer.REFLEXIVE),
        ("Summarize tech sector sentiment", CognitiveLayer.FAST_THINK),
        ("Extract key points from earnings report", CognitiveLayer.FAST_THINK),
        ("Analyze TSLA vs GM fundamentals", CognitiveLayer.MEMORY_DIG),
        ("Evaluate portfolio risk", CognitiveLayer.MEMORY_DIG),
        ("Design a long-term strategy considering macro trends", CognitiveLayer.DEEP_RESEARCH),
        ("Recommend rebalancing based on market analysis", CognitiveLayer.DEEP_RESEARCH),
    ]
    
    print("Complexity Detection Validation")
    print("=" * 80)
    
    correct = 0
    for prompt, expected in test_cases:
        result = detector.analyze(prompt)
        is_correct = result.layer == expected
        status = "✓" if is_correct else "✗"
        
        print(f"{status} {prompt[:50]}")
        print(f"  Expected: {expected.value}, Got: {result.layer.value}")
        print(f"  Confidence: {result.confidence:.0%}")
        print(f"  Reasoning: {result.reasoning}")
        print()
        
        if is_correct:
            correct += 1
    
    accuracy = correct / len(test_cases)
    print(f"Accuracy: {accuracy:.1%} ({correct}/{len(test_cases)})")
