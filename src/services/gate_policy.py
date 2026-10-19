"""
Adaptive gate policy v0 — may only TIGHTEN, never loosen (plan K2). Pure: no I/O, not wired.
自適應閘門 v0——只能收緊、絕不放寬（計畫 K2）。純函式、無 I/O、尚未接線。

Contract / 契約:
  * `approved_ceiling` is the human-approved bound (trust, score_delta_floor, mode). The result is never looser:
      trust <= ceiling trust, score_delta >= floor, mode never above the approved mode.
  * Evidence can tighten further: n >= N_MIN and mean + se < 0 drops trust one level and raises score_delta;
    any K-breach flag, validator errors, or repeated execution failures force mode 'observe'.
  * Missing / NaN / malformed input -> most conservative result with `_insufficient_data=True`.
  * Loosening is never computed here. Under ADR-003 it belongs to the charter change engine (five-condition
    test, registered keys only); outside that engine it stays a human settings write.
  * 放寬永不在此計算；依 ADR-003 由章程變更引擎（五條件檢定、僅限登錄鍵）處理，引擎之外仍為人工設定寫入。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional

TRUST_LEVELS = (0.0, 0.5, 1.0)
DELTA_MIN = 0.0
DELTA_MAX = 2.0
DELTA_TIGHTEN_STEP = 0.5
EVIDENCE_MIN_N = 10
EXEC_FAILED_7D_LIMIT = 2
MODE_RANK = {"observe": 0, "enforce": 1}


@dataclass(frozen=True)
class GatePolicy:
    trust: float
    score_delta: float
    effective_mode: str
    _insufficient_data: bool = False


def _most_conservative(insufficient: bool = True) -> GatePolicy:
    return GatePolicy(trust=TRUST_LEVELS[0], score_delta=DELTA_MAX, effective_mode="observe",
                      _insufficient_data=insufficient)


def _num(v: Any) -> Optional[float]:
    """Finite float or None (bool and strings are not numbers here). / 有限浮點數，否則 None。"""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    f = float(v)
    return f if math.isfinite(f) else None


def _snap_trust_down(t: float) -> float:
    """Largest allowed level <= t (clamped into range). / 取不超過 t 的最大信任等級。"""
    return max([lv for lv in TRUST_LEVELS if lv <= t] or [TRUST_LEVELS[0]])


def compute_gate_policy(summary: Any) -> GatePolicy:
    if not isinstance(summary, dict):
        return _most_conservative()
    ceil = summary.get("approved_ceiling")
    if not isinstance(ceil, dict):
        return _most_conservative()
    c_trust = _num(ceil.get("trust"))
    c_floor = _num(ceil.get("score_delta_floor"))
    c_mode = ceil.get("mode")
    n = _num(summary.get("n"))
    mean = _num(summary.get("mean"))
    se = _num(summary.get("se"))
    errs = _num(summary.get("validator_error_count"))
    failed = _num(summary.get("exec_failed_7d"))
    k_breach = summary.get("k_breach")
    if (None in (c_trust, c_floor, n, mean, se, errs, failed)
            or c_mode not in MODE_RANK or not isinstance(k_breach, bool)):
        return _most_conservative()

    trust = _snap_trust_down(c_trust)
    delta = min(max(c_floor, DELTA_MIN), DELTA_MAX)
    mode = c_mode

    if n >= EVIDENCE_MIN_N and mean + se < 0:
        trust = TRUST_LEVELS[max(TRUST_LEVELS.index(trust) - 1, 0)]
        delta = min(delta + DELTA_TIGHTEN_STEP, DELTA_MAX)
    if k_breach or errs > 0 or failed >= EXEC_FAILED_7D_LIMIT:
        mode = "observe"
    return GatePolicy(trust=trust, score_delta=delta, effective_mode=mode)
