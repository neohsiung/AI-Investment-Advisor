"""Behaviour of the risk keyword matching rule (whole word, not substring).
風險關鍵字比對規則的行為：整詞比對，不是子字串。

Context: substring matching let 'es', 'it', 'am' hit nearly every headline and trigger a council each time.
背景：子字串比對讓 'es'、'it'、'am' 幾乎命中每則標題，每次都觸發議會。
"""
import pytest

from src.domain.entities import RiskKeyword
from src.domain.keyword_match import keyword_in_text


@pytest.mark.parametrize("keyword,text", [
    ("es", "Amazon Jumps 5% as Morgan Stanley Names It Top Pick"),
    ("am", "The Banks Locked Agents Out"),
    ("ip", "KinderCare to Participate in Investor Conference"),
    ("mu", "Elon Musk's SpaceX Stock Giveaway"),
    ("close", "Company disclosed a new buyback"),
    ("ai", "Analysts said demand is steady"),
    ("war", "Software stocks rally"),
])
def test_keyword_inside_another_word_does_not_match(keyword, text):
    assert not keyword_in_text(keyword, text)


@pytest.mark.parametrize("keyword,text", [
    ("crash", "Markets CRASH after the open"),
    ("ai", "AI-driven chip demand"),
    ("rate hike", "Why a rate hike may shake the market"),
    ("s&p 500", "S&P 500 falls 2%"),
    ("關稅", "美國宣布關稅上調"),
    ("war", "Trade war fears return"),
])
def test_whole_word_matches_case_insensitively(keyword, text):
    assert keyword_in_text(keyword, text)


@pytest.mark.parametrize("keyword,text", [
    ("tariff", "New tariffs announced"),
    ("crash", "Two crashes in one week"),
    ("sanction", "EU widens sanctions"),
    ("rate hike", "Rate hikes are coming"),
    ("war", "Currency wars"),
])
def test_plural_of_a_word_of_three_or_more_letters_matches(keyword, text):
    assert keyword_in_text(keyword, text)


@pytest.mark.parametrize("keyword,text", [
    ("sanction", "Acme sanctioned over fraud"),
    ("recall", "Automaker recalled 2 million cars"),
    ("bankrupt", "Two bankruptcies this quarter"),
    ("plunge", "Shares plunged 9%"),
    ("fraud", "Fraudulent accounts found"),
])
def test_keyword_of_five_or_more_letters_matches_inflected_forms(keyword, text):
    assert keyword_in_text(keyword, text)


def test_long_keyword_still_needs_a_word_start():
    assert not keyword_in_text("crash", "a microcrash in rates")


def test_surrounding_whitespace_in_a_stored_keyword_is_ignored():
    assert keyword_in_text("  crash ", "Markets crash")
    assert not keyword_in_text("   ", "double  space")


def test_two_letter_keyword_has_no_plural_form():
    assert not keyword_in_text("it", "its guidance")


def test_empty_keyword_never_matches():
    assert not keyword_in_text("", "anything")


def test_entity_score_uses_whole_word_rule():
    kw = RiskKeyword(keyword="es", weight=1.0)
    assert kw.score("Morgan Stanley Names It Top Pick") == 0.0
    assert kw.score("ES futures slide overnight") == 1.0


# ── Shadow rule (DD-2026-1025, recorded only, never decides) / shadow 規則（只記錄，不做決定）──

from src.domain.keyword_match import shadow_weight  # noqa: E402


@pytest.mark.parametrize("keyword,weight,source,expected", [
    ("es", 1.0, "trends", 0.0),        # short trending ticker: excluded from free-text matching
    ("nvda", 0.4, "trends", 0.0),
    ("tesla", 1.0, "trends", 0.5),     # longer trend keyword: kept, capped
    ("crash", 1.0, "seed", 0.5),       # one keyword alone can no longer reach the 0.6 threshold
    ("crash", 0.3, "seed", 0.3),
    ("war", 1.0, None, 0.5),
])
def test_shadow_weight(keyword, weight, source, expected):
    assert shadow_weight(keyword, weight, source) == expected


def test_entity_shadow_score_needs_a_whole_word_match_and_an_active_keyword():
    kw = RiskKeyword(keyword="crash", weight=1.0, source="seed")
    assert kw.shadow_score("Markets crash") == 0.5
    assert kw.shadow_score("a microcrash in rates") == 0.0
    kw.is_active = False
    assert kw.shadow_score("Markets crash") == 0.0
