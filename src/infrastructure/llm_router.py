"""
[DEPRECATED] 此模組保留僅為向後相容。
請改用: from src.infrastructure.llm.council_tier_router import CouncilTierRouter
"""
import warnings
from src.infrastructure.llm.council_tier_router import CouncilTierRouter as _CouncilTierRouter


class DynamicModelRouter(_CouncilTierRouter):
    """[DEPRECATED] Use CouncilTierRouter instead."""

    def __init__(self, *args, **kwargs):
        warnings.warn(
            "DynamicModelRouter is deprecated. Use CouncilTierRouter instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(*args, **kwargs)


__all__ = ["DynamicModelRouter"]
