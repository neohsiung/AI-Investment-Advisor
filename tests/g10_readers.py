"""G10 support: drive each of the 7 read sites of the 6 registered keys and return the value the site actually used.
G10 輔助：驅動 6 個登錄鍵的 7 個讀取點，回傳該讀取點實際採用的值（單元測試與 E2E 共用）。

``wire(mp, get)`` points every reader module's ``get_param`` at ``get``; ``SITES[name].drive(mp)`` runs the real
reader code with its other collaborators stubbed and returns the observed value.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from unittest.mock import AsyncMock, MagicMock, patch

MODULES = (
    "src.services.order_cap_policy",
    "src.services.batch_cash_deployment_service",
    "src.services.sentinel_service",
    "src.services.proposal_shadow_service",
    "src.services.ticker_universe_service",
    "src.services.workflow_service",
)


def wire(mp: Any, get: Callable[..., Any]) -> None:
    """Replace ``get_param`` and silence-proof the module logger (MagicMock) in every reader module.
    把每個讀取模組的 get_param 換成 get，logger 換成 MagicMock 以便斷言 WARNING。"""
    import importlib
    for name in MODULES:
        mod = importlib.import_module(name)
        mp.setattr(mod, "get_param", get)
        mp.setattr(mod, "logger", MagicMock())


def warned(module_name: str, needle: str = "fallback") -> bool:
    import importlib
    lg = importlib.import_module(module_name).logger
    return any(needle in str(c.args[0]) for c in lg.warning.call_args_list if c.args)


# ── drivers ──────────────────────────────────────────────────────────────────────────────────────────────────

def _order_cap(mp: Any) -> float:
    from src.services.order_cap_policy import single_order_cap_usd
    return single_order_cap_usd(MagicMock(), None)


def _batch_min_conf(mp: Any) -> float:
    from src.services import batch_cash_deployment_service as m
    svc = m.BatchCashDeploymentService.__new__(m.BatchCashDeploymentService)
    svc.user_id = "u"
    svc.settings_service = MagicMock()
    repo = MagicMock()
    repo.get_target_allocations.return_value = []
    repo.get_all.return_value = []
    seen: dict = {}

    def collector(side, min_conf):
        seen["v"] = min_conf
        return None, []

    mp.setattr(m, "band_collector", collector)
    mp.setattr(m, "record_at_boundary", AsyncMock())
    mp.setattr(svc, "_setting_float", lambda k, d: d, raising=False)
    mp.setattr(svc, "rank_candidates", lambda **kw: [], raising=False)
    with patch("src.repositories.ticker_universe_repository.TickerUniverseRepository", return_value=repo):
        asyncio.run(svc._select_dynamic_candidates(1000.0, {}, target_records=[]))
    return seen["v"]


def _sentinel(mp: Any) -> tuple[float, float]:
    """(rotation_min_score_delta, min_hold) as handed to record_young_blocked. / 傳給 record_young_blocked 的兩值。"""
    from src.services import sentinel_service as m
    repo = MagicMock()
    repo.engine = MagicMock()
    repo.get_all_thresholds.return_value = {}
    settings = MagicMock()
    smap = {"capital_rotation_enabled": True, "rotation_min_holding_days": _sentinel.raw_hold}
    settings.get_setting.side_effect = lambda k, default=None, user_id=None: smap.get(k, default)
    buf = MagicMock()
    buf.try_acquire = AsyncMock(return_value=True)
    with patch("src.infrastructure.redis_sentinel_buffer.RedisSentinelBuffer", return_value=buf), \
         patch("src.services.search_service.InternetSearchService"), \
         patch("src.services.council_service.CouncilService"), \
         patch("src.repositories.snapshot_repository.AlchemySnapshotRepository"), \
         patch("src.services.token_logger_service.TokenLoggerService"):
        svc = m.SentinelService(user_id="u", repo=repo, market_service=MagicMock(), transaction_service=MagicMock(),
                                settings_service=settings, keyword_service=MagicMock())
    rec = AsyncMock()
    mp.setattr(m, "record_young_blocked", rec)
    mp.setattr(svc, "_acquire_cooldown", AsyncMock(return_value=True))
    mp.setattr(svc, "_research_score", lambda t: 9.0)
    mp.setattr(svc, "_holding_age_days", lambda t, i: 1.0)
    holdings = {"META": {"shares": 10.0, "current_price": 500.0, "avg_price": 450.0, "weight": 0.5}}
    with patch("src.services.trading_protections_service.TradingProtectionsService.check", return_value=None):
        try:
            asyncio.run(svc._check_capital_rotation_opportunities(
                current_allocation=holdings, candidates_override=[{"ticker": "NVDA", "composite_score": 9.5}]))
        except Exception:      # past record_young_blocked the exit compositor is not under test / 之後不在測試範圍
            pass
    args = rec.call_args.args
    return args[6], args[7]


_sentinel.raw_hold = 5


def _rotation_delta(mp: Any) -> float:
    return _sentinel(mp)[0]


def _rotation_hold(mp: Any) -> float:
    return _sentinel(mp)[1]


def _shadow(mp: Any) -> dict:
    from src.services import proposal_shadow_service as m
    deps = {"account": AsyncMock(return_value=(1000.0, 500.0)), "holdings": {}, "research_lookup": lambda *a: None,
            "gateway": MagicMock(), "mission": {}}
    settings = MagicMock()
    settings.get_setting.return_value = False
    with patch("src.services.capital_policy.tradable_capital", return_value=1000.0):
        return asyncio.run(m._build_shared("u", False, settings, deps, MagicMock()))


def _shadow_max_age(mp: Any) -> float:
    return _shadow(mp)["max_age"]


def _universe(mp: Any) -> float:
    from src.services import ticker_universe_service as m
    svc = m.TickerUniverseService(user_id="u")
    svc.repo = MagicMock()
    svc.repo.get_all.return_value = [{"ticker": "AAPL", "sector": "Tech"}]
    old = datetime.now(timezone.utc) - timedelta(days=100)       # always stale: the warning carries max_age_days
    svc.repo.get_research.return_value = [{"confidence_score": 0.8, "expected_return": 0.15, "created_at": old}]
    svc.repo.upsert_target.return_value = True
    svc.optimize_allocations()
    stale = [c for c in m.logger.warning.call_args_list if c.args and "treating as unresearched" in str(c.args[0])]
    return stale[0].args[3]


def _event_cap(mp: Any) -> int:
    """Daily cap seen by the budget gate: calls until it trips. / 日預算閘門的上限：呼叫幾次後才觸發。"""
    from src.services.workflow_service import EventAnalysisWorkflow

    class R:
        def __init__(self): self.c = {}
        def incr(self, k): self.c[k] = self.c.get(k, 0) + 1; return self.c[k]
        def expire(self, k, t): pass

    wf = EventAnalysisWorkflow.__new__(EventAnalysisWorkflow)
    wf.user_id = "u"
    wf.logger = MagicMock()
    with patch("src.services.settings_service.SettingsService") as ss, \
         patch("src.infrastructure.cache.redis_client.get_redis_sync", return_value=R()):
        ss.return_value.get_setting.return_value = _event_cap.raw
        for n in range(1, 60):
            if wf._event_budget_exceeded(False):
                return n - 1
    return 0     # never tripped = unlimited / 從未觸發＝不設限


_event_cap.raw = 8


@dataclass(frozen=True)
class Site:
    name: str
    key: str
    module: str
    drive: Callable[[Any], Any]
    engine_value: Any       # a grid value different from today's default / 與現值不同的格點值


SITES = (
    Site("order_cap_policy", "batch_deploy_max_order_usd", "src.services.order_cap_policy", _order_cap, 150.0),
    Site("batch_deploy", "batch_deploy_min_confidence", "src.services.batch_cash_deployment_service",
         _batch_min_conf, 6.5),
    Site("sentinel_delta", "rotation_min_score_delta", "src.services.sentinel_service", _rotation_delta, 3.0),
    Site("sentinel_hold", "rotation_min_holding_days", "src.services.sentinel_service", _rotation_hold, 7),
    Site("proposal_shadow", "universe_research_max_age_days", "src.services.proposal_shadow_service",
         _shadow_max_age, 21),
    Site("ticker_universe", "universe_research_max_age_days", "src.services.ticker_universe_service", _universe, 21),
    Site("workflow_cap", "event_analysis_daily_cap", "src.services.workflow_service", _event_cap, 12),
)
