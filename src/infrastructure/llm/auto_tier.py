"""
Auto tier selection — wire the (free, heuristic) semantic complexity detector
into the live routing path.

自動難度分層：把純啟發式（零成本）的語意複雜度偵測器接進實際路由。

Design decision (2026-07-11): DOWNSHIFT-ONLY.
- The caller declares a tier per task (the ceiling / intent).
- The detector may LOWER it when it is confident the prompt is simple
  (e.g. classification/extraction → nano/fast), saving cost.
- It never RAISES the tier above the caller's declared value: in a
  production trading system, silently upshifting is a budget risk and
  silently downshifting a genuinely complex task would hurt decision
  quality — so we only move in the safe direction and require confidence.
- Any error, low confidence, or disabled flag → return the declared tier
  unchanged. This function must never break a call.

設計（2026-07-11）：只降級。呼叫方宣告的 tier 是上限/意圖；偵測器只在
「有信心該任務簡單」時往下調（省成本），絕不往上調（避免預算風險與誤判
複雜任務被降級傷品質）。任何錯誤/低信心/停用 → 原封不動回傳宣告的 tier。
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# nano < fast < smart < advanced
_TIER_RANK = {"nano": 0, "fast": 1, "smart": 2, "advanced": 3}
_RANK_TIER = {v: k for k, v in _TIER_RANK.items()}

# Do not downshift when the detector is not reasonably sure the task is simple.
_MIN_CONFIDENCE = 0.5


def _enabled() -> bool:
    return os.getenv("AUTO_TIER_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


def resolve_effective_tier(declared_tier: str, text: str, *, agent_name: str = "") -> str:
    """
    Return the effective tier for a call, downshifting from ``declared_tier``
    only when the complexity detector is confident the prompt is simpler.

    Never raises; on any problem returns ``declared_tier`` unchanged.
    """
    declared = (declared_tier or "fast").strip().lower()
    if not _enabled() or declared not in _TIER_RANK or not text:
        return declared

    # Only optimize the L1-L2 band (nano/fast). A caller that explicitly asks for
    # smart/advanced is making a deliberate escalation (e.g. Thematic deep analysis,
    # council debate) — never silently downshift those, the heuristic under-rates
    # genuinely complex prompts. 只優化 L1-L2；smart/advanced 為刻意升級，一律尊重。
    if _TIER_RANK[declared] >= _TIER_RANK["smart"]:
        return declared

    try:
        # Import lazily so a detector import error can never break agent init.
        from src.infrastructure.llm.semantic_complexity_detector_v2 import (
            SemanticComplexityDetectorV2,
        )

        detector = SemanticComplexityDetectorV2()
        result = detector.analyze(text)
        confidence = getattr(result, "confidence", 0.0) or 0.0
        if confidence < _MIN_CONFIDENCE:
            return declared

        recommended = detector.recommend_tier(result)
        if recommended not in _TIER_RANK:
            return declared

        # Downshift-only: take the lower of declared vs recommended.
        effective_rank = min(_TIER_RANK[declared], _TIER_RANK[recommended])
        effective = _RANK_TIER[effective_rank]

        if effective != declared:
            logger.info(
                "auto_tier: %s downshift %s -> %s (conf=%.2f, layer=%s)",
                agent_name or "agent",
                declared,
                effective,
                confidence,
                getattr(getattr(result, "layer", None), "value", "?"),
            )
        return effective
    except Exception as exc:  # pragma: no cover - defensive, must never break a call
        logger.debug("auto_tier: detector failed (%s); using declared tier %s", exc, declared)
        return declared
