"""Price-panel loading for the evaluation pipeline (I/O lives here so the maths stays pure).
評估管線的價格資料載入（I/O 集中於此，計算保持純函式）。"""
from __future__ import annotations

import logging
from typing import Any, Iterable

import pandas as pd

logger = logging.getLogger("EvalData")


def load_price_panel(market_service: Any, symbols: Iterable[str], days: int = 2600, benchmark: str = "SPY",
                     min_coverage: float = 0.9) -> pd.DataFrame:
    """Adjusted-close panel (columns = symbols). Symbols with < min_coverage of the benchmark history are dropped
    and reported; a missing benchmark raises. / 還原收盤價面板；覆蓋率不足的標的剔除並記錄；基準缺失則拋出例外。"""
    cols = {}
    for s in dict.fromkeys([benchmark, *symbols]):
        try:
            df = market_service.get_history_df(s, days=days)
        except Exception as e:
            logger.warning("price history failed for %s: %s", s, e)
            continue
        if df is None or df.empty:
            logger.warning("no price history for %s", s)
            continue
        col = "Close" if "Close" in df.columns else "close"
        ser = df[col].dropna()
        ser.index = pd.to_datetime(ser.index).tz_localize(None).normalize()
        cols[s] = ser[~ser.index.duplicated()]
    if benchmark not in cols:
        raise RuntimeError(f"benchmark {benchmark} price history unavailable")
    panel = pd.DataFrame(cols).sort_index().dropna(subset=[benchmark]).ffill(limit=3)
    keep = panel.dropna(axis=1, thresh=int(len(panel) * min_coverage))
    dropped = sorted(set(panel.columns) - set(keep.columns))
    if dropped:
        logger.warning("dropped for thin history: %s", dropped)
    return keep.dropna()
