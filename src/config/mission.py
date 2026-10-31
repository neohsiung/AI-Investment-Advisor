"""
Typed loader for config/mission.yaml (the mission & invariants single source of truth).
config/mission.yaml 的型別化載入器（使命與不變量的唯一真相）。

Anything that needs a mission number should call `load_mission()` instead of copying the value.
需要使命數值的程式請呼叫 `load_mission()`，不要複製數字。
"""
from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import List

import yaml
from pydantic import BaseModel, Field

MISSION_PATH = Path(__file__).resolve().parents[2] / "config" / "mission.yaml"


class Objective(BaseModel):
    benchmark: str
    metric: str
    aspiration_annual_pct: float = Field(ge=0)
    default_allocation: str


class Budgets(BaseModel):
    max_total_cost_pct_of_nav: float = Field(gt=0, le=10)
    max_llm_usd_per_year: float = Field(gt=0)
    max_hypothesis_trials_per_quarter: int = Field(gt=0)


class Invariants(BaseModel):
    max_nonsafety_sells_per_day: int = Field(ge=0, le=20)
    max_nonsafety_sell_pct_of_nav: float = Field(gt=0, le=100)
    max_annual_turnover_x_nav: float = Field(gt=0)
    min_benchmark_weight_pct: float = Field(ge=0, le=100)
    max_tracking_error_pct: float = Field(ge=0, le=100)
    sells_require_replacement_plan: bool
    single_order_executor: bool
    trading_disabled_when_capital_cap_is_zero: bool


class Promotion(BaseModel):
    min_deflated_sharpe: float = Field(ge=0.5, le=1)
    min_t_stat: float = Field(ge=2)
    min_forward_shadow_days: int = Field(ge=30)
    max_initial_live_weight_pct: float = Field(gt=0, le=100)


class KillCriterion(BaseModel):
    id: str
    name: str
    threshold: float
    unit: str


class AdrEntry(BaseModel):
    id: str
    date: date
    decision: str
    reason: str


class Mission(BaseModel):
    version: int
    adr: List[AdrEntry]
    objective: Objective
    budgets: Budgets
    invariants: Invariants
    promotion: Promotion
    kill_criteria: List[KillCriterion]
    # ADR-005: the only strategies a frozen charter still lets through (BUY and SELL). Required: a yaml without it must
    # fail loud, not silently freeze nothing or everything. / ADR-005：凍結期間唯一放行的策略；必填，缺了就大聲失敗。
    frozen_exit_whitelist: List[str]


@lru_cache(maxsize=1)
def load_mission(path: str | None = None) -> Mission:
    """Parse and validate the mission file; raises on any problem (fail loud, never default).
    解析並驗證使命檔；任何問題都會拋出例外（大聲失敗，絕不套用預設值）。"""
    p = Path(path) if path else MISSION_PATH
    with open(p, encoding="utf-8") as f:
        return Mission.model_validate(yaml.safe_load(f))
