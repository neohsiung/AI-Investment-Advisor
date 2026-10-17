"""
Core (benchmark) holdings: positions the system holds as its default allocation (config/mission.yaml
`objective.benchmark`), not as active bets. Discretionary exit/rebalance logic must not touch them, otherwise
parking idle cash in the benchmark would be undone by stop-loss / concentration / pruning code and create a
buy-sell loop that burns friction.
核心（基準）持倉：系統以基準（mission.yaml objective.benchmark）作為預設配置的部位，而非主動押注。
自由裁量的出場/再平衡邏輯不得動它們，否則停損、集中度、剔除等程式會把『停泊閒置資金』拆掉，形成買賣迴圈。
"""
from __future__ import annotations

from typing import FrozenSet

from src.config.mission import load_mission


def core_tickers() -> FrozenSet[str]:
    return frozenset({load_mission().objective.benchmark.upper()})


def normalize_symbol(symbol: str) -> str:
    sym = (symbol or "").strip().upper()
    for suffix in (".US", ".RTH", ".EXT", ".L", ".UK"):
        if sym.endswith(suffix):
            sym = sym[: -len(suffix)]
    return sym


def is_core(symbol: str) -> bool:
    return normalize_symbol(symbol) in core_tickers()
