"""
Infrastructure Governance Module.
包含外部配額控制、頻率節流與資源守衛。
"""
from src.infrastructure.governance.quota_governor import (
    ExternalQuotaGovernor,
    QuotaRule,
    DEFAULT_RULES,
)

__all__ = ["ExternalQuotaGovernor", "QuotaRule", "DEFAULT_RULES"]
