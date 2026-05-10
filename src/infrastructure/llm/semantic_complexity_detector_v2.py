"""
AST-based Semantic Complexity Detection v2 — Week 1 Implementation
AST 語義複雜度檢測 v2 — Week 1 實現

Enhanced complexity analysis with 7 feature extractors:
  1. Structural Features (clause depth, conditions, loops, queries, references)
  2. Semantic Features (concept count, causal chains, uncertainty, multi-step logic)
  3. Temporal Features (time spans, sequence length, frequency changes)
  4. Numerical Features (precision, operations, comparisons)
  5. Domain Features (tickers, indices, derivatives, risk factors, regulatory refs)
  6. Intent Features (decision type, portfolio size)
  7. Context Features (conversation depth, entity references, contradictions)

Classification: REFLEXIVE (0.0-0.2) → FAST_THINK (0.2-0.5) → MEMORY_DIG (0.5-0.8) → DEEP_RESEARCH (0.8-1.0)

Accuracy target: >90% on historical test set
Cost impact: 30-40% token reduction via tier optimization
"""

import re
import logging
import math
from dataclasses import dataclass
from typing import Dict, Optional, List, Any, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class CognitiveLayer(Enum):
    """Cognitive layers mapped to LLM tiers."""
    REFLEXIVE = "reflexive"              # nano: classification, routing
    FAST_THINK = "fast_think"            # fast: summarization, extraction
    MEMORY_DIG = "memory_dig"            # smart: analysis, reasoning
    DEEP_RESEARCH = "deep_research"      # advanced: strategy, CIO decisions


# ═══════════════════════════════════════════════════════════════════════════════
# Feature Dataclasses (7 categories)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class StructuralFeatures:
    """語法結構複雜度 — Syntactic structure complexity"""
    clause_depth: int           # Max nesting of conditionals/loops
    condition_count: int        # IF/THEN/ELSE branches
    loop_count: int            # FOR/WHILE/REPEAT patterns
    nested_queries: int        # Multi-level sub-queries
    reference_count: int       # Cross-references to entities/concepts
    
    def complexity_score(self, text_length: int = 0) -> float:
        """0.0 (simple) to 1.0 (very complex)"""
        length_factor = min(1.0, text_length / 1000.0)
        return min(1.0, 
            self.clause_depth * 0.3 +
            math.log(self.condition_count + 1) * 0.2 +
            self.nested_queries * 0.3 +
            self.reference_count * 0.1 +
            length_factor * 0.1
        )


@dataclass
class SemanticFeatures:
    """語義複雜度 — Semantic complexity"""
    concept_count: int         # Unique financial/domain concepts
    causal_chains: int         # A→B→C dependencies
    uncertainty_markers: int   # "may", "could", "might", "uncertain"
    multi_step_logic: int      # Multi-part reasoning
    
    def complexity_score(self) -> float:
        """0.0 to 1.0"""
        return min(1.0,
            math.log(self.concept_count + 1) * 0.3 +
            self.causal_chains * 0.3 +
            self.uncertainty_markers * 0.2 +
            self.multi_step_logic * 0.2
        )


@dataclass
class TemporalFeatures:
    """時間跨度和序列複雜度 — Temporal span and sequence complexity"""
    time_spans: int            # Number of distinct time periods
    sequence_length: int       # Length of time series
    frequency_changes: int     # Number of frequency shifts
    
    def complexity_score(self) -> float:
        """0.0 to 1.0"""
        return min(1.0,
            self.time_spans * 0.25 +
            math.log(self.sequence_length + 1) * 0.5 +
            self.frequency_changes * 0.25
        )


@dataclass
class NumericalFeatures:
    """數值精度和操作複雜度 — Numerical precision and operation complexity"""
    precision_level: float     # Decimal places needed (0.0-1.0 scale)
    operation_complexity: int  # Count of +,-,*,/,%
    comparison_chains: int     # A < B < C chains
    
    def complexity_score(self) -> float:
        return min(1.0,
            math.log(self.precision_level + 1) * 0.2 +
            math.log(self.operation_complexity + 1) * 0.4 +
            self.comparison_chains * 0.4
        )


