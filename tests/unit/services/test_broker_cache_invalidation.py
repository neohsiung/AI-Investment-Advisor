"""
Regression tests for BrokerFactory change-token cache invalidation.
測試 BrokerFactory 變更權杖快取失效機制。

Context (2026-08-02): BrokerFactory._instances was a process-lifetime dict with
no invalidation, so a credential or etoro_mode change never took effect until
the process restarted. In production this left the API process serving a broker
built before credentials existed, permanently falling back to the localhost
bridge. The cache entry now carries a token derived from the config it was
built from and is rebuilt whenever that config changes.

The token deliberately does NOT contain the credentials — it uses the
`settings.updated_at` of the rows holding them, so no secret is ever hashed
(see BrokerFactory._change_token). The repo stub below therefore has to model
that timestamp, not just the value.
"""
from datetime import datetime, timedelta, timezone

import pytest
from unittest.mock import MagicMock, patch

from src.services.broker_factory import BrokerFactory

_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _repo(values: dict) -> MagicMock:
    """
    Settings repo stub modelling both access paths.

    `get_many_with_meta` returns (value, updated_at) per key. The stamp is
    bumped whenever a value changes, which is exactly what `Setting.updated_at`
    does in production via `onupdate=func.now()` — tests can keep mutating the
    plain `values` dict and the timestamps follow.

    模擬 settings 表兩種存取路徑；值一變就 bump 時間戳，與 production 的
    `onupdate=func.now()` 行為一致，測試仍可直接改 values dict。
    """
    repo = MagicMock()
    seen: dict = {}
    ticks: dict = {}

    def _meta(uid, keys):
        out = {}
        for key in keys:
            value = values.get(key)
            if key not in seen:
                seen[key] = value
                ticks[key] = 0
            elif seen[key] != value:
                seen[key] = value
                ticks[key] += 1
            stamp = None if value is None else _EPOCH + timedelta(minutes=ticks[key])
            out[key] = (value, stamp)
        return out

    repo.get.side_effect = lambda uid, key: values.get(key)
    repo.get_many_with_meta.side_effect = _meta
    return repo


