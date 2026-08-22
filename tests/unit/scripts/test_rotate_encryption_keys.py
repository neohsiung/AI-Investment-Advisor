"""
Tests for scripts/rotate_encryption_keys.py.

Context (2026-08-20): this script runs once, against production, holding the
only copy of two encryption keys, on the table that stores the live eToro
credentials. There is no second chance to notice it did the wrong thing — a
row it silently skips becomes a credential encrypted under a retired key,
which `_decrypt` then hands back as ciphertext-looking-like-a-value
(settings_repository.py:155). So the cases that matter most here are the
refusals, not the happy path.

本腳本只會對正式環境跑一次，且處理的是實盤 eToro 憑證所在的資料表；
漏掉一列就會留下綁在退役金鑰上的憑證，而 _decrypt 會把它當成有效值回傳。
因此測試重點在「該中止時有沒有中止」，而非happy path。
"""
import json

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from scripts.rotate_encryption_keys import RotationError, rotate
from src.data.models import Base, LLMProvider, Setting

USER = "00000000-0000-4000-a000-000000000001"

APP_OLD = Fernet.generate_key().decode()
APP_NEW = Fernet.generate_key().decode()
LLM_OLD = Fernet.generate_key().decode()
LLM_NEW = Fernet.generate_key().decode()

THIRD_PARTY = Fernet.generate_key().decode()  # a key the script does not have


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng, tables=[Setting.__table__, LLMProvider.__table__])
    return eng


@pytest.fixture
def keys(monkeypatch):
    """Both key pairs present — the state the script requires."""
    monkeypatch.setenv("APP_SECRET_KEY", APP_OLD)
    monkeypatch.setenv("APP_SECRET_KEY_NEW", APP_NEW)
    monkeypatch.setenv("LLM_CREDENTIAL_KEY", LLM_OLD)
    monkeypatch.setenv("LLM_CREDENTIAL_KEY_NEW", LLM_NEW)


def _enc(key: str, plaintext: str, prefix: str = "ENC:") -> str:
    return f"{prefix}{Fernet(key.encode()).encrypt(plaintext.encode()).decode()}"


def _add_setting(engine, key: str, value: str):
    session = sessionmaker(bind=engine)()
    session.add(Setting(user_id=USER, key=key, value=value))
    session.commit()
    session.close()


def _add_provider(engine, code: str, encrypted: str):
    session = sessionmaker(bind=engine)()
    session.add(LLMProvider(
        user_id=USER, provider_code=code, display_name=code,
        encrypted_api_key=encrypted,
    ))
    session.commit()
    session.close()


def _raw_setting(engine, key: str):
    """
    The value as the application sees it, read outside the ORM.

    `Setting.value` is Column(JSON), so the column text is JSON-encoded and a
    plain SELECT hands back '"ENC:..."' — quotes and all. Decoding here keeps
    the tests talking about the value rather than about its serialisation,
    and leaves the genuinely double-serialised rows (TestJsonQuoting) visibly
    different: those decode to a string that STILL has quotes around it.
    settings.value 是 JSON 欄位，直接 SELECT 會拿到帶引號的 JSON 文字；
    這裡解碼一層，讓測試討論的是值本身，而真正被重複序列化的列解碼後仍帶引號。
    """
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT value FROM settings WHERE user_id=:u AND key=:k"),
            {"u": USER, "k": key},
        ).fetchone()
    return json.loads(row[0]) if row else None


def _raw_provider(engine, code: str):
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT encrypted_api_key FROM llm_providers WHERE provider_code=:c"),
            {"c": code},
        ).fetchone()
    return row[0] if row else None


def _decrypts_to(ciphertext: str, key: str, prefix: str) -> str:
    assert ciphertext.startswith(prefix), f"expected {prefix} prefix, got {ciphertext[:8]!r}"
    token = ciphertext[len(prefix):]
    return Fernet(key.encode()).decrypt(token.encode()).decode()


