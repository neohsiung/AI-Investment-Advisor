"""
LLM Tier Definitions
"""
from enum import Enum

class LLMTier(str, Enum):
    NANO = "nano"
    FAST = "fast"
    SMART = "smart"
    ADVANCED = "advanced"

    @classmethod
    def from_string(cls, value: str) -> "LLMTier":
        """Convert string to LLMTier, defaulting to FAST if unknown."""
        try:
            return cls(value.lower())
        except ValueError:
            return cls.FAST
