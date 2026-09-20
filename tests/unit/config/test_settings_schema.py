"""
The settings registry must stay tied to reality.

Two directions of drift, both of which have already happened in this codebase:

  * a key the code reads but the schema omits — the operator has no way to set
    it, and `get_setting` silently returns None;
  * a schema default that disagrees with the code's own constant — behaviour
    changes the moment the row is absent. `keyword_max_count` was written into
    this schema as 60 while RiskKeywordService.MAX_KEYWORDS was 1000, and the
    pruning tests caught it.

註冊表必須與程式碼保持一致：漏收鍵會讓使用者無法設定；預設值與程式常數不符
則會在該列缺失時靜默改變行為（keyword_max_count 就發生過 60 vs 1000）。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.config.settings_schema import (
    SettingsSchemaError,
    coerce_value,
    load_schema,
    schema_default,
)

SRC = Path("src")

# Keys read from the settings table that deliberately are NOT user-facing
# configuration, so they must not appear in the schema.
#   * machine-written scratch rows (53 of 128 live rows are alpha_spy_* code)
#   * runtime caches and cursors
#   * legacy/aliased spellings kept only for backwards-compatible reads
# 這些鍵刻意不納入 schema：機器寫入的暫存、執行期快取、以及僅供舊路徑讀取的別名。
NOT_USER_FACING = {
    "cached_intelligence_briefing",
    "last_intelligence_timestamp",
    "readwise_last_sync",
    "scheduler_reload_signal",
    "notification_channels",
    "channel_telegram_bot_token_legacy",
    # lower-case / bare aliases of schema keys, read but never written by the UI
    "ai_provider",
    "preferred_provider",
    "api_key",
    "AI_API_KEY",
    "API_KEY",
    "openrouter_api_key",
    "OPENROUTER_BASE_URL",
    "ALPHA_VANTAGE_API_KEY",
    "FINNHUB_API_KEY",
    "GROQ_API_KEY",
    "READWISE_API_KEY",
    "telegram_chat_id",
    "source_gemini_api_key",
    "source_groq_api_key",
    "risk_challenge",
    "risk_consistency",
    "risk_count",
    "risk_exposure",
    "risk_factor_count",
    "risk_keywords_nonempty",
    "risk_level",
    "risk_management",
    "risk_score",
    "risk_stance",
    "enabled_report_types",
}

_GET_SETTING = re.compile(r'get_setting\(\s*["\']([a-zA-Z0-9_.]+)["\']')


def _keys_read_in_src() -> set[str]:
    found = set()
    for path in SRC.rglob("*.py"):
        try:
            text = path.read_text()
        except OSError:
            continue
        found.update(_GET_SETTING.findall(text))
    return found


class TestSchemaIntegrity:

    def test_loads(self):
        schema = load_schema()
        assert schema.fields, "schema loaded empty"
        assert schema.groups, "schema declares no groups"

    def test_every_field_belongs_to_a_declared_group(self):
        schema = load_schema()
        group_ids = {g.id for g in schema.groups}
        orphans = {k: f.group for k, f in schema.fields.items() if f.group not in group_ids}
        assert not orphans, f"fields in undeclared groups: {orphans}"

    def test_every_field_is_reachable_from_by_group(self):
        """A field in no group would exist but never render in the UI."""
        schema = load_schema()
        rendered = {f.key for g in schema.by_group() for f in g["fields"]}
        assert rendered == set(schema.fields), (
            f"not rendered: {set(schema.fields) - rendered}"
        )

    def test_enum_defaults_are_members_of_their_enum(self):
        schema = load_schema()
        bad = [
            f.key for f in schema.fields.values()
            if f.type == "enum" and f.default is not None
            and str(f.default) not in [str(e) for e in (f.enum or [])]
        ]
        assert not bad, f"enum defaults outside their own enum: {bad}"

    def test_every_default_validates_against_its_own_field(self):
        """
        A default that its own field would reject is a latent failure: the first
        save that round-trips it would 400.
        自身欄位會拒絕的預設值是潛在錯誤：第一次回寫就會被驗證擋下。
        """
        schema = load_schema()
        for key, f in schema.fields.items():
            if f.default is None:
                continue
            coerce_value(key, f.default)  # must not raise

    def test_numeric_bounds_are_ordered(self):
        schema = load_schema()
        bad = [
            f.key for f in schema.fields.values()
            if f.minimum is not None and f.maximum is not None and f.minimum > f.maximum
        ]
        assert not bad, f"min > max: {bad}"

    def test_depends_targets_exist_and_are_boolean(self):
        schema = load_schema()
        problems = []
        for f in schema.fields.values():
            if not f.depends:
                continue
            target = schema.get(f.depends)
            if target is None:
                problems.append(f"{f.key} depends on missing {f.depends}")
            elif target.type != "bool":
                problems.append(f"{f.key} depends on non-bool {f.depends} ({target.type})")
        assert not problems, problems


class TestSchemaMatchesCode:

    def test_keys_read_by_code_are_registered(self):
        read = _keys_read_in_src()
        schema = load_schema()
        missing = sorted(k for k in read if not schema.is_known(k) and k not in NOT_USER_FACING)
        assert not missing, (
            "these keys are read via get_setting() but are not in "
            "config/settings_schema.yaml, so they have no default, no type and "
            f"no UI field: {missing}"
        )

    def test_risk_keyword_defaults_match_the_service_constants(self):
        """The specific drift that shipped and was caught by the pruning tests."""
        from src.services.risk_keyword_service import RiskKeywordService

        assert schema_default("keyword_max_count") == RiskKeywordService.MAX_KEYWORDS
        assert schema_default("keyword_target_count") == RiskKeywordService.DEFAULT_TARGET

    def test_trading_gate_default_is_fail_closed(self):
        """
        `ai_trading_enabled` must default to false. It previously defaulted to
        "true" at the read site in risk_manager, so an absent row authorised
        live order placement.
        缺少該列不得等於授權下單。
        """
        assert schema_default("ai_trading_enabled") is False


class TestValidation:

    @pytest.mark.parametrize("value,expected", [
        ("true", True), ("false", False), (1, True), (0, False), (True, True),
    ])
    def test_bool_coercion(self, value, expected):
        assert coerce_value("ai_trading_enabled", value) is expected

    def test_rejects_out_of_range_int(self):
        with pytest.raises(SettingsSchemaError):
            coerce_value("auto_trade_threshold", 101)

    def test_rejects_unknown_enum_member(self):
        with pytest.raises(SettingsSchemaError):
            coerce_value("etoro_mode", "paper")

    def test_rejects_malformed_time(self):
        with pytest.raises(SettingsSchemaError):
            coerce_value("schedule_daily", "7pm")

    def test_accepts_and_normalises_time(self):
        assert coerce_value("schedule_daily", "7:05") == "07:05"

    def test_json_accepts_a_string_payload(self):
        assert coerce_value("target_allocation", '{"NVDA": 0.1}') == {"NVDA": 0.1}

    def test_list_rejects_a_json_object(self):
        with pytest.raises(SettingsSchemaError):
            coerce_value("ai_energy_tickers", '{"not": "a list"}')

    def test_unknown_key_passes_through_untouched(self):
        """
        Machine-written rows must survive coercion. The table holds generated
        code under alpha_spy_* keys that the registry deliberately omits.
        機器寫入的列必須原樣通過；alpha_spy_* 等鍵刻意不在註冊表中。
        """
        assert coerce_value("alpha_spy_1234", "def f(): pass") == "def f(): pass"


class TestSecrets:

    def test_credentials_are_marked_secret(self):
        schema = load_schema()
        for key in ("etoro_api_key", "etoro_user_key", "channel_email_smtp_pass",
                    "futu_pwd", "webhook_api_key", "source_polygon_api_key"):
            assert schema.is_secret(key), f"{key} must be type: secret"

    def test_non_credentials_are_not_secret(self):
        schema = load_schema()
        for key in ("auto_trade_threshold", "risk_profile", "target_cash_ratio"):
            assert not schema.is_secret(key)

    def test_repository_encrypts_schema_secrets_the_regex_would_miss(self):
        """
        `futu_pwd` is the case that motivated union-ing the schema with the
        legacy name patterns: the pattern list contains "_pass", not "pwd", so
        that password was previously stored in plaintext.
        futu_pwd 正是要把 schema 與舊正則取聯集的原因：模式只有 "_pass"，
        因此該密碼過去以明文儲存。
        """
        from unittest.mock import MagicMock

        from src.repositories.settings_repository import AlchemySettingsRepository

        repo = AlchemySettingsRepository(engine=MagicMock())
        assert repo._should_encrypt("futu_pwd") is True
        assert not any(p in "futu_pwd" for p in repo.sensitive_patterns), (
            "if the regex now matches futu_pwd this test no longer proves anything"
        )

    def test_legacy_encrypted_keys_absent_from_schema_still_encrypt(self):
        """
        Switching to schema-only would have downgraded 8 live credentials to
        plaintext. The union keeps them encrypted.
        改為只看 schema 會讓 8 個線上憑證變成明文；聯集保住它們。
        """
        from unittest.mock import MagicMock

        from src.repositories.settings_repository import AlchemySettingsRepository

        repo = AlchemySettingsRepository(engine=MagicMock())
        schema = load_schema()
        for legacy in ("etoro_token", "openrouter_api_key", "nvidia_api_key",
                       "fred_api_key", "tiingo_api_key"):
            assert not schema.is_known(legacy), f"{legacy} is in the schema now; update this test"
            assert repo._should_encrypt(legacy) is True


class TestDatabaseRemainsTheAuthority:
    """
    The settings table is the source of truth for VALUES. The schema is metadata
    only (types, labels, validation, shipped defaults). These tests pin that
    boundary, because a registry file is exactly the thing that could quietly
    become a second source of truth.

    settings 表是「值」的唯一權威；schema 只是中介資料（型別、標籤、驗證、
    出貨預設值）。註冊表檔案正是最容易悄悄變成第二真相來源的東西，故明確固定邊界。
    """

    def test_schema_file_contains_no_values_only_metadata(self):
        """No credential or user value may be committed into the schema file."""
        from pathlib import Path

        text = Path("config/settings_schema.yaml").read_text()
        assert "ENC:" not in text, "an encrypted value leaked into the schema file"
        assert "gAAAAA" not in text, "a Fernet ciphertext leaked into the schema file"

    def test_stored_value_overrides_the_schema_default(self):
        """
        A row in the settings table must win over the shipped default — the
        lowest tier of the documented precedence
        (settings table > .env > code defaults).
        settings 表的值必須勝過出貨預設值。
        """
        from unittest.mock import MagicMock

        from src.services.settings_service import SettingsService

        repo = MagicMock()
        # The repository returns whatever is stored, ignoring the passed default.
        repo.get.side_effect = lambda uid, key, default=None: 0.31
        svc = SettingsService(user_id="u1", settings_repo=repo)

        assert schema_default("target_cash_ratio") == 0.2
        assert svc.get_setting("target_cash_ratio") == 0.31

    def test_schema_default_used_only_when_nothing_is_stored(self):
        from unittest.mock import MagicMock

        from src.services.settings_service import SettingsService

        repo = MagicMock()
        # Mimic "no row": the repository echoes back the default it was given.
        repo.get.side_effect = lambda uid, key, default=None: default
        svc = SettingsService(user_id="u1", settings_repo=repo)

        assert svc.get_setting("target_cash_ratio") == schema_default("target_cash_ratio")

    def test_explicit_caller_default_still_wins(self):
        """Existing call sites that pass their own default keep their behaviour."""
        from unittest.mock import MagicMock

        from src.services.settings_service import SettingsService

        repo = MagicMock()
        repo.get.side_effect = lambda uid, key, default=None: default
        svc = SettingsService(user_id="u1", settings_repo=repo)

        assert svc.get_setting("target_cash_ratio", 0.99) == 0.99

    def test_seeding_values_come_from_the_registry(self):
        """
        `initialize_user_settings` had its own defaults dict, so one number lived
        in three places (here, the read site, the schema). It now reads the
        registry.
        種子值改由註冊表提供，避免同一個數字存在三處。
        """
        import inspect

        from src.services.settings_service import SettingsService

        src = inspect.getsource(SettingsService.initialize_user_settings)
        assert "_sc.default(" in src, "seeding no longer sources from the schema"
        for literal in ('"risk_profile": "Aggressive"', '"target_cash_ratio": 0.2'):
            assert literal not in src, f"literal seed value reappeared: {literal}"