class TestHappyPath:
    def test_settings_value_is_readable_under_the_new_key(self, engine, keys):
        _add_setting(engine, "etoro_api_key", _enc(APP_OLD, "etoro-secret-abc"))

        assert rotate(commit=True, engine=engine) == 0

        stored = _raw_setting(engine, "etoro_api_key")
        assert _decrypts_to(stored, APP_NEW, "ENC:") == "etoro-secret-abc"

    def test_old_key_can_no_longer_open_the_rotated_value(self, engine, keys):
        """The point of rotation: the leaked key stops working."""
        _add_setting(engine, "etoro_user_key", _enc(APP_OLD, "user-key-xyz"))

        rotate(commit=True, engine=engine)

        stored = _raw_setting(engine, "etoro_user_key")
        with pytest.raises(Exception):
            _decrypts_to(stored, APP_OLD, "ENC:")

    def test_provider_key_is_rewrapped_with_the_llm_key(self, engine, keys):
        _add_provider(engine, "openai", _enc(LLM_OLD, "sk-live-123", "FERN:"))

        assert rotate(commit=True, engine=engine) == 0

        stored = _raw_provider(engine, "openai")
        assert _decrypts_to(stored, LLM_NEW, "FERN:") == "sk-live-123"

    def test_each_table_uses_its_own_key_pair(self, engine, keys):
        """
        A settings row must not end up under LLM_CREDENTIAL_KEY_NEW, or vice
        versa — they are read back by different ciphers.
        """
        _add_setting(engine, "etoro_api_key", _enc(APP_OLD, "from-settings"))
        _add_provider(engine, "nim", _enc(LLM_OLD, "from-provider", "FERN:"))

        rotate(commit=True, engine=engine)

        assert _decrypts_to(_raw_setting(engine, "etoro_api_key"), APP_NEW, "ENC:") == "from-settings"
        assert _decrypts_to(_raw_provider(engine, "nim"), LLM_NEW, "FERN:") == "from-provider"


class TestDryRunIsTheDefault:
    def test_dry_run_leaves_the_row_untouched(self, engine, keys):
        original = _enc(APP_OLD, "etoro-secret-abc")
        _add_setting(engine, "etoro_api_key", original)

        assert rotate(commit=False, engine=engine) == 0

        assert _raw_setting(engine, "etoro_api_key") == original


class TestRefusals:
    """Every case where writing something would be worse than writing nothing."""

    def test_value_encrypted_under_an_unknown_key_aborts_the_batch(self, engine, keys):
        _add_setting(engine, "etoro_api_key", _enc(APP_OLD, "healthy"))
        _add_setting(engine, "stripe_secret", _enc(THIRD_PARTY, "opaque"))

        assert rotate(commit=True, engine=engine) == 1

        assert _decrypts_to(_raw_setting(engine, "etoro_api_key"), APP_OLD, "ENC:") == "healthy"

    def test_partial_rotation_never_reaches_the_database(self, engine, keys):
        """All-or-nothing across both tables, not just within one."""
        _add_setting(engine, "etoro_api_key", _enc(APP_OLD, "healthy"))
        _add_provider(engine, "broken", _enc(THIRD_PARTY, "opaque", "FERN:"))

        assert rotate(commit=True, engine=engine) == 1

        assert _decrypts_to(_raw_setting(engine, "etoro_api_key"), APP_OLD, "ENC:") == "healthy"

    @pytest.mark.parametrize("missing", [
        "APP_SECRET_KEY", "APP_SECRET_KEY_NEW",
        "LLM_CREDENTIAL_KEY", "LLM_CREDENTIAL_KEY_NEW",
    ])
    def test_missing_key_refuses_to_run(self, engine, keys, monkeypatch, missing):
        monkeypatch.delenv(missing, raising=False)
        _add_setting(engine, "etoro_api_key", _enc(APP_OLD, "healthy"))

        with pytest.raises(RotationError, match=missing):
            rotate(commit=True, engine=engine)

    def test_identical_old_and_new_key_refuses_to_run(self, engine, keys, monkeypatch):
        """A no-op rotation that reports success would be worse than an error."""
        monkeypatch.setenv("APP_SECRET_KEY_NEW", APP_OLD)

        with pytest.raises(RotationError, match="identical"):
            rotate(commit=True, engine=engine)

    def test_malformed_key_refuses_to_run(self, engine, keys, monkeypatch):
        monkeypatch.setenv("APP_SECRET_KEY_NEW", "not-a-fernet-key")

        with pytest.raises(RotationError, match="not a valid Fernet key"):
            rotate(commit=True, engine=engine)