class TestBrokerCacheInvalidation:

    def setup_method(self):
        BrokerFactory._instances.clear()

    def teardown_method(self):
        BrokerFactory._instances.clear()

    def test_same_config_is_cached(self):
        """Unchanged config must reuse the cached instance (no rebuild)."""
        values = {"etoro_api_key": "key-a", "etoro_user_key": "user-a", "etoro_mode": "demo"}
        with patch('src.services.broker_factory.AlchemySettingsRepository') as MockRepo, \
             patch('src.services.broker_factory.EtoroService') as MockEtoro:
            MockRepo.return_value = _repo(values)
            MockEtoro.side_effect = lambda **kw: MagicMock(name="broker")

            first = BrokerFactory.get_broker("u1", broker_type="etoro")
            second = BrokerFactory.get_broker("u1", broker_type="etoro")

            assert first is second
            assert MockEtoro.call_count == 1

    def test_credential_change_rebuilds_instance(self):
        """Changing etoro_api_key must invalidate — this is the prod bug."""
        values = {"etoro_api_key": "key-a", "etoro_user_key": "user-a", "etoro_mode": "demo"}
        with patch('src.services.broker_factory.AlchemySettingsRepository') as MockRepo, \
             patch('src.services.broker_factory.EtoroService') as MockEtoro:
            MockRepo.return_value = _repo(values)
            MockEtoro.side_effect = lambda **kw: MagicMock(name="broker")

            first = BrokerFactory.get_broker("u1", broker_type="etoro")
            values["etoro_api_key"] = "key-b"          # credential rotated
            second = BrokerFactory.get_broker("u1", broker_type="etoro")

            assert first is not second
            assert MockEtoro.call_count == 2

    def test_mode_change_rebuilds_instance(self):
        """demo -> real must not be served from a stale cache entry."""
        values = {"etoro_api_key": "k", "etoro_user_key": "u", "etoro_mode": "demo"}
        with patch('src.services.broker_factory.AlchemySettingsRepository') as MockRepo, \
             patch('src.services.broker_factory.EtoroService') as MockEtoro:
            MockRepo.return_value = _repo(values)
            MockEtoro.side_effect = lambda **kw: MagicMock(name="broker")

            BrokerFactory.get_broker("u1", broker_type="etoro")
            values["etoro_mode"] = "real"
            BrokerFactory.get_broker("u1", broker_type="etoro")

            assert MockEtoro.call_count == 2
            assert MockEtoro.call_args_list[0].kwargs["mode"] == "demo"
            assert MockEtoro.call_args_list[1].kwargs["mode"] == "real"

    def test_trading_mode_paper_override_changes_token(self):
        """Flipping TRADING_MODE=paper must invalidate a real-mode entry."""
        values = {"etoro_api_key": "k", "etoro_user_key": "u", "etoro_mode": "real"}
        with patch('src.services.broker_factory.AlchemySettingsRepository') as MockRepo, \
             patch('src.services.broker_factory.EtoroService') as MockEtoro:
            MockRepo.return_value = _repo(values)
            MockEtoro.side_effect = lambda **kw: MagicMock(name="broker")

            with patch.dict('os.environ', {}, clear=False):
                import os
                os.environ.pop("TRADING_MODE", None)
                BrokerFactory.get_broker("u1", broker_type="etoro")
            with patch.dict('os.environ', {"TRADING_MODE": "paper"}):
                BrokerFactory.get_broker("u1", broker_type="etoro")

            assert MockEtoro.call_count == 2
            assert MockEtoro.call_args_list[0].kwargs["mode"] == "real"
            assert MockEtoro.call_args_list[1].kwargs["mode"] == "demo"

    def test_missing_etoro_mode_defaults_to_demo(self):
        """Fail-safe: an absent etoro_mode must never mean live money."""
        with patch('src.services.broker_factory.AlchemySettingsRepository') as MockRepo, \
             patch('src.services.broker_factory.EtoroService') as MockEtoro:
            MockRepo.return_value = _repo({"etoro_api_key": "k", "etoro_user_key": "u"})
            MockEtoro.side_effect = lambda **kw: MagicMock(name="broker")

            BrokerFactory.get_broker("u1", broker_type="etoro")

            assert MockEtoro.call_args.kwargs["mode"] == "demo"

    def test_invalidate_clears_matching_slots_only(self):
        values = {"etoro_api_key": "k", "etoro_user_key": "u", "etoro_mode": "demo"}
        with patch('src.services.broker_factory.AlchemySettingsRepository') as MockRepo, \
             patch('src.services.broker_factory.EtoroService') as MockEtoro:
            MockRepo.return_value = _repo(values)
            MockEtoro.side_effect = lambda **kw: MagicMock(name="broker")

            BrokerFactory.get_broker("u1", broker_type="etoro")
            BrokerFactory.get_broker("u2", broker_type="etoro")
            assert len(BrokerFactory._instances) == 2

            removed = BrokerFactory.invalidate(user_id="u1")

            assert removed == 1
            assert "u1_etoro" not in BrokerFactory._instances
            assert "u2_etoro" in BrokerFactory._instances

    def test_cache_key_format_preserved(self):
        """Existing tests/consumers rely on the '<user>_<broker>' key format."""
        values = {"etoro_api_key": "k", "etoro_user_key": "u", "etoro_mode": "demo"}
        with patch('src.services.broker_factory.AlchemySettingsRepository') as MockRepo, \
             patch('src.services.broker_factory.EtoroService') as MockEtoro:
            MockRepo.return_value = _repo(values)
            MockEtoro.side_effect = lambda **kw: MagicMock(name="broker")

            BrokerFactory.get_broker("test_user", broker_type="etoro")

            assert "test_user_etoro" in BrokerFactory._instances

    def test_cache_does_not_grow_on_repeated_rotation(self):
        """One slot per (user, broker) — rotations must not leak entries."""
        values = {"etoro_api_key": "k0", "etoro_user_key": "u", "etoro_mode": "demo"}
        with patch('src.services.broker_factory.AlchemySettingsRepository') as MockRepo, \
             patch('src.services.broker_factory.EtoroService') as MockEtoro:
            MockRepo.return_value = _repo(values)
            MockEtoro.side_effect = lambda **kw: MagicMock(name="broker")

            for i in range(5):
                values["etoro_api_key"] = f"k{i}"
                BrokerFactory.get_broker("u1", broker_type="etoro")

            assert len(BrokerFactory._instances) == 1

    def test_change_token_is_not_derived_from_credentials(self):
        """
        The token must contain neither the raw secret nor any digest of it.

        2026-08-02: this used to assert the token WAS a sha256 hexdigest of the
        config. Hashing a credential — even only to compare, never to store —
        is the pattern static analysis flags (py/weak-sensitive-data-hashing),
        so the token is now built from settings.updated_at instead. The
        property under test got stronger, not weaker: previously the secret was
        merely unreadable in the token, now it never enters it at all.
        現在斷言更強：秘密不只是「在權杖裡讀不出來」，而是根本沒進去過。
        """
        import hashlib

        secret = "super-secret-key"
        values = {"etoro_api_key": secret, "etoro_user_key": "u", "etoro_mode": "demo"}
        with patch('src.services.broker_factory.AlchemySettingsRepository') as MockRepo, \
             patch('src.services.broker_factory.EtoroService') as MockEtoro:
            MockRepo.return_value = _repo(values)
            MockEtoro.side_effect = lambda **kw: MagicMock(name="broker")

            BrokerFactory.get_broker("u1", broker_type="etoro")
            token = BrokerFactory._instances["u1_etoro"][0]

            assert secret not in token
            # Nor any digest of it — the token must not be a hash of the secret
            # under any common algorithm, truncated or otherwise.
            for algo in ("md5", "sha1", "sha256", "sha512"):
                digest = hashlib.new(algo, secret.encode()).hexdigest()
                assert digest[:8] not in token
            # It must still carry the invalidation signal: the key's timestamp.
            assert "etoro_api_key@" in token
