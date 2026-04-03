"""
Budget Aware Model Router — Phase 6 Application Service.
具備預算意識的模型路由器 — Phase 6 應用服務。

[DEPRECATED] This module has moved to src.infrastructure.llm.
請改用 src.infrastructure.llm.budget_aware_model_router。
"""

import warnings
from src.infrastructure.llm.budget_aware_model_router import BudgetAwareModelRouter

# Emit deprecation warning when this module is imported
warnings.warn(
    "src.services.budget_aware_model_router is deprecated. "
    "Please use 'from src.infrastructure.llm import BudgetAwareModelRouter' instead.",
    DeprecationWarning,
    stacklevel=2
)

__all__ = ["BudgetAwareModelRouter"]
