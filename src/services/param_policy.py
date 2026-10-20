"""
Single read point (and human-write recorder) for the charter's registered, self-adjustable thresholds.
章程中已登記、可自我調整之門檻的唯一讀取點（含人工寫入記錄）。

Registry: config/parameter_registry.yaml (bounds, rollback value, risk direction, policy). Store: the
``parameter_values`` table (alembic 028). A mission-store entry is a PATH into config/mission.yaml: it is
resolved through ``load_mission()``, its number is never copied here.
登錄檔為 config/parameter_registry.yaml；儲存為 parameter_values；mission 類參數只走路徑解析，不複製數字。

Rules (all enforced by tests/unit/services/test_param_policy.py):
  * The effective value is the stored value (highest version) or, if none, the seed (schema default / mission).
    Until the Change Engine exists nothing but a human write creates a row, so the seed is what comes back.
  * The result is clamped inside the registry bounds. A tighten_only / frozen parameter is never returned
    riskier than the seed (frozen is always the seed). A special value (e.g. 0 = unlimited) is never returned.
  * ANY read failure returns the registry rollback value, logs WARNING and carries ``fallback_reason``;
    never a number riskier than the seed.  Missing data = skip + mark, not a plausible default.
  * Whenever the returned value differs from the stored value (clamped into bounds, pulled back to the seed
    for tighten_only / frozen, or moved off a special value) the result carries ``fallback_reason``
    ('clamped: ...', 'riskier_than_seed: ...', 'frozen: ...' or 'special_value: ...') and ``stored_value``
    keeps what was actually stored.  An unmarked substitution would look like a real answer.
    返回值與儲存值不同時（夾界、拉回 seed、移出特殊值）一律帶 fallback_reason，並以 stored_value 保留原值。
  * tradable_capital_pct: bounds.min is 1, so a human-stored 0 ("stop all trading") is clamped to 1 AND carries
    a ``clamped:`` marker. Consumers (milestone G10) must keep reading the raw setting for 0 = stop trading and
    treat ANY ``fallback_reason`` as "do not trust for a safety switch".
    tradable_capital_pct 的 bounds.min 為 1，人工寫入的 0（停止所有交易）會被夾成 1 並帶標記；
    G10 消費端須另讀原始設定判斷 0，且任何 fallback_reason 都代表「不可用於安全開關」。
  * NOT wired into any consumer yet (milestone G10). Calling this changes no live behaviour.
    注意：特殊值（如 0）被夾回界內，故 G10 的消費端若需要「0＝停止交易」之類的人工開關，須另行讀取，不可經此函式。

讀取失敗一律回登錄檔 rollback 值、WARNING 並附 fallback_reason，絕不回傳比 seed 更冒險的值。
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import sessionmaker

from src.config.parameter_registry import Parameter, load_registry, resolve_mission_path
from src.config.mission import load_mission
from src.config.settings_schema import schema_default
from src.data.database import get_db_engine
from src.data.models import ParameterValue

logger = logging.getLogger(__name__)

SOURCES = ("seed", "engine", "human", "rollback")


@dataclass(frozen=True)
class ParamResult:
    """Value plus provenance. ``fallback_reason`` is set whenever the value is a substitute.
    數值加來源；只要是代換值就帶 fallback_reason。"""
    key: str
    value: Any
    source: str
    fallback_reason: Optional[str] = None
    # What the store actually held when ``value`` is a substitute for it (None = no row, or value is as stored).
    # 值為代換時，儲存庫中實際存放的值。
    stored_value: Any = None

    def __float__(self) -> float:
        return float(self.value)


def _engine(engine: Any = None) -> Any:
    if engine is not None:
        return engine
    return get_db_engine()


def _param(key: str) -> Parameter:
    for p in load_registry().parameters:
        if p.key == key:
            return p
    raise KeyError(f"'{key}' is not a registered parameter")


def _seed(p: Parameter) -> Any:
    """The value a clean install carries. / 乾淨安裝的值。"""
    if p.store == "mission":
        return resolve_mission_path(load_mission(), p.mission_path)
    return schema_default(p.key)


def _rollback(p: Parameter) -> Any:
    return p.rollback_value if p.store == "settings" else _seed(p)


def _as_aware(ts: Optional[datetime]) -> Optional[datetime]:
    if ts is not None and ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


def _riskier(p: Parameter, value: float, seed: float) -> bool:
    return p.risk_direction * (value - seed) > 0


def _clamp_marked(p: Parameter, value: Any, seed: Any) -> tuple[Any, Optional[str]]:
    """Bounds, seed ceiling for non-adaptive policies, special values. Raises on non-numeric input.
    Returns (value, reason); reason is None iff the value is exactly as stored.
    回傳 (值, 原因)；原因為 None 代表與儲存值完全相同。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"stored value {value!r} is not a finite number")
    v = float(value)
    s = float(seed)
    reason: Optional[str] = None
    if p.policy == "frozen":
        v = s
        if v != float(value):
            reason = f"frozen: stored={value} seed={seed}"
    if p.bounds is not None:
        b = min(max(v, p.bounds.min), p.bounds.max)
        if b != v and reason is None:
            reason = f"clamped: stored={value} bounds=[{p.bounds.min},{p.bounds.max}]"
        v = b
    if p.policy in ("tighten_only", "frozen") and _riskier(p, v, s):
        v = s
        if reason is None:
            reason = f"riskier_than_seed: stored={value} seed={seed}"
    if v in p.special_values:  # unreachable by construction when bounds exclude it; belt and braces
        v = s
        if reason is None:
            reason = f"special_value: stored={value} seed={seed}"
    if reason is not None and v == float(value):
        reason = None  # a later step restored the stored value: nothing was substituted
    if isinstance(seed, int) and not isinstance(seed, bool) and float(v).is_integer():
        return int(v), reason
    return v, reason


