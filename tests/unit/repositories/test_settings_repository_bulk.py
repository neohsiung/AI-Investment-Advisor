"""
Atomicity tests for AlchemySettingsRepository.set_many.
測試設定批次寫入的原子性。

Context (2026-08-02): SettingsService.save_settings_bulk looped over `set()`,
which commits per key. A mid-loop failure therefore left a partial write. The
keys written together include the eToro credential PAIR — and a half-rotated
pair (one key new, one key old) is exactly the state that took eToro sync down
on 2026-08-02. set_many() makes the write all-or-nothing.
"""
import pytest
from unittest.mock import patch

from sqlalchemy import create_engine, text

from src.repositories.settings_repository import AlchemySettingsRepository
from src.data.models import Base, Setting

USER = "00000000-0000-4000-a000-000000000001"


@pytest.fixture
def repo():
    """Repository bound to a fresh in-memory DB with the settings table."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[Setting.__table__])

    with patch('src.repositories.settings_repository.get_db_engine', return_value=engine):
        r = AlchemySettingsRepository()
    # _resolve_user rejects 'system'/None; bypass the users-table lookup here.
    r._resolve_user = lambda uid: uid
    r._engine_for_test = engine
    return r


def _raw(repo, key):
    with repo._engine_for_test.connect() as conn:
        row = conn.execute(
            text("SELECT value FROM settings WHERE user_id=:u AND key=:k"),
            {"u": USER, "k": key},
        ).fetchone()
    return row[0] if row else None


class TestSetManyHappyPath:

    def test_inserts_new_keys(self, repo):
        repo.set_many(USER, {"a": "1", "b": "2"})

        assert repo.get(USER, "a") == "1"
        assert repo.get(USER, "b") == "2"

    def test_updates_existing_without_duplicating(self, repo):
        repo.set(USER, "a", "old")
        repo.set_many(USER, {"a": "new", "b": "2"})

        assert repo.get(USER, "a") == "new"
        with repo._engine_for_test.connect() as conn:
            n = conn.execute(
                text("SELECT COUNT(*) FROM settings WHERE user_id=:u AND key='a'"), {"u": USER}
            ).scalar()
        assert n == 1

    def test_empty_dict_is_a_noop(self, repo):
        repo.set_many(USER, {})  # must not raise

        with repo._engine_for_test.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM settings")).scalar() == 0

    def test_storage_parity_with_set(self, repo):
        """
        set_many must store a sensitive key the same WAY as set().

        Compares the encrypted-or-not shape plus the decrypted round-trip, not
        raw bytes: Fernet embeds a random IV and timestamp, so two encryptions
        of the same plaintext never match byte-for-byte. And whether encryption
        happens at all depends on APP_SECRET_KEY being present, which differs
        between running this file alone and running the whole suite — so the
        assertion has to hold in both environments.
        比較「加密與否的形狀」與「解密後的值」，不比原始位元組：
        Fernet 含隨機 IV，同一明文兩次加密必然不同；且是否加密取決於 APP_SECRET_KEY，
        單跑此檔與跑全套時並不一致。
        """
        def is_enc(v):
            return str(v).strip('"').startswith("ENC:")

        repo.set(USER, "etoro_api_key", "opaque-key")
        repo.set_many(USER, {"etoro_user_key": "opaque-key"})

        assert is_enc(_raw(repo, "etoro_user_key")) == is_enc(_raw(repo, "etoro_api_key"))
        assert repo.get(USER, "etoro_user_key") == repo.get(USER, "etoro_api_key") == "opaque-key"

    def test_encrypt_is_applied_to_sensitive_keys_only(self, repo):
        """_should_encrypt must be consulted per key, same as set()."""
        seen = []
        repo._encrypt = lambda v: (seen.append(v), f"ENC:{v}")[1]

        repo.set_many(USER, {"etoro_api_key": "secret", "etoro_mode": "real"})

        assert seen == ["secret"], "encrypt applied to the wrong key set"
        assert str(_raw(repo, "etoro_mode")).strip('"') == "real"


class TestSetManyAtomicity:

    def test_credential_pair_is_all_or_nothing(self, repo):
        """
        The headline case: if the SECOND credential fails to encrypt, the FIRST
        must not be left written. A half-rotated pair is the 2026-08-02 outage.
        """
        real_encrypt = repo._encrypt
        calls = {"n": 0}

        def flaky_encrypt(value):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("cipher exploded on the second key")
            return real_encrypt(value)

        repo._encrypt = flaky_encrypt

        with pytest.raises(RuntimeError):
            repo.set_many(USER, {"etoro_api_key": "AAA", "etoro_user_key": "BBB"})

        assert _raw(repo, "etoro_api_key") is None, "partial write — first key leaked through"
        assert _raw(repo, "etoro_user_key") is None

    def test_failure_does_not_clobber_prior_values(self, repo):
        """A failed rotation must leave the previously-good pair intact."""
        repo.set_many(USER, {"etoro_api_key": "GOOD_A", "etoro_user_key": "GOOD_B"})

        real_encrypt = repo._encrypt
        calls = {"n": 0}

        def flaky_encrypt(value):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("boom")
            return real_encrypt(value)

        repo._encrypt = flaky_encrypt

        with pytest.raises(RuntimeError):
            repo.set_many(USER, {"etoro_api_key": "NEW_A", "etoro_user_key": "NEW_B"})

        assert repo.get(USER, "etoro_api_key") == "GOOD_A"
        assert repo.get(USER, "etoro_user_key") == "GOOD_B"

    def test_mixed_insert_and_update_rolls_back_together(self, repo):
        repo.set(USER, "existing", "before")

        real_encrypt = repo._encrypt

        def boom(value):
            raise RuntimeError("boom")

        # 'new_secret' is sensitive → hits _encrypt → raises mid-transaction.
        repo._encrypt = boom
        with pytest.raises(RuntimeError):
            repo.set_many(USER, {"existing": "after", "new_secret_api_key": "x"})

        repo._encrypt = real_encrypt
        assert repo.get(USER, "existing") == "before", "update was not rolled back"
        assert _raw(repo, "new_secret_api_key") is None


class TestInterfaceContract:

    def test_set_many_is_on_the_interface(self):
        """MagicMock(spec=ISettingsRepository) consumers need the attribute."""
        from src.repositories.settings_repository import ISettingsRepository

        assert hasattr(ISettingsRepository, "set_many")

    def test_service_has_no_silent_loop_fallback(self):
        """
        A hasattr()-guarded fallback to the per-key loop would silently restore
        the non-atomic path — the exact bug being removed.
        """
        import inspect
        from src.services.settings_service import SettingsService

        src = inspect.getsource(SettingsService.save_settings_bulk)
        assert "hasattr" not in src
        assert "set_many" in src
