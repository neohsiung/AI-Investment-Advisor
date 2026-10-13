"""
Unit tests for Universe Lifecycle Momentum Pruning
==================================================
外圍標的池自適應動能剪枝與換血機制單元測試
"""
import asyncio
from datetime import datetime, timedelta, timezone
import pandas as pd
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.universe_lifecycle_service import UniverseLifecycleService


@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.get_all.return_value = []
    repo.remove.return_value = True
    repo.add_log.return_value = True
    return repo


@pytest.fixture
def mock_market():
    market = MagicMock()
    return market


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings_dict = {
        "enable_universe_momentum_pruning": True,
        "universe_candidate_max_stagnation_days": 14,
        "universe_candidate_relative_strength_cutoff": -0.025,
        "universe_max_contenders_per_sector": 3,
    }
    settings.get_setting.side_effect = lambda k, default=None: settings_dict.get(k, default)
    return settings


def test_prune_stagnant_candidates(mock_repo, mock_market, mock_settings):
    """驗證候選池駐留超過 14 天且相對於 SPY 動能衰竭 (< -2.5%) 之標的被正確剪枝，新標的與置頂標的獲豁免。"""
    async def _test():
        svc = UniverseLifecycleService(user_id="test_user", repo=mock_repo, market=mock_market)
        svc.settings = mock_settings

        now = datetime.now(timezone.utc)
        old_time = (now - timedelta(days=20)).isoformat()
        fresh_time = (now - timedelta(days=5)).isoformat()

        candidates = [
            # 1. 停滯 20 天且 RS 落後 -> 應被剪枝
            {"ticker": "STAG", "added_at": old_time, "is_pinned": False, "sector": "Tech"},
            # 2. 停滯 20 天但置頂 -> 豁免保留
            {"ticker": "PINN", "added_at": old_time, "is_pinned": True, "sector": "Tech"},
            # 3. 僅進駐 5 天 (<14 天) -> 保留
            {"ticker": "FRES", "added_at": fresh_time, "is_pinned": False, "sector": "Tech"},
            # 4. 停滯 20 天但表現優異 -> 保留
            {"ticker": "GOOD", "added_at": old_time, "is_pinned": False, "sector": "Tech"},
        ]
        mock_repo.get_all.return_value = candidates

        # 模擬歷史行情：
        # SPY: 500 -> 510 (+2.0%)
        # STAG: 100 -> 94 (-6.0%) => RS delta = -6.0% - 2.0% = -8.0% (< -2.5%) -> 淘汰
        # GOOD: 200 -> 215 (+7.5%) => RS delta = +7.5% - 2.0% = +5.5% (>= -2.5%) -> 保留
        def fake_get_history_df(sym, days=60):
            if sym == "SPY":
                return pd.DataFrame({"close": [500.0, 510.0]})
            elif sym == "STAG":
                return pd.DataFrame({"close": [100.0, 94.0]})
            elif sym == "GOOD":
                return pd.DataFrame({"close": [200.0, 215.0]})
            return None

        mock_market.get_history_df.side_effect = fake_get_history_df

        pruned = await svc.prune_stagnant_candidates()

        assert len(pruned) == 1
        assert pruned[0]["ticker"] == "STAG"
        assert pruned[0]["rs_delta"] == -0.08
        mock_repo.remove.assert_called_once()
        mock_repo.add_log.assert_called_once()

    asyncio.run(_test())


def test_prune_stale_shadow_positions(mock_repo, mock_market, mock_settings):
    """驗證在影子池觀測超過 14 天且虧損/未達標之影子部位被正確清理。"""
    async def _test():
        svc = UniverseLifecycleService(user_id="test_user", repo=mock_repo, market=mock_market)
        svc.settings = mock_settings

        now = datetime.now(timezone.utc)
        old_time = (now - timedelta(days=16)).isoformat()
        fresh_time = (now - timedelta(days=6)).isoformat()

        shadows = [
            # 1. 影子觀測 16 天且虧損 -> 淘汰
            {"ticker": "SHAD_BAD", "added_at": old_time, "is_pinned": False},
            # 2. 影子觀測 16 天但獲利 -> 保留繼續觀察/待畢業
            {"ticker": "SHAD_OK", "added_at": old_time, "is_pinned": False},
            # 3. 影子觀測僅 6 天 -> 保留
            {"ticker": "SHAD_NEW", "added_at": fresh_time, "is_pinned": False},
        ]
        mock_repo.get_all.return_value = shadows

        def fake_get_history_df(sym, days=60):
            if sym == "SHAD_BAD":
                return pd.DataFrame({"close": [50.0, 48.0]})  # -4.0%
            elif sym == "SHAD_OK":
                return pd.DataFrame({"close": [50.0, 55.0]})  # +10.0%
            return None

        mock_market.get_history_df.side_effect = fake_get_history_df

        pruned = await svc.prune_stale_shadow_positions(max_observation_days=14)

        assert len(pruned) == 1
        assert pruned[0]["ticker"] == "SHAD_BAD"
        assert pruned[0]["shadow_return"] == -0.04
        mock_repo.remove.assert_called_once()

    asyncio.run(_test())