def _clamp(p: Parameter, value: Any, seed: Any) -> Any:
    return _clamp_marked(p, value, seed)[0]


def _latest_row(session: Any, key: str):
    return (
        session.query(ParameterValue)
        .filter(ParameterValue.key == key)
        .order_by(ParameterValue.version.desc())
        .first()
    )


def get_param(key: str, engine: Any = None) -> ParamResult:
    """Effective value of a registered parameter; see module docstring for the failure rule.
    已登記參數的有效值；失敗規則見模組說明。"""
    try:
        p = _param(key)
    except KeyError as e:
        logger.warning("get_param: %s", e)
        return ParamResult(key, None, "rollback", f"unregistered_key: {e}")
    try:
        seed = _seed(p)
        with sessionmaker(bind=_engine(engine))() as s:
            row = _latest_row(s, key)
            if row is None:
                v, why = _clamp_marked(p, seed, seed)
                return ParamResult(key, v, "seed", why, seed if why else None)
            v, why = _clamp_marked(p, row.value_json, seed)
            return ParamResult(key, v, row.source, why, row.value_json if why else None)
    except Exception as e:
        logger.warning("get_param(%s) failed (%s); returning rollback value", key, e)
        try:
            rb = _rollback(p)
        except Exception as e2:  # even the seed is unreadable: say so, return nothing usable
            logger.warning("get_param(%s): rollback value unreadable too (%s)", key, e2)
            return ParamResult(key, None, "rollback", f"read_failed: {e}; rollback_failed: {e2}")
        return ParamResult(key, rb, "rollback", f"read_failed: {e}")


def record_value(key: str, value: Any, source: str, engine: Any = None,
                 now: Optional[datetime] = None, change_id: Optional[int] = None) -> int:
    """Append a new version of ``key``; returns the version. Raises on failure (callers must not swallow).
    追加新版本並回傳版本號；失敗時拋出例外，呼叫端不得吞掉。"""
    if source not in SOURCES:
        raise ValueError(f"unknown source {source!r}")
    _param(key)
    with sessionmaker(bind=_engine(engine))() as s:
        try:
            nxt = (s.query(func.max(ParameterValue.version)).filter(ParameterValue.key == key).scalar() or 0) + 1
            s.add(ParameterValue(key=key, version=nxt, value_json=value, source=source, change_id=change_id,
                                 effective_from=now or datetime.now(timezone.utc)))
            s.commit()
            return nxt
        except Exception:
            s.rollback()
            raise


def record_human_write(key: str, value: Any, engine: Any = None, now: Optional[datetime] = None) -> bool:
    """Record a UI/operator write of a registered key as source=human; True if a row was added.
    Only a CHANGE counts: the settings form posts every field, and an untouched key must not restart its
    evidence clock. Unregistered keys are not this module's business (False). Raises on store failure.
    只有「改變」才算：設定表單會送出全部欄位，未動的鍵不可重置證據時鐘。"""
    try:
        p = _param(key)
    except KeyError:
        return False
    current = _seed(p)
    with sessionmaker(bind=_engine(engine))() as s:
        row = _latest_row(s, key)
        if row is not None:
            current = row.value_json
    try:
        if float(value) == float(current):
            return False
    except (TypeError, ValueError):
        pass  # non-numeric: fall through and record, the reader will refuse it later
    record_value(key, value, "human", engine=engine, now=now)
    return True


def evidence_clock_start(key: str, engine: Any = None) -> Optional[datetime]:
    """When the current value took effect (None = never changed since install). Evidence for a change must be
    gathered after this instant. / 目前數值生效的時刻；證據必須是此刻之後蒐集的。"""
    _param(key)
    with sessionmaker(bind=_engine(engine))() as s:
        row = _latest_row(s, key)
        return _as_aware(row.effective_from) if row is not None else None


def seed_value(key: str) -> Any:
    """Seed (clean-install) value of a registry key, for display only. / 登錄鍵的 seed 值，僅供顯示。"""
    return _seed(_param(key))
