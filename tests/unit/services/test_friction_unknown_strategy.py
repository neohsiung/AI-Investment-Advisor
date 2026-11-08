"""An unregistered strategy name takes the stricter friction reading and carries the _unknown_strategy marker.
未登記的策略名在摩擦閘門採較嚴判定（視為例行單、受門檻約束），並帶 _unknown_strategy 標記。"""
import pytest

from src.services.friction_aware_tranche_sizing_service import FrictionAwareTrancheSizingService


async def _run(name):
    service = FrictionAwareTrancheSizingService(user_id="test_user")
    return await service.evaluate_order_friction_and_tranche(
        ticker="NVDA", action="BUY", quantity=5.0, current_price=135.0, strategy_name=name,
        expected_alpha_pct=0.0040, delta_weight=None,
    )


@pytest.mark.asyncio
async def test_unknown_name_is_held_to_the_hurdle_and_flagged():
    metric = await _run("momentum_entry")
    assert metric.decision == "BLOCKED_BY_FRICTION"
    assert metric.unknown_strategy is True
    assert metric.to_dict()["_unknown_strategy"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("name", [None, "", "AutomatedTrading", "emergency_hedge", "stop_loss"])
async def test_unnamed_and_registered_names_keep_their_exemption_and_are_not_flagged(name):
    metric = await _run(name)
    assert metric.passed_hurdle is True
    assert metric.unknown_strategy is False
