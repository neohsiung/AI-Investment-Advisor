"""
Unit Tests for Alpha Spread Bidding & Friction Offset Service (Phase 57)
========================================================================
測試內容涵蓋：
1. 物理摩擦精算 (Half-spread, Slippage compensator, VPIN toxicity)
2. 毛 Alpha 精算與跨板塊多角化溢價 (+12 bps)
3. 利差競標 5 級階梯決策 (AGGRESSIVE_EXPAND, EXPAND, NEUTRAL_PROCEED, DEFENSIVE_CONTRACT, FRICTION_BLOCKED)
4. Dataclass 序列化與反序列化 (to_dict, from_dict)
5. 雙渠道診斷戰報生成 (format_spread_bidding_report)
6. 批次建倉服務整合 (BatchCashDeploymentService)
7. 對話路由器 0-LLM /spread 系統指令直通
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.alpha_spread_bidding_service import (
    AlphaSpreadBiddingService,
    BiddingAssessmentResult,
    BiddingCandidateMetric,
)


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    # Default settings mapping
    store = {
        "enable_alpha_spread_bidding": True,
        "alpha_bidding_hurdle_bps": 15.0,
        "cross_sector_max_bidding_quota_pct": 0.45,
        "cross_sector_min_bidding_quota_pct": 0.20,
        "alpha_bidding_diversification_premium_bps": 12.0,
    }
    settings.get_setting.side_effect = lambda k, default=None: store.get(k, default)
    return settings


@pytest.fixture
def mock_market_data():
    mkt = MagicMock()
    # Mock quote for AAPL with 2 bps half-spread
    async def _get_quote(ticker):
        if ticker == "AAPL":
            return {"bid": 199.98, "ask": 200.02, "mid": 200.00, "last": 200.00}
        elif ticker == "V":
            return {"bid": 279.95, "ask": 280.05, "mid": 280.00, "last": 280.00}
        elif ticker == "WIDE":
            return {"spread_pct": 0.004}  # 40 bps full spread -> 20 bps half spread
        return None
    mkt.get_quote = AsyncMock(side_effect=_get_quote)
    return mkt


@pytest.fixture
def bidding_service(mock_settings, mock_market_data):
    return AlphaSpreadBiddingService(
        user_id="test_user",
        settings_service=mock_settings,
        market_data_service=mock_market_data,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 1. 物理摩擦精算測試
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_calculate_friction_with_bid_ask(bidding_service):
    """測試根據 Bid-Ask 計算半價差 (AAPL: 200.02 - 199.98 = 0.04 -> half-spread = 0.02 / 200 = 1.0 bps)"""
    half_sp, tox, total = await bidding_service.calculate_candidate_friction("AAPL")
    assert half_sp == 1.0
    assert tox == 0.0
    assert total == 1.0


@pytest.mark.asyncio
async def test_calculate_friction_with_spread_pct(bidding_service):
    """測試根據 spread_pct 計算半價差 (WIDE: 40 bps full spread -> 20 bps half spread)"""
    half_sp, tox, total = await bidding_service.calculate_candidate_friction("WIDE")
    assert half_sp == 20.0
    assert total == 20.0


@pytest.mark.asyncio
async def test_calculate_friction_fallback(bidding_service):
    """測試報價缺失時回退至大型股預設 3.5 bps"""
    half_sp, tox, total = await bidding_service.calculate_candidate_friction("UNKNOWN")
    assert half_sp == 3.5
    assert total == 3.5


@pytest.mark.asyncio
async def test_calculate_friction_with_slippage_and_vpin(mock_settings, mock_market_data):
    """測試滑點補償器與 VPIN 毒性守衛之微觀結構摩擦懲罰"""
    mock_slippage_guard = MagicMock()
    mock_compensator = MagicMock()
    mock_metric = MagicMock()
    mock_metric.slippage_multiplier = 1.5  # (1.5 - 1.0) * 8.0 = 4.0 bps
    mock_metric.adverse_selection_count = 2  # 2 * 3.0 = 6.0 bps
    mock_compensator.get_metrics.return_value = mock_metric
    mock_slippage_guard.compensator = mock_compensator

    mock_vpin_guard = MagicMock()
    mock_vpin_eval = MagicMock()
    mock_vpin_eval.vpin = 0.30  # (0.30 - 0.20) * 50.0 = 5.0 bps
    mock_vpin_guard.evaluate_ticker = AsyncMock(return_value=mock_vpin_eval)

    svc = AlphaSpreadBiddingService(
        user_id="test_user",
        settings_service=mock_settings,
        market_data_service=mock_market_data,
        slippage_guard=mock_slippage_guard,
        vpin_guard=mock_vpin_guard,
    )

    half_sp, tox, total = await svc.calculate_candidate_friction("AAPL")
    assert half_sp == 1.0
    # tox = 4.0 + 6.0 + 5.0 = 15.0 bps
    assert tox == 15.0
    assert total == 16.0


# ═══════════════════════════════════════════════════════════════════════════
# 2. 毛 Alpha 精算與多角化溢價測試
# ═══════════════════════════════════════════════════════════════════════════

def test_calculate_gross_alpha_regular(bidding_service):
    """常規標的毛 Alpha 精算：基準 5.0 分為 15 bps，7.0 分為 25 bps"""
    alpha_5 = bidding_service.calculate_candidate_gross_alpha("NVDA", confidence_score=5.0)
    assert alpha_5 == 15.0

    alpha_7 = bidding_service.calculate_candidate_gross_alpha("NVDA", confidence_score=7.0)
    assert alpha_7 == 25.0

    alpha_9 = bidding_service.calculate_candidate_gross_alpha("NVDA", confidence_score=9.0)
    assert alpha_9 == 35.0


def test_calculate_gross_alpha_cross_sector(bidding_service):
    """跨板塊注入標的享有 +12.0 bps 多角化溢價"""
    alpha_regular = bidding_service.calculate_candidate_gross_alpha("V", confidence_score=7.0, is_cross_sector_injected=False)
    alpha_injected = bidding_service.calculate_candidate_gross_alpha("V", confidence_score=7.0, is_cross_sector_injected=True)
    assert alpha_regular == 25.0
    assert alpha_injected == 37.0  # 25.0 + 12.0


# ═══════════════════════════════════════════════════════════════════════════
# 3. 利差競標階梯決策測試 (evaluate_bidding_for_batch)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_bidding_ladder_aggressive_expand(bidding_service):
    """淨利差 >= 1.5x Hurdle (>= 22.5 bps) -> AGGRESSIVE_EXPAND (45%)"""
    contender = {
        "ticker": "V",
        "sector": "Financials",
        "confidence": 7.5,  # gross alpha = 15 + 2.5*5 + 12 = 39.5 bps
        "current_price": 280.0,
        "role": "金融板塊龍頭自癒",
    }
    # V friction = ~1.79 bps, net spread = ~37.7 bps >= 22.5 bps
    res = await bidding_service.evaluate_bidding_for_batch([], contender=contender, base_quota_pct=0.35)
    assert res.bidding_status == "AGGRESSIVE_EXPAND"
    assert res.cross_sector_adjusted_quota_pct == 0.45
    assert "V" in res.candidates
    assert res.candidates["V"].bidding_status == "AGGRESSIVE_EXPAND"
    assert res.candidates["V"].allocated_quota_pct == 0.45


@pytest.mark.asyncio
async def test_bidding_ladder_expand(bidding_service):
    """淨利差 15.0 ~ 22.4 bps -> EXPAND (40%)"""
    # 透過 mock calculate_candidate_friction 控制摩擦
    with patch.object(bidding_service, "calculate_candidate_friction", new_callable=AsyncMock) as mock_fric:
        mock_fric.return_value = (10.0, 5.0, 15.0)  # 摩擦 15 bps
        # gross alpha for conf 6.8: 15 + 1.8*5 + 12 = 36.0 bps -> net = 21.0 bps
        contender = {
            "ticker": "COP",
            "sector": "Energy",
            "confidence": 6.8,
            "current_price": 120.0,
            "role": "能源板塊龍頭自癒",
        }
        res = await bidding_service.evaluate_bidding_for_batch([], contender=contender, base_quota_pct=0.35)
        assert res.bidding_status == "EXPAND"
        assert res.cross_sector_adjusted_quota_pct == 0.40


@pytest.mark.asyncio
async def test_bidding_ladder_neutral_proceed(bidding_service):
    """淨利差 5.0 ~ 14.9 bps -> NEUTRAL_PROCEED (35%)"""
    with patch.object(bidding_service, "calculate_candidate_friction", new_callable=AsyncMock) as mock_fric:
        mock_fric.return_value = (15.0, 10.0, 25.0)  # 摩擦 25 bps
        # gross alpha for conf 6.0: 15 + 1.0*5 + 12 = 32.0 bps -> net = 7.0 bps
        contender = {
            "ticker": "ECL",
            "sector": "Materials",
            "confidence": 6.0,
            "current_price": 240.0,
            "role": "材料板塊龍頭自癒",
        }
        res = await bidding_service.evaluate_bidding_for_batch([], contender=contender, base_quota_pct=0.35)
        assert res.bidding_status == "NEUTRAL_PROCEED"
        assert res.cross_sector_adjusted_quota_pct == 0.35


@pytest.mark.asyncio
async def test_bidding_ladder_defensive_contract(bidding_service):
    """淨利差 0.0 ~ 4.9 bps -> DEFENSIVE_CONTRACT (25%)"""
    with patch.object(bidding_service, "calculate_candidate_friction", new_callable=AsyncMock) as mock_fric:
        mock_fric.return_value = (20.0, 10.0, 30.0)  # 摩擦 30 bps
        # gross alpha for conf 6.0: 32.0 bps -> net = 2.0 bps
        contender = {
            "ticker": "ECL",
            "sector": "Materials",
            "confidence": 6.0,
            "current_price": 240.0,
            "role": "材料板塊龍頭自癒",
        }
        res = await bidding_service.evaluate_bidding_for_batch([], contender=contender, base_quota_pct=0.35)
        assert res.bidding_status == "DEFENSIVE_CONTRACT"
        assert res.cross_sector_adjusted_quota_pct == 0.25


@pytest.mark.asyncio
async def test_bidding_ladder_friction_blocked(bidding_service):
    """淨利差 < 0.0 bps (摩擦 > 毛 Alpha) -> FRICTION_BLOCKED (20%)"""
    with patch.object(bidding_service, "calculate_candidate_friction", new_callable=AsyncMock) as mock_fric:
        mock_fric.return_value = (30.0, 15.0, 45.0)  # 摩擦 45 bps
        # gross alpha for conf 6.0: 32.0 bps -> net = -13.0 bps
        contender = {
            "ticker": "HIGH_FRIC",
            "sector": "Materials",
            "confidence": 6.0,
            "current_price": 100.0,
            "role": "高摩擦材料自癒",
        }
        res = await bidding_service.evaluate_bidding_for_batch([], contender=contender, base_quota_pct=0.35)
        assert res.bidding_status == "FRICTION_BLOCKED"
        assert res.cross_sector_adjusted_quota_pct == 0.20


# ═══════════════════════════════════════════════════════════════════════════
# 4. Dataclass 序列化與反序列化測試
# ═══════════════════════════════════════════════════════════════════════════

def test_dataclass_serialization_roundtrip():
    metric = BiddingCandidateMetric(
        ticker="V",
        current_price=280.0,
        confidence_score=7.5,
        gross_alpha_bps=39.5,
        half_spread_bps=1.8,
        toxicity_bps=0.0,
        total_friction_bps=1.8,
        net_alpha_spread_bps=37.7,
        is_cross_sector_injected=True,
        injected_sector="Financials",
        bidding_status="AGGRESSIVE_EXPAND",
        allocated_quota_pct=0.45,
        rationale="強勁淨利差",
    )
    m_dict = metric.to_dict()
    restored_m = BiddingCandidateMetric.from_dict(m_dict)
    assert restored_m.ticker == "V"
    assert restored_m.allocated_quota_pct == 0.45
    assert restored_m.is_cross_sector_injected is True

    result = BiddingAssessmentResult(
        hurdle_bps=15.0,
        base_quota_pct=0.35,
        cross_sector_adjusted_quota_pct=0.45,
        bidding_status="AGGRESSIVE_EXPAND",
        candidates={"V": metric},
        average_friction_bps=1.8,
        portfolio_net_spread_bps=37.7,
        injected_ticker="V",
        injected_sector="Financials",
    )
    r_dict = result.to_dict()
    restored_r = BiddingAssessmentResult.from_dict(r_dict)
    assert restored_r.bidding_status == "AGGRESSIVE_EXPAND"
    assert restored_r.cross_sector_adjusted_quota_pct == 0.45
    assert "V" in restored_r.candidates
    assert restored_r.candidates["V"].net_alpha_spread_bps == 37.7


# ═══════════════════════════════════════════════════════════════════════════
# 5. 雙渠道戰報生成測試 (format_spread_bidding_report)
# ═══════════════════════════════════════════════════════════════════════════

def test_format_spread_bidding_report(bidding_service):
    metric = BiddingCandidateMetric(
        ticker="V",
        current_price=280.0,
        confidence_score=7.5,
        gross_alpha_bps=39.5,
        half_spread_bps=1.8,
        toxicity_bps=0.0,
        total_friction_bps=1.8,
        net_alpha_spread_bps=37.7,
        is_cross_sector_injected=True,
        injected_sector="Financials",
        bidding_status="AGGRESSIVE_EXPAND",
        allocated_quota_pct=0.45,
        rationale="強勁淨利差",
    )
    assessment = BiddingAssessmentResult(
        hurdle_bps=15.0,
        base_quota_pct=0.35,
        cross_sector_adjusted_quota_pct=0.45,
        bidding_status="AGGRESSIVE_EXPAND",
        candidates={"V": metric},
        average_friction_bps=1.8,
        portfolio_net_spread_bps=37.7,
        injected_ticker="V",
        injected_sector="Financials",
    )
    report = bidding_service.format_spread_bidding_report(assessment, channel="telegram")
    assert "開盤建倉前動態利差競標與摩擦抵消儀表" in report
    assert "ALPHA_SURPLUS" in report
    assert "15.0 bps" in report
    assert "V" in report
    assert "45.0%" in report
    assert "/batch" in report


# ═══════════════════════════════════════════════════════════════════════════
# 6. BatchCashDeploymentService 整合測試
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_batch_deployment_service_with_alpha_bidding(mock_settings):
    """測試在 BatchCashDeploymentService 中，跨板塊 Contender 受到利差競標動態上浮至 45%"""
    from src.services.batch_cash_deployment_service import BatchCashDeploymentService

    mock_broker = MagicMock()
    mock_account = MagicMock()
    mock_account.total_equity = 1685.0
    mock_account.available_cash = 1000.0
    mock_broker.get_account = AsyncMock(return_value=mock_account)

    # 模擬 2 檔重度科技持倉以觸發 DRIFT_BREACH
    mock_pos_nvda = MagicMock()
    mock_pos_nvda.symbol = "NVDA"
    mock_pos_nvda.market_value = 400.0
    mock_pos_nvda.unrealized_pnl = 10.0
    mock_pos_nvda.cost_basis = 390.0

    mock_pos_aapl = MagicMock()
    mock_pos_aapl.symbol = "AAPL"
    mock_pos_aapl.market_value = 300.0
    mock_pos_aapl.unrealized_pnl = 5.0
    mock_pos_aapl.cost_basis = 295.0

    mock_broker.get_positions = AsyncMock(return_value=[mock_pos_nvda, mock_pos_aapl])

    # 建立 mock bidding service 回傳 45% AGGRESSIVE_EXPAND
    mock_bidding_svc = MagicMock()
    mock_bidding_svc.is_enabled = True

    cand_metric = BiddingCandidateMetric(
        ticker="V",
        current_price=280.0,
        confidence_score=7.5,
        gross_alpha_bps=39.5,
        half_spread_bps=1.8,
        toxicity_bps=0.0,
        total_friction_bps=1.8,
        net_alpha_spread_bps=37.7,
        is_cross_sector_injected=True,
        injected_sector="Financials",
        bidding_status="AGGRESSIVE_EXPAND",
        allocated_quota_pct=0.45,
        rationale="強勁淨利差",
    )
    bidding_res = BiddingAssessmentResult(
        hurdle_bps=15.0,
        base_quota_pct=0.35,
        cross_sector_adjusted_quota_pct=0.45,
        bidding_status="AGGRESSIVE_EXPAND",
        candidates={"V": cand_metric},
        average_friction_bps=1.8,
        portfolio_net_spread_bps=37.7,
        injected_ticker="V",
        injected_sector="Financials",
    )
    mock_bidding_svc.evaluate_bidding_for_batch = AsyncMock(return_value=bidding_res)

    batch_svc = BatchCashDeploymentService(
        user_id="test_user",
        settings_service=mock_settings,
        broker=mock_broker,
        alpha_spread_bidding_service=mock_bidding_svc,
    )

    plan = await batch_svc.get_deployment_plan(batch_number=1)
    assert plan is not None
    assert "alpha_bidding_summary" in plan
    assert plan["alpha_bidding_summary"]["cross_sector_adjusted_quota_pct"] == 0.45

    cs_info = plan.get("cross_sector_injection")
    if cs_info:
        assert cs_info["injected_quota_pct"] == 0.45
        assert cs_info["alpha_bidding_status"] == "AGGRESSIVE_EXPAND"


# ═══════════════════════════════════════════════════════════════════════════
# 7. 對話路由器 /spread 指令直通測試
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_conversation_router_spread_command():
    """測試對話路由器 0-LLM /spread 指令直通"""
    from src.services.conversation_router import ConversationRouter

    router = ConversationRouter()
    # 驗證關鍵字已在系統快速指令白名單
    assert router._is_system_command("spread")
    assert router._is_system_command("/spread")
    assert router._is_system_command("bidding")
    assert router._is_system_command("friction")
    assert router._is_system_command("利差")
    assert router._is_system_command("摩擦")

    adapter = MagicMock()
    mock_broker = MagicMock()
    mock_broker.get_account = AsyncMock(return_value=MagicMock(total_equity=1685.0, available_cash=1000.0))
    mock_broker.get_positions = AsyncMock(return_value=[])

    with patch("src.services.broker_factory.BrokerFactory.get_broker", return_value=mock_broker):
        resp = await router._handle_system_command(adapter, "telegram_user", "/spread", "test_user")
        assert resp is not None
        assert "開盤建倉前動態利差競標與摩擦抵消儀表" in resp
        assert "基準利差門檻" in resp
