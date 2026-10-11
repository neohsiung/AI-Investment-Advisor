"""
Unit tests for RiskParityCVaRService (Phase 33)
================================================
測試多資產動態風險平價 (Equal Risk Contribution) 與極端尾部 CVaR 資本配置引擎
"""
import math
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest
import yaml

from src.services.conversation_router import ConversationRouter
from src.services.risk_parity_cvar_service import (
    AssetRiskMetrics,
    RiskParityAllocationResult,
    RiskParityCVaRService,
)


@pytest.fixture
def synthetic_returns():
    """產生 3 檔具備不同波動率與左尾衝擊之標的回報序列"""
    np.random.seed(42)
    days = 120
    # Asset A: 低波動 (15% 年化)
    ra = np.random.normal(0.0005, 0.15 / math.sqrt(252), days)
    # Asset B: 中波動 (25% 年化)
    rb = np.random.normal(0.0008, 0.25 / math.sqrt(252), days)
    # Asset C: 高波動 (45% 年化) + 肥尾崩跌衝擊
    rc = np.random.normal(0.0012, 0.45 / math.sqrt(252), days)
    rc[15] = -0.09
    rc[45] = -0.11

    dates = pd.date_range("2026-01-01", periods=days, freq="B")
    return pd.DataFrame({"LOW_VOL": ra, "MED_VOL": rb, "HIGH_VOL": rc}, index=dates)


