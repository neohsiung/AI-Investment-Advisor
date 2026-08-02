"""
Repository for PortfolioBacktestEngine run persistence (P4.1).

Powers the backtest results UI (P5.1): each run is saved with its metrics,
trade log, and equity curve so past strategy iterations are re-viewable and
comparable.
"""
from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from src.data.database import BaseRepository, get_db_engine


class IBacktestRepository(ABC):
    @abstractmethod
    def save_run(self, user_id: str, ticker: str, strategy_name: str, initial_cash: float,
                 final_cash: float, metrics: Dict[str, Any], trades: List[Dict[str, Any]],
                 equity_curve: List[float], dates: List[str],
                 params: Optional[Dict[str, Any]] = None) -> str:
        ...

    @abstractmethod
    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        ...

    @abstractmethod
    def list_runs(self, user_id: str, ticker: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        ...


class AlchemyBacktestRepository(BaseRepository, IBacktestRepository):
    def __init__(self, db_path: Optional[str] = None, engine: Any = None):
        engine = engine or get_db_engine(db_path)
        BaseRepository.__init__(self, engine)

    def save_run(self, user_id: str, ticker: str, strategy_name: str, initial_cash: float,
                 final_cash: float, metrics: Dict[str, Any], trades: List[Dict[str, Any]],
                 equity_curve: List[float], dates: List[str],
                 params: Optional[Dict[str, Any]] = None) -> str:
        run_id = str(uuid.uuid4())
        is_sqlite = self.engine.dialect.name == "sqlite"
        # psycopg2 needs an explicit CAST(:x AS jsonb) for JSONB columns — a
        # raw Python dict param doesn't auto-adapt (matches the convention in
        # event_queue_repository.py). sqlite has no jsonb cast; plain TEXT.
        metrics_val = json.dumps(metrics)
        trades_val = json.dumps(trades)
        params_val = json.dumps(params) if params else None
        json_cols = "(:metrics, :trades, :params)" if is_sqlite else \
            "(CAST(:metrics AS jsonb), CAST(:trades AS jsonb), CAST(:params AS jsonb))"

        with self.engine.begin() as conn:
            conn.execute(text(f"""
                INSERT INTO backtest_runs
                    (id, user_id, ticker, strategy_name, initial_cash, final_cash, metrics, trades, params)
                VALUES
                    (:id, :user_id, :ticker, :strategy_name, :initial_cash, :final_cash, {json_cols[1:-1]})
            """), {
                "id": run_id, "user_id": user_id, "ticker": ticker, "strategy_name": strategy_name,
                "initial_cash": initial_cash, "final_cash": final_cash,
                "metrics": metrics_val, "trades": trades_val, "params": params_val,
            })
            if equity_curve:
                rows = [
                    {"id": str(uuid.uuid4()), "run_id": run_id, "seq": i,
                     "date": dates[i] if i < len(dates) else None, "equity": v}
                    for i, v in enumerate(equity_curve)
                ]
                conn.execute(text("""
                    INSERT INTO backtest_equity_points (id, run_id, seq, date, equity)
                    VALUES (:id, :run_id, :seq, :date, :equity)
                """), rows)
        return run_id

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self.engine.connect() as conn:
            row = conn.execute(text(
                "SELECT * FROM backtest_runs WHERE id = :id"
            ), {"id": run_id}).fetchone()
            if not row:
                return None
            run = dict(row._mapping)
            # sqlite stores JSON columns as TEXT (needs json.loads); postgres
            # JSONB deserializes to dict/list automatically via psycopg2.
            if self.engine.dialect.name == "sqlite":
                for col in ("metrics", "trades", "params"):
                    if isinstance(run.get(col), str):
                        run[col] = json.loads(run[col])
            points = conn.execute(text(
                "SELECT seq, date, equity FROM backtest_equity_points WHERE run_id = :id ORDER BY seq"
            ), {"id": run_id}).fetchall()
            run["equity_curve"] = [
                {"seq": p.seq, "date": p.date, "equity": float(p.equity)} for p in points
            ]
            return run

    def list_runs(self, user_id: str, ticker: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        with self.engine.connect() as conn:
            query = "SELECT id, ticker, strategy_name, initial_cash, final_cash, metrics, created_at FROM backtest_runs WHERE user_id = :user_id"
            params: Dict[str, Any] = {"user_id": user_id, "limit": limit}
            if ticker:
                query += " AND ticker = :ticker"
                params["ticker"] = ticker
            query += " ORDER BY created_at DESC LIMIT :limit"
            rows = conn.execute(text(query), params).fetchall()
            results = [dict(r._mapping) for r in rows]
            if self.engine.dialect.name == "sqlite":
                for r in results:
                    if isinstance(r.get("metrics"), str):
                        r["metrics"] = json.loads(r["metrics"])
            return results
