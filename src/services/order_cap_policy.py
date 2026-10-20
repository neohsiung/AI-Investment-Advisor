"""
Single read point for the per-order USD cap shared by batch deployment, rotation buys, rebalance ramp-in and the
proposal shadow sizing. Settings family: ``order_caps`` in config/settings_families.yaml.
批次建倉、換庫買進、再平衡逐步建倉與提案影子定額共用的單筆金額上限讀取點。

Precedence (documented in config/settings_families.yaml, not enforced here):
mission bounds > tradable_capital_pct > tradable_capital_usd > single order cap.
This helper only returns the last one; the earlier ones bound the whole budget elsewhere.

DOCUMENTED EXCEPTION: ``benchmark_parking_max_order_usd`` (default 250) keeps its own, intentionally larger cap
(human-approved). Parking does NOT call this helper.
文件化的例外：benchmark_parking_max_order_usd（預設 250）為人工核准之刻意較大的獨立上限，不經此函式。

Failure rule: an unreadable, non-numeric, non-finite or <= 0 value yields the schema default with a WARNING -
never a larger number.
讀取失敗或值非法一律回 schema 預設值並以 warning 記錄，絕不回傳更大的數字。
"""
from __future__ import annotations

import logging
import math
from typing import Any, Optional

from src.config.settings_schema import schema_default
from src.services.param_policy import get_param

logger = logging.getLogger(__name__)

SINGLE_ORDER_CAP_KEY = "batch_deploy_max_order_usd"


def default_single_order_cap_usd() -> float:
    """Schema default of the single-order cap. / 單筆上限的 schema 預設值。"""
    return float(schema_default(SINGLE_ORDER_CAP_KEY))


def single_order_cap_usd(settings_service: Any, user_id: Optional[str]) -> float:
    """Current single-order USD cap (always > 0). / 目前的單筆金額上限（恆大於 0）。"""
    default = default_single_order_cap_usd()
    try:
        # G10: read through param_policy (settings_service/user_id kept for signature compatibility).
        # G10：改經 param_policy 讀取（保留 settings_service/user_id 以維持簽章）。
        r = get_param(SINGLE_ORDER_CAP_KEY)
        raw = r.value
        if r.fallback_reason:
            logger.warning("%s fallback (%s); value %r", SINGLE_ORDER_CAP_KEY, r.fallback_reason, raw)
        if raw is None:
            return default
        val = float(raw)
        if math.isfinite(val) and val > 0:
            return val
        logger.warning("%s=%r is not a positive number; using schema default %s", SINGLE_ORDER_CAP_KEY, raw, default)
    except Exception as e:
        logger.warning("%s unreadable (%s); using schema default %s", SINGLE_ORDER_CAP_KEY, e, default)
    return default