@dataclass
class DomainFeatures:
    """投資領域特定複雜度 — Domain-specific (Financial) complexity"""
    ticker_count: int
    market_indices: int        # S&P, VIX, etc.
    derivative_types: int      # Options, futures, swaps
    risk_factor_count: int     # Market, credit, liquidity, etc.
    regulatory_refs: int       # SEC, Fed, etc.
    
    def complexity_score(self) -> float:
        return min(1.0,
            math.log(self.ticker_count + 1) * 0.1 +
            self.market_indices * 0.2 +
            self.derivative_types * 0.3 +
            self.risk_factor_count * 0.2 +
            self.regulatory_refs * 0.2
        )


@dataclass
class IntentFeatures:
    """動作類型和風險程度 — Action type and risk level"""
    is_portfolio_decision: bool
    is_trade_execution: bool
    is_risk_assessment: bool
    is_optimization: bool
    portfolio_size: float      # Dollar amount involved
    
    def complexity_score(self) -> float:
        base = 0.1 if not any([
            self.is_portfolio_decision,
            self.is_trade_execution,
            self.is_risk_assessment
        ]) else 0.5
        
        # High-risk decisions get boost
        if self.is_trade_execution or self.is_risk_assessment:
            base += 0.3
        
        if self.portfolio_size > 1_000_000:
            base += 0.1
            
        return min(1.0, base)


@dataclass
class ContextFeatures:
    """上文依賴和歷史 — Context dependency and history"""
    conversation_turn: int     # How deep is the conversation?
    referenced_entities: int   # Prior mentioned entities
    contradictions: int        # Conflicting statements
    
    def complexity_score(self) -> float:
        return min(1.0,
            math.log(self.conversation_turn + 1) * 0.4 +
            math.log(self.referenced_entities + 1) * 0.3 +
            self.contradictions * 0.3
        )


@dataclass
class ComplexityResult:
    """Result of complexity analysis."""
    layer: CognitiveLayer
    confidence: float                      # 0.0-1.0
    base_layer: CognitiveLayer
    complexity_score: float               # 0.0-1.0
    adjustments: Dict[str, float]
    features: Dict[str, Any]
    reasoning: str


# ═══════════════════════════════════════════════════════════════════════════════
# AST Complexity Detector v2
# ═══════════════════════════════════════════════════════════════════════════════

