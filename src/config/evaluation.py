"""
Typed loader for config/evaluation.yaml (cost model and ETF universe of the offline strategy lab).
config/evaluation.yaml 的型別化載入器（離線策略實驗室的成本模型與 ETF 宇宙）。

The lab reads cost and universe through `load_evaluation()`; nothing may re-declare them as literals.
實驗室一律經 `load_evaluation()` 取得成本與宇宙，不得在程式內寫死。
"""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import List

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

EVALUATION_PATH = Path(__file__).resolve().parents[2] / "config" / "evaluation.yaml"


class EvaluationConfig(BaseModel):
    version: int = 1
    cost_bps_per_side: float = Field(gt=0, le=100)
    cost_basis_status: str = "unverified_conservative_default"
    cost_basis_note: str = ""
    cost_multipliers: List[float]
    etf_universe: List[str]

    @field_validator("cost_basis_status")
    @classmethod
    def _status(cls, v: str) -> str:
        if v not in ("unverified_conservative_default", "measured"):
            raise ValueError("cost_basis_status must be unverified_conservative_default or measured")
        return v

    @field_validator("cost_multipliers")
    @classmethod
    def _mults(cls, v: List[float]) -> List[float]:
        # The honesty requirement lives in the loader so a config edit cannot quietly drop the stress level.
        # 誠實性要求放在載入器，改設定檔無法悄悄拿掉壓力測試。
        if len(set(v)) != len(v) or any(m <= 0 for m in v):
            raise ValueError("cost_multipliers must be unique and positive")
        if 1.0 not in v or max(v) < 2.0:
            raise ValueError("cost_multipliers must include 1.0 and at least one level >= 2.0")
        return sorted(float(m) for m in v)

    @field_validator("etf_universe")
    @classmethod
    def _universe(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("etf_universe must not be empty")
        if len({s.upper() for s in v}) != len(v):
            raise ValueError("etf_universe has duplicates")
        return v

    @model_validator(mode="after")
    def _measured_needs_note(self) -> "EvaluationConfig":
        if self.cost_basis_status == "measured" and not self.cost_basis_note.strip():
            raise ValueError("a measured cost needs cost_basis_note describing how it was derived")
        return self

    @property
    def universe_tag(self) -> str:
        """Short digest of the universe; part of a trial's identity. / 宇宙摘要，屬於試驗身分的一部分。"""
        return hashlib.sha256(",".join(sorted(s.upper() for s in self.etf_universe)).encode()).hexdigest()[:8]


@lru_cache(maxsize=1)
def load_evaluation() -> EvaluationConfig:
    with open(EVALUATION_PATH, encoding="utf-8") as f:
        return EvaluationConfig(**yaml.safe_load(f))
