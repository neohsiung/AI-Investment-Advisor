"""
Tests for the tradable-capital cap.
可交易資本上限的測試。

Context (2026-08-11): the loop is being pointed at a live eToro account for
the first time. The account holds ~$1,048; the mandate is $100. Everything
below exists to make sure that gap cannot leak — a cap that silently stops
applying is worse than no cap, because the operator believes they are safe.

2026-08-11：此迴圈首次對實盤 eToro 帳戶運作。帳戶約有 $1,048，授權上限為 $100。
以下測試確保這個差額不會外洩——「靜默失效的上限」比沒有上限更糟，因為操作者會
以為自己是安全的。
"""
import pytest
from unittest.mock import MagicMock

from src.services.capital_policy import (
    DEFAULT_TRADABLE_CAPITAL_USD,
    is_small_test_capital,
    tradable_capital,
)


def _repo(**values):
    repo = MagicMock()
    repo.get.side_effect = lambda uid, key: values.get(key)
    return repo


class TestTradableCapital:

    def test_caps_a_larger_account(self):
        """The production shape: $1,048 account, $100 mandate."""
        assert tradable_capital("u1", 1048.64, _repo(tradable_capital_usd=100)) == 100.0

    def test_never_exceeds_the_real_account(self):
        """
        A cap above the balance must not invent money.
        上限高於餘額時不得憑空放大資金。
        """
        assert tradable_capital("u1", 40.0, _repo(tradable_capital_usd=100)) == 40.0

    def test_defaults_to_the_100_cap_when_unset(self):
        """
        An absent setting must not mean "use the whole account". During a live
        test the safe default is the restrictive one.
        設定缺漏不得等同「動用整個帳戶」；實測期間的安全預設是較嚴格的那個。
        """
        assert tradable_capital("u1", 1048.64, _repo()) == DEFAULT_TRADABLE_CAPITAL_USD

    def test_zero_is_the_documented_way_to_uncap(self):
        assert tradable_capital("u1", 1048.64, _repo(tradable_capital_usd=0)) == 1048.64

    def test_unreadable_settings_keep_the_cap(self):
        """
        A failing settings table must not unlock the account.
        設定表讀取失敗不得解鎖整個帳戶。
        """
        repo = MagicMock()
        repo.get.side_effect = RuntimeError("db down")
        assert tradable_capital("u1", 1048.64, repo) == DEFAULT_TRADABLE_CAPITAL_USD

    def test_garbage_cap_value_falls_back_to_the_default(self):
        assert tradable_capital("u1", 1048.64, _repo(tradable_capital_usd="abc")) == \
            DEFAULT_TRADABLE_CAPITAL_USD

    @pytest.mark.parametrize("nlv", [0, -5, None, "n/a"])
    def test_unusable_account_value_yields_zero(self, nlv):
        assert tradable_capital("u1", nlv, _repo()) == 0.0


class TestPositionSizingArithmetic:
    """
    The $10 minimum against $100 is the trap this configuration must clear.
    $100 資本搭配 $10 最小單，是本設定必須跨過的陷阱。
    """

    def test_the_010_default_collapses_onto_the_broker_minimum(self):
        """
        Documents WHY max_single_position_pct must be raised to 0.20.

        At 0.10 the per-position cap equals eToro's $10 minimum exactly, so
        any downward clamp lands below the minimum and the order is skipped —
        the system would evaluate signals, clear every threshold, and then
        place nothing at all.
        說明為何 max_single_position_pct 必須調到 0.20：0.10 時每筆上限剛好等於
        eToro 的 $10 最小單，任何往下鉗制都會跌破門檻而整筆略過。
        """
        capital = tradable_capital("u1", 1048.64, _repo(tradable_capital_usd=100))
        assert capital * 0.10 == 10.0  # == the broker minimum, zero headroom

    def test_020_leaves_clamp_headroom_above_the_minimum(self):
        capital = tradable_capital("u1", 1048.64, _repo(tradable_capital_usd=100))
        per_position = capital * 0.20
        assert per_position == 20.0
        assert per_position >= 2 * 10.0  # 2x the $10 minimum

    def test_four_positions_fit_beside_the_cash_target(self):
        """20% cash target leaves $80, i.e. four $20 positions."""
        capital = tradable_capital("u1", 1048.64, _repo(tradable_capital_usd=100))
        deployable = capital * (1 - 0.2)
        assert int(deployable // (capital * 0.20)) == 4


class TestSmallTestWaiver:

    def test_waives_at_the_100_mandate(self):
        assert is_small_test_capital(
            "u1", 1048.64, _repo(tradable_capital_usd=100, small_test_capital_usd=100)
        ) is True

    def test_rearms_when_capital_is_raised(self):
        """
        Raising the mandate past the waiver limit must re-arm the gate without
        anyone remembering to switch a flag back off.
        調高授權資本超過豁免上限時，關卡必須自動恢復，無需有人記得把旗標關回去。
        """
        assert is_small_test_capital(
            "u1", 1048.64, _repo(tradable_capital_usd=500, small_test_capital_usd=100)
        ) is False

    def test_uncapped_account_is_not_a_small_test(self):
        assert is_small_test_capital(
            "u1", 1048.64, _repo(tradable_capital_usd=0, small_test_capital_usd=100)
        ) is False