class TestRiskParityCVaRServiceMath:
    """數學公式與核心演算法測試"""

    def test_covariance_matrix_estimation_and_regularization(self, synthetic_returns):
        """驗證協方差矩陣估算、對角正則化與嚴格正定性"""
        cov = RiskParityCVaRService.estimate_covariance_matrix(synthetic_returns, annualize=True)
        assert cov.shape == (3, 3)

        # 檢驗對稱性
        np.testing.assert_allclose(cov, cov.T, atol=1e-8)

        # 檢驗特徵值全正 (嚴格正定)
        eigenvalues = np.linalg.eigvalsh(cov)
        assert np.all(eigenvalues > 0.0), f"Covariance matrix not positive definite: {eigenvalues}"

        # 檢驗年化規模合理 (低波約 0.0225, 高波約 0.2025)
        assert cov[0, 0] < cov[1, 1] < cov[2, 2]

    def test_mrc_trc_euler_decomposition_identity(self, synthetic_returns):
        """驗證歐拉定理風險分解恆等式：∑ TRC_i = σ_p，∑ % TRC_i = 1.0"""
        cov = RiskParityCVaRService.estimate_covariance_matrix(synthetic_returns, annualize=True)
        weights = np.array([0.5, 0.3, 0.2])

        mrc, trc_pct, port_vol = RiskParityCVaRService.compute_risk_contributions(weights, cov)

        assert port_vol > 0.0
        assert len(mrc) == 3
        assert len(trc_pct) == 3

        # 檢驗相對風險貢獻總和為 1.0
        np.testing.assert_almost_equal(np.sum(trc_pct), 1.0, decimal=6)

        # 檢驗歐拉分解 TRC 總和等於投組波動率
        trc = weights * mrc
        np.testing.assert_almost_equal(np.sum(trc), port_vol, decimal=6)

    def test_cyclical_coordinate_descent_erc_convergence(self, synthetic_returns):
        """驗證循環坐標下降法 (CCD) 求解等風險貢獻權重精準收斂至 1/N"""
        cov = RiskParityCVaRService.estimate_covariance_matrix(synthetic_returns, annualize=True)
        w_erc = RiskParityCVaRService.solve_risk_parity_weights(cov)

        assert len(w_erc) == 3
        np.testing.assert_almost_equal(np.sum(w_erc), 1.0, decimal=6)
        assert np.all(w_erc > 0.0)

        # 度量求解後之 TRC%
        _, trc_pct, _ = RiskParityCVaRService.compute_risk_contributions(w_erc, cov)

        # 3 標的等風險貢獻下，各標的 TRC% 應精確為 1/3 (0.333333)
        target_b = np.array([1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0])
        np.testing.assert_allclose(trc_pct, target_b, atol=1e-4)

    def test_inverse_volatility_monotonicity_in_erc(self, synthetic_returns):
        """驗證在等風險貢獻下，高波動資產配置權重嚴格小於低波動資產"""
        cov = RiskParityCVaRService.estimate_covariance_matrix(synthetic_returns, annualize=True)
        w_erc = RiskParityCVaRService.solve_risk_parity_weights(cov)

        # LOW_VOL 權重 > MED_VOL 權重 > HIGH_VOL 權重
        assert w_erc[0] > w_erc[1] > w_erc[2]

    def test_historical_var_and_cvar(self, synthetic_returns):
        """驗證歷史 VaR 與 CVaR 單調性 (CVaR >= VaR)"""
        for col in synthetic_returns.columns:
            r = synthetic_returns[col].to_numpy()
            var95, cvar95 = RiskParityCVaRService.compute_asset_cvar(r, alpha=0.95)
            assert var95 >= 0.0
            assert cvar95 >= var95, f"{col} CVaR ({cvar95}) should be >= VaR ({var95})"

        # HIGH_VOL 具有極端崩跌，其 CVaR 應顯著高於 LOW_VOL
        _, cvar_low = RiskParityCVaRService.compute_asset_cvar(synthetic_returns["LOW_VOL"].to_numpy())
        _, cvar_high = RiskParityCVaRService.compute_asset_cvar(synthetic_returns["HIGH_VOL"].to_numpy())
        assert cvar_high > cvar_low * 2.0

    def test_tail_adjusted_risk_budgets_shrinkage(self):
        """驗證極端尾部 CVaR 風險預算收縮機制"""
        # 標的 A 平穩 (CVaR 2%)，標的 B 肥尾崩跌 (CVaR 8%)
        cvars = np.array([0.02, 0.08])
        base_b = np.array([0.5, 0.5])

        adj_b = RiskParityCVaRService.compute_tail_adjusted_risk_budgets(
            cvars, base_budgets=base_b, cvar_penalty_weight=0.5
        )

        assert len(adj_b) == 2
        np.testing.assert_almost_equal(np.sum(adj_b), 1.0, decimal=6)
        # 肥尾標的 B 的風險預算應顯著被削弱 (< 0.5)
        assert adj_b[1] < 0.5
        assert adj_b[0] > 0.5
        assert adj_b[0] > adj_b[1]

    def test_weight_constraints_clamping_and_simplex_projection(self):
        """驗證權重上限截斷與單體幾何投影"""
        raw_w = np.array([0.60, 0.25, 0.15])
        max_cap = 0.35

        clamped = RiskParityCVaRService.apply_weight_constraints(raw_w, max_weight=max_cap)

        assert len(clamped) == 3
        np.testing.assert_almost_equal(np.sum(clamped), 1.0, decimal=6)
        # 所有維度不得超越 35%
        assert np.all(clamped <= max_cap + 1e-6)
        assert np.all(clamped >= 0.0)

    def test_risk_concentration_hhi_and_enc(self):
        """驗證 HHI 與有效風險資產數 (ENC) 的極限與尺度"""
        # 1. 完全平價 (N=4): HHI 應為 1/4 = 0.25, ENC 應為 4.0
        trc_balanced = np.array([0.25, 0.25, 0.25, 0.25])
        hhi, enc = RiskParityCVaRService.compute_risk_concentration(trc_balanced)
        np.testing.assert_almost_equal(hhi, 0.25, decimal=6)
        np.testing.assert_almost_equal(enc, 4.0, decimal=6)

        # 2. 極端集中 (單一資產獨占 100% 風險): HHI 應為 1.0, ENC 應為 1.0
        trc_concentrated = np.array([1.0, 0.0, 0.0, 0.0])
        hhi_c, enc_c = RiskParityCVaRService.compute_risk_concentration(trc_concentrated)
        np.testing.assert_almost_equal(hhi_c, 1.0, decimal=6)
        np.testing.assert_almost_equal(enc_c, 1.0, decimal=6)

    def test_edge_cases_single_and_two_assets(self):
        """邊界條件測試：單一標的 (N=1) 與兩標的 (N=2)"""
        # N=1
        cov1 = np.array([[0.04]])
        w1 = RiskParityCVaRService.solve_risk_parity_weights(cov1)
        assert len(w1) == 1
        assert w1[0] == 1.0

        # N=2 對角協方差
        cov2 = np.diag([0.01, 0.04])  # σ1=0.1, σ2=0.2
        w2 = RiskParityCVaRService.solve_risk_parity_weights(cov2)
        # 對角矩陣下 w ∝ 1/σ: w1 : w2 = 10 : 5 = 2 : 1 -> w1=2/3, w2=1/3
        np.testing.assert_allclose(w2, np.array([2.0 / 3.0, 1.0 / 3.0]), atol=1e-4)


