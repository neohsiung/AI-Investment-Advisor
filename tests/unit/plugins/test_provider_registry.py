"""
Data provider registry.

Provider wiring lived in six independently-maintained places inside
market_data_service.py: eight hand-constructed instances whose `.id` was assigned
AFTER construction, plus six separate hand-ordered priority lists (quote,
batch-quote, history, indicators, news, fundamentals), plus an
`EQUITY_ONLY_PROVIDER_IDS` frozenset.

Six orderings over one population is a drift machine, and it had already drifted:
`financialdata` appeared in the batch-quote chain and in NO other list, so it was
easy to miss — the first draft of config/data_providers.yaml gave it no
capabilities at all, which would have silently dropped it from batch price fetches.
That is exactly the failure the manifest is meant to prevent, so the expected
chains are asserted here explicitly.

供應商接線原本分散在 market_data_service 的六處：八個手動建構（建構後才指派 .id）、
六份各自手排的優先序清單，以及一個 frozenset。六份順序共用同一群供應商必然漂移，
而且已經漂移過：financialdata 只出現在批次報價鏈中，本 manifest 的初稿漏掉它。
"""
from __future__ import annotations

import pytest

from src.data.providers import (
    CAPABILITIES,
    capability_order,
    get_spec,
    list_specs,
    registry,
)
from src.data.providers.base import MarketDataProvider
from src.plugins.registry import PluginError


class TestManifest:

    def test_manifest_loads(self):
        specs = list_specs(force=True)
        assert specs, "no providers declared"

    def test_every_class_path_resolves_to_a_market_data_provider(self):
        """
        The base-class check is what makes the manifest's dotted `class:` safe to
        import. A path naming something that is not a MarketDataProvider must be
        rejected, not constructed.
        基底類別檢查讓 manifest 的 dotted class 可安全匯入；指向非供應商的路徑必須被拒絕。
        """
        for spec in list_specs(force=True):
            cls = registry.resolve_dotted(spec.class_path, key=spec.id)
            assert issubclass(cls, MarketDataProvider)

    def test_unknown_capability_names_are_rejected(self):
        """
        A typo'd capability would remove the provider from the chain the author
        meant to add it to, while looking like a successful edit.
        拼錯的 capability 會讓供應商從作者想加入的鏈中消失，卻看起來像編輯成功。
        """
        with pytest.raises(PluginError, match="unknown capability"):
            capability_order("quotes")   # note the plural

    @pytest.mark.parametrize("capability", CAPABILITIES)
    def test_each_capability_has_at_least_one_provider(self, capability):
        assert capability_order(capability), f"nothing serves '{capability}'"


class TestChainsMatchTheOriginalCode:
    """
    These orders were transcribed from the six hardcoded lists. Asserting them
    means a manifest edit that silently reorders a chain — for instance moving the
    paid Polygon ahead of free Yahoo for news — shows up as a test change rather
    than as a quiet cost or behaviour shift.
    這些順序由六份硬編清單轉錄而來；若 manifest 編輯靜默改變順序（例如把付費的
    Polygon 排到免費 Yahoo 之前），會以測試變更的形式顯現，而非靜默的成本變化。
    """

    EXPECTED = {
        "quote":        ["polygon", "tiingo", "finnhub", "fmp", "alpha_vantage", "yahoo_finance"],
        "quote_batch":  ["polygon", "tiingo", "fmp", "financialdata", "yahoo_finance"],
        "history":      ["polygon", "tiingo", "fmp", "yahoo_finance"],
        "indicators":   ["polygon", "yahoo_finance"],
        "news":         ["tiingo", "finnhub", "alpha_vantage", "fmp", "yahoo_finance", "polygon"],
        "fundamentals": ["polygon", "finnhub", "fmp", "alpha_vantage", "yahoo_finance"],
    }

    @pytest.mark.parametrize("capability,expected", sorted(EXPECTED.items()))
    def test_chain(self, capability, expected):
        assert [s.id for s in capability_order(capability)] == expected

    def test_financialdata_is_in_the_batch_chain(self):
        """
        The specific provider the first manifest draft dropped. It appears in that
        one chain and nowhere else, so nothing else would have caught its absence.
        初稿漏掉的就是這一個：它只出現在此鏈中，其他地方都不會察覺它消失。
        """
        assert "financialdata" in [s.id for s in capability_order("quote_batch")]

    def test_every_capability_is_covered_by_an_expectation(self):
        """Adding a capability must come with an expected order, not silence."""
        assert set(self.EXPECTED) == set(CAPABILITIES)


