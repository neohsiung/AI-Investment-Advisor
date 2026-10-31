"""An order whose quantity cannot be read is not sent, and a missing quantity never becomes $100.
BUY quantity is a USD amount, so a made-up 100.0 is a real $100 order. / 讀不到數量的單不送出；缺值不補 100。"""
import json

import pytest

from src.agents.action_extractor import ActionExtractorAgent, parse_order_quantity


@pytest.mark.parametrize("raw,expected", [
    (10, 10.0), ("10", 10.0), (" 2.5 ", 2.5), (3.0, 3.0), ("1,000", 1000.0), ("1,234,567.50", 1234567.5),
])
def test_parse_order_quantity_accepts_plain_positive_numbers(raw, expected):
    assert parse_order_quantity(raw) == expected


def test_a_dollar_amount_is_only_accepted_for_a_buy():
    """BUY quantity is USD; SELL quantity is shares, so '$500' on a SELL would be read as 500 shares."""
    assert parse_order_quantity("$250", "BUY") == 250.0
    assert parse_order_quantity("$250", "buy") == 250.0
    assert parse_order_quantity("$250", "SELL") is None
    assert parse_order_quantity("$250") is None


@pytest.mark.parametrize("raw", ["1,5", "1,00", "1,0,0", "1_000", "$$5", "1e3", "1e400", "10 shares", "5.", ".5x",
                                 "１０", 10 ** 400, "9" * 400])
def test_ambiguous_or_overflowing_text_is_unreadable(raw):
    """European decimals ('1,5' -> 15.0), underscores, exponents and huge integers must not become a quantity."""
    assert parse_order_quantity(raw, "BUY") is None


@pytest.mark.parametrize("raw", [None, "", "  ", "abc", "5%", "10 %", 0, 0.0, -3, "-3", float("nan"), float("inf"),
                                 "nan", "inf", True, [], {}])
def test_parse_order_quantity_rejects_everything_else(raw):
    """A percentage is a weight, not a quantity: '5%' used to become 5.0 (a $5 BUY)."""
    assert parse_order_quantity(raw) is None


def _block(actions):
    return "[CONVINCING_ACTION]\n" + json.dumps({"actions": actions}) + "\n[/CONVINCING_ACTION]"


def test_json_block_without_quantity_yields_none_not_100():
    agent = ActionExtractorAgent(user_id="u")
    orders = agent._extract_json_block(_block([{"ticker": "aapl", "action": "BUY", "confidence": 8}]))
    assert len(orders) == 1 and orders[0]["quantity"] is None


def test_json_block_with_zero_quantity_yields_none():
    agent = ActionExtractorAgent(user_id="u")
    orders = agent._extract_json_block(_block([{"ticker": "aapl", "action": "SELL", "quantity": 0}]))
    assert orders and orders[0]["quantity"] is None


def test_json_block_keeps_a_real_quantity():
    agent = ActionExtractorAgent(user_id="u")
    orders = agent._extract_json_block(_block([{"ticker": "aapl", "action": "SELL", "quantity": 12}]))
    assert orders[0]["quantity"] == 12


def test_source_has_no_quantity_default_of_100():
    import inspect

    from src.agents import action_extractor as mod
    src = inspect.getsource(mod)
    assert "or 100.0" not in src and "else 100.0" not in src