def test_enforce_sector_contender_quotas(mock_repo, mock_market, mock_settings):
    """驗證單一板塊候選股上限 (例如 3 檔)，超出配額之評分最低者被安全修剪。"""
    async def _test():
        svc = UniverseLifecycleService(user_id="test_user", repo=mock_repo, market=mock_market)
        svc.settings = mock_settings

        # 4 檔 Tech (配額 3), 2 檔 Financials (配額 3)
        candidates = [
            {"ticker": "AAPL", "sector": "Technology", "confidence_score": 0.95, "target_weight": 0.15, "is_pinned": True},
            {"ticker": "MSFT", "sector": "Technology", "confidence_score": 0.90, "target_weight": 0.12, "is_pinned": False},
            {"ticker": "NVDA", "sector": "Technology", "confidence_score": 0.85, "target_weight": 0.10, "is_pinned": False},
            {"ticker": "ORCL", "sector": "Technology", "confidence_score": 0.60, "target_weight": 0.05, "is_pinned": False},  # 應被淘汰
            {"ticker": "JPM", "sector": "Financials", "confidence_score": 0.80, "target_weight": 0.08, "is_pinned": False},
            {"ticker": "BAC", "sector": "Financials", "confidence_score": 0.75, "target_weight": 0.07, "is_pinned": False},
        ]
        mock_repo.get_all.return_value = candidates

        pruned = await svc.enforce_sector_contender_quotas(max_per_sector=3)

        assert len(pruned) == 1
        assert pruned[0]["ticker"] == "ORCL"
        assert pruned[0]["sector"] == "Technology"
        mock_repo.remove.assert_called_once()

    asyncio.run(_test())


def test_prune_universe_momentum_combined(mock_repo, mock_market, mock_settings):
    """驗證 prune_universe_momentum 整合調用三道剪枝機制。"""
    async def _test():
        svc = UniverseLifecycleService(user_id="test_user", repo=mock_repo, market=mock_market)
        svc.settings = mock_settings

        with patch.object(svc, "prune_stagnant_candidates", return_value=[{"ticker": "STAG_1"}]), \
             patch.object(svc, "prune_stale_shadow_positions", return_value=[{"ticker": "SHAD_1"}]), \
             patch.object(svc, "enforce_sector_contender_quotas", return_value=[{"ticker": "TECH_4"}]):

            res = await svc.prune_universe_momentum()

            assert res["success"] is True
            assert res["total_pruned"] == 3
            assert len(res["stagnant_candidates"]) == 1
            assert len(res["stale_shadow_positions"]) == 1
            assert len(res["sector_quota_pruned"]) == 1

    asyncio.run(_test())


def test_conversation_router_universe_prune():
    """驗證 ConversationRouter 的 /universe prune 快捷指令。"""
    async def _test():
        from src.services.conversation_router import ConversationRouter

        router = ConversationRouter()

        mock_uni_svc = MagicMock()
        mock_uni_svc.prune_universe_momentum = AsyncMock(return_value={
            "success": True,
            "total_pruned": 2,
            "stagnant_candidates": [{"ticker": "STAG_A", "tenure_days": 18.0, "rs_delta": -0.052}],
            "stale_shadow_positions": [{"ticker": "SHAD_B", "tenure_days": 15.0, "shadow_return": -0.015}],
            "sector_quota_pruned": [],
        })

        with patch("src.services.universe_lifecycle_service.UniverseLifecycleService", return_value=mock_uni_svc), \
             patch("src.repositories.ticker_universe_repository.TickerUniverseRepository"):

            reply = await router._handle_system_command(
                adapter=None,
                channel_user_id="test_channel",
                text="/universe prune",
                resolved_user_id="test_user",
            )
            assert reply is not None
            assert "標的池自適應動能剪枝與換血完成" in reply
            assert "2 檔標的" in reply
            assert "STAG_A" in reply
            assert "SHAD_B" in reply

    asyncio.run(_test())