class TestEquityOnlyRouting:

    def test_equity_only_derives_from_asset_classes(self):
        """
        Was a frozenset of two ids maintained by hand. Index symbols must never be
        routed to an equities-only provider.
        原本是手工維護的兩個 id 的 frozenset；指數符號不得路由至個股專用供應商。
        """
        equity_only = {s.id for s in list_specs(force=True) if s.equity_only}
        assert equity_only == {"polygon", "tiingo"}

    def test_service_property_matches_the_manifest(self):
        from unittest.mock import MagicMock, patch

        with patch('src.data.providers.build_all', return_value={}), \
             patch('src.services.market_data_service.InternetSearchService'), \
             patch('src.services.market_data_service.SettingsService'):
            from src.services.market_data_service import MarketDataService

            svc = MarketDataService(user_id="u1")
            assert svc.EQUITY_ONLY_PROVIDER_IDS == frozenset({"polygon", "tiingo"})


class TestCredentialsAreDeclared:

    def test_every_keyed_provider_declares_its_credential_setting(self):
        """
        The settings UI renders credential fields from these declarations, so an
        omission means a provider that cannot be configured through the product.
        設定 UI 依這些宣告渲染憑證欄位；漏宣告等於該供應商無法透過產品設定。
        """
        # yahoo_finance needs no key; everything else does.
        for spec in list_specs(force=True):
            if spec.id == "yahoo_finance":
                continue
            assert spec.credentials, f"{spec.id} declares no credentials"

    def test_credential_keys_exist_in_the_settings_schema(self):
        """
        A credential naming a key absent from config/settings_schema.yaml would
        never be rendered, so it could never be set.
        憑證若指向 settings_schema 中不存在的鍵，就永遠不會被渲染，也就無法設定。
        """
        from src.config.settings_schema import load_schema

        schema = load_schema()
        missing = [
            (spec.id, key)
            for spec in list_specs(force=True)
            for key in spec.credentials
            if not schema.is_known(key)
        ]
        assert not missing, f"credentials not in the settings schema: {missing}"

    def test_enable_switches_exist_in_the_settings_schema(self):
        from src.config.settings_schema import load_schema

        schema = load_schema()
        missing = [
            (spec.id, spec.enabled_setting)
            for spec in list_specs(force=True)
            if spec.enabled_setting and not schema.is_known(spec.enabled_setting)
        ]
        assert not missing, f"enable switches not in the settings schema: {missing}"


class TestNoHardcodedListsRemain:
    """
    Source-level guards against the old patterns returning.

    Both assertions strip comments first. The module DOCUMENTS the patterns it
    replaced ("this was eight `self.x = XProvider(...)` / `self.x.id = \"x\"`
    pairs"), and a naive regex matches that prose instead of real code — which it
    did on the first attempt here, as it had twice before in this series.
    兩個斷言都先剝除註解：模組的註解引用了被取代的舊寫法，
    直接用正則會命中說明文字而非真正的程式碼（本檔初版與先前兩次都犯了這個錯）。
    """

    @staticmethod
    def _code_only() -> str:
        from pathlib import Path

        raw = Path("src/services/market_data_service.py").read_text()
        return "\n".join(
            line for line in raw.splitlines() if not line.lstrip().startswith("#")
        )

    def test_market_data_service_has_no_provider_literal_lists(self):
        import re

        matches = re.findall(
            r"\[\s*self\.(?:polygon|tiingo|fmp|yfinance|finnhub|alpha_vantage|financialdata)\b",
            self._code_only(),
        )
        assert not matches, f"{len(matches)} hardcoded provider list(s) are back"

    def test_ids_are_not_assigned_imperatively(self):
        import re

        assert not re.search(r"self\.\w+\.id\s*=\s*[\"\']", self._code_only()), (
            "provider ids are being assigned after construction again; the id "
            "belongs to the manifest"
        )