class TestNestedCiphertext:
    """
    ENC(FERN(key)) is real: prod's `settings.openrouter_api_key` holds one,
    and llm_config_chain.py:236-245 rejects it, so the value has been unused
    since 2026-07-11. Rotation must move BOTH layers without changing what
    the application does with the row.
    """

    def test_both_layers_are_rotated(self, engine, keys):
        inner = _enc(LLM_OLD, "sk-live-123", "FERN:")
        _add_setting(engine, "openrouter_api_key", _enc(APP_OLD, inner))

        assert rotate(commit=True, engine=engine) == 0

        outer = _decrypts_to(_raw_setting(engine, "openrouter_api_key"), APP_NEW, "ENC:")
        assert _decrypts_to(outer, LLM_NEW, "FERN:") == "sk-live-123"

    def test_the_retired_keys_open_neither_layer(self, engine, keys):
        """The whole point: no layer is left behind on a leaked key."""
        inner = _enc(LLM_OLD, "sk-live-123", "FERN:")
        _add_setting(engine, "openrouter_api_key", _enc(APP_OLD, inner))

        rotate(commit=True, engine=engine)

        stored = _raw_setting(engine, "openrouter_api_key")
        with pytest.raises(Exception):
            _decrypts_to(stored, APP_OLD, "ENC:")

        outer = _decrypts_to(stored, APP_NEW, "ENC:")
        with pytest.raises(Exception):
            _decrypts_to(outer, LLM_OLD, "FERN:")

    def test_nesting_shape_is_preserved_not_flattened(self, engine, keys):
        """
        Fully unwrapping would turn a value the app currently ignores into one
        it starts using — a behaviour change smuggled into a security fix.
        """
        inner = _enc(LLM_OLD, "sk-live-123", "FERN:")
        _add_setting(engine, "openrouter_api_key", _enc(APP_OLD, inner))

        rotate(commit=True, engine=engine)

        outer = _decrypts_to(_raw_setting(engine, "openrouter_api_key"), APP_NEW, "ENC:")
        assert outer.startswith("FERN:"), "inner layer was flattened away"

    def test_broken_inner_layer_aborts_the_batch(self, engine, keys):
        inner = _enc(THIRD_PARTY, "opaque", "FERN:")
        _add_setting(engine, "openrouter_api_key", _enc(APP_OLD, inner))
        _add_setting(engine, "etoro_api_key", _enc(APP_OLD, "healthy"))

        assert rotate(commit=True, engine=engine) == 1

        assert _decrypts_to(_raw_setting(engine, "etoro_api_key"), APP_OLD, "ENC:") == "healthy"


class TestValuesLeftAlone:
    def test_plaintext_setting_is_not_touched(self, engine, keys):
        """Rotation is not the place to start encrypting things."""
        _add_setting(engine, "etoro_api_base_url", "https://public-api.etoro.com")

        assert rotate(commit=True, engine=engine) == 0

        assert _raw_setting(engine, "etoro_api_base_url") == "https://public-api.etoro.com"

    def test_b64h_fallback_is_not_touched(self, engine, keys):
        """B64H: is keyless obfuscation — no key to rotate it onto."""
        _add_provider(engine, "legacy", "B64H:c2stbGl2ZQ==.deadbeef")

        assert rotate(commit=True, engine=engine) == 0

        assert _raw_provider(engine, "legacy") == "B64H:c2stbGl2ZQ==.deadbeef"

    def test_non_sensitive_key_name_is_still_rotated(self, engine, keys):
        """
        Selection is by value prefix, not key name. A row encrypted back when
        the name matched the sensitive patterns still holds a real ciphertext;
        skipping it would strand it on the retired key.
        """
        _add_setting(engine, "legacy_credential", _enc(APP_OLD, "still-a-secret"))

        assert rotate(commit=True, engine=engine) == 0

        assert _decrypts_to(_raw_setting(engine, "legacy_credential"), APP_NEW, "ENC:") \
            == "still-a-secret"


class TestJsonQuoting:
    def test_double_serialised_value_keeps_its_quotes(self, engine, keys):
        """
        Some rows store the JSON string '"ENC:..."', quotes included —
        `_decrypt` strips them (settings_repository.py:134). Rotation must
        read through the quotes and put them back, not quietly normalise the
        storage shape.
        """
        _add_setting(engine, "etoro_api_key", f'"{_enc(APP_OLD, "quoted-secret")}"')

        assert rotate(commit=True, engine=engine) == 0

        stored = _raw_setting(engine, "etoro_api_key")
        assert stored.startswith('"') and stored.endswith('"')
        assert _decrypts_to(stored[1:-1], APP_NEW, "ENC:") == "quoted-secret"

    def test_unquoted_value_does_not_gain_quotes(self, engine, keys):
        _add_setting(engine, "etoro_user_key", _enc(APP_OLD, "plain-shape"))

        rotate(commit=True, engine=engine)

        stored = _raw_setting(engine, "etoro_user_key")
        assert not stored.startswith('"')