class TestRiskParityCVaRServiceIntegration:
    """服務整合與端對端優化測試"""

    def test_optimize_allocations_end_to_end(self, synthetic_returns):
        """測試完整 optimize_allocations 回傳結果與各欄位正確性"""
        svc = RiskParityCVaRService(user_id="test_user")
        symbols = ["LOW_VOL", "MED_VOL", "HIGH_VOL"]
        cur_w = {"LOW_VOL": 0.3333, "MED_VOL": 0.3333, "HIGH_VOL": 0.3334}

        res = svc.optimize_allocations(symbols, synthetic_returns, current_weights=cur_w)

        assert isinstance(res, RiskParityAllocationResult)
        assert res.symbols == symbols
        assert len(res.asset_metrics) == 3

        # 檢驗集中度下降
        assert res.parity_hhi_risk < res.current_hhi_risk
        assert res.effective_risk_assets_parity > res.effective_risk_assets_current

        # 檢驗 HIGH_VOL 的 tail_risk_flag 正確觸發
        assert res.asset_metrics["HIGH_VOL"].tail_risk_flag is True

        # 檢驗目標配置總和為 1.0
        tot_target = sum(m.final_target_weight for m in res.asset_metrics.values())
        np.testing.assert_almost_equal(tot_target, 1.0, decimal=4)

        # 檢驗 to_dict 序列化完整
        d = res.to_dict()
        assert "symbols" in d
        assert "asset_metrics" in d
        assert "risk_concentration_reduction_pct" in d

    def test_caching_and_fast_lookup(self, synthetic_returns):
        """測試評估成果之快取寫入與讀取"""
        svc = RiskParityCVaRService(user_id="cache_test_user")
        symbols = ["LOW_VOL", "MED_VOL", "HIGH_VOL"]
        res = svc.optimize_allocations(symbols, synthetic_returns)

        # 應已寫入內存快取
        cached = svc.get_latest_cached_assessment()
        assert cached is not None
        assert cached["symbols"] == symbols
        assert "portfolio_vol_cvar_adjusted" in cached

    @pytest.mark.asyncio
    async def test_batch_cash_deployment_risk_parity_integration(self):
        """測試 BatchCashDeploymentService 整合風險平價動態微調"""
        from src.services.batch_cash_deployment_service import BatchCashDeploymentService

        mock_broker = MagicMock()
        mock_account = MagicMock(total_equity=1700.0, available_cash=1400.0)
        mock_broker.get_account = AsyncMock(return_value=mock_account)
        mock_broker.get_positions = AsyncMock(return_value=[])

        # 建立啟用 risk parity 之 mock settings
        mock_settings = MagicMock()
        mock_settings.get_setting.side_effect = lambda k, d=None: True if k == "enable_dynamic_risk_parity" else d

        deploy_svc = BatchCashDeploymentService(
            user_id="test_deploy_user",
            settings_service=mock_settings,
            broker=mock_broker,
        )

        with patch("src.repositories.ticker_universe_repository.TickerUniverseRepository.get_target_allocations") as mock_targets:
            mock_targets.return_value = [
                {"ticker": "NVDA", "target_weight": 0.10, "confidence_score": 0.686},
                {"ticker": "TSM",  "target_weight": 0.10, "confidence_score": 0.669},
                {"ticker": "AAPL", "target_weight": 0.10, "confidence_score": 0.686},
            ]

            plan = await deploy_svc.get_deployment_plan(batch_number=1)

            assert "risk_parity_applied" in plan
            assert plan["risk_parity_applied"] is True
            assert plan["can_execute"] is True
            assert len(plan["items"]) == 3
            for it in plan["items"]:
                assert "risk_parity_target_pct" in it
                assert "cvar_tail_risk_flag" in it
                assert it["amount_usd"] >= 10.0

    @pytest.mark.asyncio
    async def test_conversation_router_riskparity_command(self):
        """測試 /riskparity 及其別名零延遲回應"""
        router = ConversationRouter()
        adapter = MagicMock()

        for cmd in ("/riskparity", "/parity", "/cvar", "/mrc", "風險平價", "平價配置"):
            reply = await router.route(adapter, "channel_uid", cmd, "test_user")
            assert reply is not None
            assert "多資產動態風險平價與極端尾部 CVaR 配置報告" in reply
            assert "循環坐標下降法" in reply
            assert "風險集中度 (HHI)" in reply
            assert "有效風險資產數" in reply

    def test_settings_schema_keys_presence(self):
        """驗證 settings_schema.yaml 中 5 項設定鍵宣告完整"""
        with open("config/settings_schema.yaml", "r", encoding="utf-8") as f:
            schema = yaml.safe_load(f)

        keys = {s["key"]: s for s in schema.get("settings", [])}
        expected_keys = [
            "enable_dynamic_risk_parity",
            "risk_parity_lookback_days",
            "risk_parity_cvar_confidence",
            "risk_parity_cvar_penalty_weight",
            "risk_parity_max_weight_cap",
        ]
        for ek in expected_keys:
            assert ek in keys, f"Missing {ek} in settings_schema.yaml"
            assert keys[ek]["type"] in ("bool", "int", "float")