class SemanticComplexityDetectorV2:
    """
    Enhanced complexity detector with 7 feature extractors.
    
    使用 7 個特徵提取器的增強複雜度檢測器。
    """
    
    # Complexity thresholds for layer assignment
    COMPLEXITY_THRESHOLDS = {
        # (lower, upper): layer
        (0.0, 0.2): CognitiveLayer.REFLEXIVE,
        (0.2, 0.5): CognitiveLayer.FAST_THINK,
        (0.5, 0.8): CognitiveLayer.MEMORY_DIG,
        (0.8, 1.0): CognitiveLayer.DEEP_RESEARCH,
    }
    
    # Domain keywords (financial)
    FINANCIAL_KEYWORDS = {
        "stock", "equity", "bond", "derivative", "option", "future", "swap",
        "portfolio", "allocation", "rebalance", "rebalancing", "hedge", "margin", "risk",
        "volatility", "correlation", "dividend", "yield", "return", "loss",
        "leverage", "short", "long", "bull", "bear", "bull call", "bear put",
        "strategy", "optimize", "optimization"
    }
    
    # Market indices
    MARKET_INDICES = {"sp500", "s&p", "nasdaq", "dow", "vix", "dxy", "indu"}
    
    # Regulatory bodies
    REGULATORY_KEYWORDS = {"sec", "fed", "finra", "occ", "cbot", "cme", "doj"}
    
    # Risk factors
    RISK_FACTORS = {"market", "credit", "liquidity", "operational", "systemic", "tail"}
    
    # Derivatives
    DERIVATIVES = {"option", "future", "swap", "forward", "swaption", "straddle", "spread", "call", "put", "calls", "puts"}
    
    # Uncertainty markers
    UNCERTAINTY_MARKERS = {"may", "might", "could", "uncertain", "unclear", "ambiguous", "risky"}
    
    # Causal/intent markers
    CAUSAL_MARKERS = {"if", "then", "because", "therefore", "thus", "hence", "so", "because"}
    DECISION_KEYWORDS = {"decide", "recommend", "suggest", "should", "must", "execute", "trade"}
    
    def __init__(self):
        """Initialize detector."""
        pass
    
    def analyze(self, request: str, context: Optional[Dict] = None) -> ComplexityResult:
        """
        Analyze request complexity and assign cognitive layer.
        
        Args:
            request: User input text
            context: Optional contextual metadata (agent_name, user_id, conversation_turn, etc.)
        
        Returns:
            ComplexityResult with layer assignment, confidence, and feature breakdown
        """
        context = context or {}
        
        # Normalize text
        normalized = self._normalize_text(request)
        
        # Extract all 7 feature categories
        structural = self._extract_structural_features(normalized)
        semantic = self._extract_semantic_features(normalized)
        temporal = self._extract_temporal_features(normalized)
        numerical = self._extract_numerical_features(normalized)
        domain = self._extract_domain_features(normalized)
        intent = self._extract_intent_features(normalized, context)
        context_features = self._extract_context_features(context)
        
        # Compute overall complexity score
        complexity_score = self._compute_complexity_score(
            structural, semantic, temporal, numerical, domain, intent, context_features, len(normalized)
        )
        
        # Classify into cognitive layer
        base_layer = self._classify_layer(complexity_score)
        
        # Apply adjustments (budget, context, etc.)
        adjustments = self._compute_adjustments(context)
        adjusted_score = min(1.0, max(0.0, complexity_score + sum(adjustments.values())))
        final_layer = self._classify_layer(adjusted_score)
        
        # Compute confidence
        confidence = self._compute_confidence(complexity_score, base_layer)
        
        # Build reasoning
        reasoning = self._build_reasoning(
            complexity_score, base_layer, final_layer, structural, semantic, domain, intent
        )
        
        return ComplexityResult(
            layer=final_layer,
            confidence=confidence,
            base_layer=base_layer,
            complexity_score=complexity_score,
            adjustments=adjustments,
            features={
                "structural": {
                    "clause_depth": structural.clause_depth,
                    "condition_count": structural.condition_count,
                    "loop_count": structural.loop_count,
                    "nested_queries": structural.nested_queries,
                    "reference_count": structural.reference_count,
                    "score": structural.complexity_score()
                },
                "semantic": {
                    "concept_count": semantic.concept_count,
                    "causal_chains": semantic.causal_chains,
                    "uncertainty_markers": semantic.uncertainty_markers,
                    "multi_step_logic": semantic.multi_step_logic,
                    "score": semantic.complexity_score()
                },
                "temporal": {
                    "time_spans": temporal.time_spans,
                    "sequence_length": temporal.sequence_length,
                    "frequency_changes": temporal.frequency_changes,
                    "score": temporal.complexity_score()
                },
                "numerical": {
                    "precision_level": numerical.precision_level,
                    "operation_complexity": numerical.operation_complexity,
                    "comparison_chains": numerical.comparison_chains,
                    "score": numerical.complexity_score()
                },
                "domain": {
                    "ticker_count": domain.ticker_count,
                    "market_indices": domain.market_indices,
                    "derivative_types": domain.derivative_types,
                    "risk_factor_count": domain.risk_factor_count,
                    "regulatory_refs": domain.regulatory_refs,
                    "score": domain.complexity_score()
                },
                "intent": {
                    "is_portfolio_decision": intent.is_portfolio_decision,
                    "is_trade_execution": intent.is_trade_execution,
                    "is_risk_assessment": intent.is_risk_assessment,
                    "is_optimization": intent.is_optimization,
                    "portfolio_size": intent.portfolio_size,
                    "score": intent.complexity_score()
                },
                "context": {
                    "conversation_turn": context_features.conversation_turn,
                    "referenced_entities": context_features.referenced_entities,
                    "contradictions": context_features.contradictions,
                    "score": context_features.complexity_score()
                }
            },
            reasoning=reasoning
        )
    
    def recommend_tier(self, result: ComplexityResult) -> str:
        """
        Recommend tier (nano, fast, smart, advanced) based on layer.
        
        Args:
            result: ComplexityResult from analyze()
        
        Returns:
            Tier name: "nano", "fast", "smart", "advanced"
        """
        mapping = {
            CognitiveLayer.REFLEXIVE: "nano",
            CognitiveLayer.FAST_THINK: "fast",
            CognitiveLayer.MEMORY_DIG: "smart",
            CognitiveLayer.DEEP_RESEARCH: "advanced"
        }
        return mapping.get(result.layer, "fast")
    
    # ───────────────────────────────────────────────────────────────────────────
    # Feature Extractors (7 categories)
    # ───────────────────────────────────────────────────────────────────────────
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text for analysis."""
        # Lowercase, remove extra whitespace, normalize punctuation
        text = text.lower()
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    
    def _extract_structural_features(self, text: str) -> StructuralFeatures:
        """Extract syntactic structure complexity."""
        # Clause depth: count nested parentheses
        max_depth = 0
        current_depth = 0
        for char in text:
            if char in '([{':
                current_depth += 1
                max_depth = max(max_depth, current_depth)
            elif char in ')]}':
                current_depth = max(0, current_depth - 1)
        
        # Condition count: count if/then/else patterns
        condition_pattern = r'\b(if|then|else|elif|and|or|when|while)\b'
        condition_count = len(re.findall(condition_pattern, text))
        
        # Loop count: count for/while patterns
        loop_pattern = r'\b(for|while|repeat|foreach|loop)\b'
        loop_count = len(re.findall(loop_pattern, text))
        
        # Nested queries: count sub-query patterns
        nested_query_pattern = r'(select|where|from|join|group\s+by|order\s+by)'
        nested_queries = len(re.findall(nested_query_pattern, text))
        
        # Reference count: count mentions of entities
        reference_pattern = r'\b[A-Z][A-Z0-9]+(?:\.[A-Z]+)?\b'
        reference_count = len(re.findall(reference_pattern, text))
        
        return StructuralFeatures(
            clause_depth=max_depth,
            condition_count=condition_count,
            loop_count=loop_count,
            nested_queries=nested_queries,
            reference_count=reference_count
        )
    
    def _extract_semantic_features(self, text: str) -> SemanticFeatures:
        """Extract semantic complexity."""
        # Concept count: count unique domain concepts
        words = set(text.split())
        financial_concepts = len(words & self.FINANCIAL_KEYWORDS)
        
        # Causal chains: count causal markers
        causal_count = len(re.findall(r'\b(' + '|'.join(self.CAUSAL_MARKERS) + r')\b', text))
        
        # Uncertainty markers
        uncertainty_count = len(re.findall(r'\b(' + '|'.join(self.UNCERTAINTY_MARKERS) + r')\b', text))
        
        # Multi-step logic: count question marks, numbers, lists
        multi_step_count = text.count('?') + len(re.findall(r'\d+\.', text))
        
        return SemanticFeatures(
            concept_count=financial_concepts,
            causal_chains=causal_count,
            uncertainty_markers=uncertainty_count,
            multi_step_logic=multi_step_count
        )
    
    def _extract_temporal_features(self, text: str) -> TemporalFeatures:
        """Extract temporal complexity."""
        # Time spans: count date patterns and time periods
        date_pattern = r'(\d{4}[-/]\d{2}[-/]\d{2}|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december|q[1-4]|\byear\b|\bmonth\b|\bweek\b|\bday\b)'
        time_spans = len(set(re.findall(date_pattern, text)))
        
        # Sequence length: estimate from references to time series
        sequence_pattern = r'(series|trend|historical|backtest|candlestick|ohlc|volatility|correlation)'
        sequence_length = len(re.findall(sequence_pattern, text)) * 10
        
        # Frequency changes: count mentions of different frequencies
        freq_pattern = r'(daily|weekly|monthly|quarterly|annual|minute|hour|intraday)'
        frequency_changes = len(set(re.findall(freq_pattern, text)))
        
        return TemporalFeatures(
            time_spans=time_spans,
            sequence_length=sequence_length,
            frequency_changes=frequency_changes
        )
    
    def _extract_numerical_features(self, text: str) -> NumericalFeatures:
        """Extract numerical complexity."""
        # Precision level: detect decimal places
        decimals = re.findall(r'\d+\.\d+', text)
        max_precision = max([len(d.split('.')[1]) for d in decimals] if decimals else [0])
        precision_level = min(1.0, max_precision / 10.0)
        
        # Operation complexity: count arithmetic operators
        operations = len(re.findall(r'[+\-*/%<>=]', text))
        
        # Comparison chains: count consecutive comparisons
        comparison_chains = len(re.findall(r'\d+\s*[<>]=?\s*\d+', text))
        
        return NumericalFeatures(
            precision_level=precision_level,
            operation_complexity=operations,
            comparison_chains=comparison_chains
        )
    
    def _extract_domain_features(self, text: str) -> DomainFeatures:
        """Extract domain-specific (financial) complexity."""
        # Ticker count: count stock ticker patterns
        ticker_pattern = r'\b[A-Z]{1,5}(?:\s*[-/]\s*[A-Z]{1,5})?\b'
        tickers = len(re.findall(ticker_pattern, text))
        
        # Market indices - more flexible matching
        market_indices_matches = []
        for idx in self.MARKET_INDICES:
            market_indices_matches.extend(re.findall(r'\b' + re.escape(idx) + r'\b', text, re.IGNORECASE))
        market_indices = len(market_indices_matches)
        
        # Derivative types
        derivative_matches = []
        for deriv in self.DERIVATIVES:
            derivative_matches.extend(re.findall(r'\b' + re.escape(deriv) + r'\b', text, re.IGNORECASE))
        derivative_count = len(derivative_matches)
        
        # Risk factors
        risk_factors_matches = []
        for risk in self.RISK_FACTORS:
            risk_factors_matches.extend(re.findall(r'\b' + re.escape(risk) + r'\b', text, re.IGNORECASE))
        risk_factors = len(risk_factors_matches)
        
        # Regulatory references
        regulatory_matches = []
        for reg in self.REGULATORY_KEYWORDS:
            regulatory_matches.extend(re.findall(r'\b' + re.escape(reg) + r'\b', text, re.IGNORECASE))
        regulatory_count = len(regulatory_matches)
        
        return DomainFeatures(
            ticker_count=tickers,
            market_indices=market_indices,
            derivative_types=derivative_count,
            risk_factor_count=risk_factors,
            regulatory_refs=regulatory_count
        )
    
    def _extract_intent_features(self, text: str, context: Dict) -> IntentFeatures:
        """Extract intent and risk level."""
        # Decision type detection
        is_portfolio_decision = bool(re.search(r'portfolio|allocation|rebalance|adjust|modify', text, re.IGNORECASE))
        is_trade_execution = bool(re.search(r'buy|sell|trade|execute|place|order|short|long', text, re.IGNORECASE))
        is_risk_assessment = bool(re.search(r'risk|hedge|protect|downside|upside|vega|delta', text, re.IGNORECASE))
        is_optimization = bool(re.search(r'optimi[sz]|efficient|maximi[sz]|minimi[sz]', text, re.IGNORECASE))
        
        # Portfolio size: extract dollar amounts
        portfolio_size = 0.0
        
        # Pattern 1: $XXM or $XXK (e.g., $5M, $100K)
        amount_match = re.search(r'\$(\d+(?:\.\d+)?)\s*(M|K|B|million|billion|k|m|bn)\b', text, re.IGNORECASE)
        if amount_match:
            value = float(amount_match.group(1))
            unit = amount_match.group(2).lower()
            if unit in ['m', 'million']:
                portfolio_size = value * 1e6
            elif unit in ['k', 'k']:
                portfolio_size = value * 1e3
            elif unit in ['b', 'bn', 'billion']:
                portfolio_size = value * 1e9
        
        # Pattern 2: numeric value with text (e.g., 5 million, 100 thousand)
        if portfolio_size == 0:
            amount_match = re.search(r'(\d+(?:\.\d+)?)\s*(million|billion|thousand|k|m|bn)\b', text, re.IGNORECASE)
            if amount_match:
                value = float(amount_match.group(1))
                unit = amount_match.group(2).lower()
                if unit in ['million', 'm']:
                    portfolio_size = value * 1e6
                elif unit in ['thousand', 'k']:
                    portfolio_size = value * 1e3
                elif unit in ['billion', 'bn', 'b']:
                    portfolio_size = value * 1e9
        
        return IntentFeatures(
            is_portfolio_decision=is_portfolio_decision,
            is_trade_execution=is_trade_execution,
            is_risk_assessment=is_risk_assessment,
            is_optimization=is_optimization,
            portfolio_size=portfolio_size
        )
    
    def _extract_context_features(self, context: Dict) -> ContextFeatures:
        """Extract context-based complexity."""
        conversation_turn = context.get("conversation_turn", 0)
        referenced_entities = context.get("referenced_entities", 0)
        contradictions = context.get("contradictions", 0)
        
        return ContextFeatures(
            conversation_turn=conversation_turn,
            referenced_entities=referenced_entities,
            contradictions=contradictions
        )
    
    # ───────────────────────────────────────────────────────────────────────────
    # Scoring & Classification
    # ───────────────────────────────────────────────────────────────────────────
    
    def _compute_complexity_score(self,
                                  structural: StructuralFeatures,
                                  semantic: SemanticFeatures,
                                  temporal: TemporalFeatures,
                                  numerical: NumericalFeatures,
                                  domain: DomainFeatures,
                                  intent: IntentFeatures,
                                  context: ContextFeatures,
                                  text_length: int) -> float:
        """
        Weighted combination of all feature categories.
        Returns score in [0.0, 1.0].
        """
        weights = {
            'structural': 0.05,
            'semantic': 0.15,
            'temporal': 0.10,
            'numerical': 0.10,
            'domain': 0.25,
            'intent': 0.30,
            'context': 0.05
        }
        
        scores = [
            structural.complexity_score(text_length) * weights['structural'],
            semantic.complexity_score() * weights['semantic'],
            temporal.complexity_score() * weights['temporal'],
            numerical.complexity_score() * weights['numerical'],
            domain.complexity_score() * weights['domain'],
            intent.complexity_score() * weights['intent'],
            context.complexity_score() * weights['context'],
        ]
        
        return min(1.0, sum(scores))
    
    def _classify_layer(self, complexity_score: float) -> CognitiveLayer:
        """Assign to cognitive layer based on complexity."""
        for (lower, upper), layer in self.COMPLEXITY_THRESHOLDS.items():
            if lower <= complexity_score < upper:
                return layer
        return CognitiveLayer.DEEP_RESEARCH
    
    def _compute_adjustments(self, context: Dict) -> Dict[str, float]:
        """Compute complexity adjustments based on context."""
        adjustments = {}
        
        # Budget constraint adjustment
        if context.get("budget_critical", False):
            adjustments["budget_downgrade"] = -0.1
        
        # High-priority adjustment
        if context.get("high_priority", False):
            adjustments["priority_boost"] = 0.1
        
        return adjustments
    
    def _compute_confidence(self, complexity_score: float, layer: CognitiveLayer) -> float:
        """
        Compute confidence in the layer assignment.
        Higher confidence near layer boundaries.
        """
        # Find which threshold band we're in
        for (lower, upper), _ in self.COMPLEXITY_THRESHOLDS.items():
            if lower <= complexity_score < upper:
                # Distance from boundaries
                dist_from_lower = complexity_score - lower
                dist_from_upper = upper - complexity_score
                min_dist = min(dist_from_lower, dist_from_upper)
                range_width = upper - lower
                # Confidence decreases near boundaries
                return 1.0 - (min_dist / range_width) * 0.5
        
        return 0.8
    
    def _build_reasoning(self,
                        complexity_score: float,
                        base_layer: CognitiveLayer,
                        final_layer: CognitiveLayer,
                        structural: StructuralFeatures,
                        semantic: SemanticFeatures,
                        domain: DomainFeatures,
                        intent: IntentFeatures) -> str:
        """Build human-readable reasoning."""
        parts = []
        
        parts.append(f"Complexity score: {complexity_score:.2f}")
        parts.append(f"Base layer: {base_layer.value}")
        if base_layer != final_layer:
            parts.append(f"Adjusted to: {final_layer.value}")
        
        # Top contributing factors
        if structural.clause_depth > 2:
            parts.append(f"High structural complexity (depth={structural.clause_depth})")
        if semantic.concept_count > 3:
            parts.append(f"Multiple financial concepts (count={semantic.concept_count})")
        if domain.ticker_count > 2:
            parts.append(f"Multiple assets involved (tickers={domain.ticker_count})")
        if intent.is_trade_execution:
            parts.append("Trade execution request (high priority)")
        if intent.portfolio_size > 100_000:
            parts.append(f"Large portfolio size (${intent.portfolio_size:,.0f})")
        
        return " | ".join(parts)
