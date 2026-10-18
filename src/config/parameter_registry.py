"""
Typed loader for config/parameter_registry.yaml (the pre-registered surface of self-adjustable thresholds).
config/parameter_registry.yaml 的型別化載入器（事先登記、可自我調整門檻的範圍）。

This module only parses and validates the registry. It changes no behaviour: nothing in the trading path reads
it yet (a later milestone adds the single read helper). Missing or malformed files raise; there is no default.
本模組只解析並驗證登錄檔，不改變任何行為；解析失敗一律拋出例外，絕不套用預設值。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, List, Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.config.mission import Mission

REGISTRY_PATH = Path(__file__).resolve().parents[2] / "config" / "parameter_registry.yaml"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Bounds(_Strict):
    min: float
    max: float

    @model_validator(mode="after")
    def _ordered(self) -> "Bounds":
        if self.min > self.max:
            raise ValueError("bounds.min > bounds.max")
        return self


class Evidence(_Strict):
    metric: str
    horizons_days: List[int]
    min_n: int = Field(ge=1)
    counterfactual_source: str


class Parameter(_Strict):
    key: str
    store: Literal["settings", "mission"]
    cls: Literal["A", "B", "C", "D"] = Field(alias="class")
    risk_direction: Literal[-1, 1]
    policy: Literal["adaptive", "tighten_only", "frozen"]
    owner: str = ""
    mission_path: Optional[str] = None
    rollback_value: Optional[Any] = None
    bounds: Optional[Bounds] = None
    grid: List[float] = Field(default_factory=list)
    special_values: List[float] = Field(default_factory=list)
    max_step_grids: int = Field(default=1, ge=1, le=1)
    cooldown_days: int = Field(default=0, ge=0)
    evidence: Optional[Evidence] = None
    untestable_reason: Optional[str] = None

    @model_validator(mode="after")
    def _shape(self) -> "Parameter":
        if self.store == "settings" and (self.rollback_value is None or self.bounds is None):
            raise ValueError(f"{self.key}: settings parameter needs rollback_value and bounds")
        if self.store == "mission" and not self.mission_path:
            raise ValueError(f"{self.key}: mission parameter needs mission_path")
        return self


class ParameterRegistry(_Strict):
    version: int
    parameters: List[Parameter]


@lru_cache(maxsize=1)
def load_registry(path: str | None = None) -> ParameterRegistry:
    """Parse and validate the registry; raises on any problem (fail loud, never default).
    解析並驗證登錄檔；任何問題都會拋出例外（大聲失敗，絕不套用預設值）。"""
    p = Path(path) if path else REGISTRY_PATH
    with open(p, encoding="utf-8") as f:
        return ParameterRegistry.model_validate(yaml.safe_load(f))


def resolve_mission_path(mission: Mission, dotted: str) -> Any:
    """Return the mission value at `section.field` (KeyError if the path does not exist).
    取得 mission 中 `區段.欄位` 的值；路徑不存在時拋 KeyError。"""
    node: Any = mission
    for part in dotted.split("."):
        if not hasattr(node, part):
            raise KeyError(f"mission has no '{dotted}' (failed at '{part}')")
        node = getattr(node, part)
    return node
