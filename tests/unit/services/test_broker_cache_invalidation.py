"""
Regression tests for BrokerFactory config-fingerprint cache invalidation.
測試 BrokerFactory 設定指紋快取失效機制。

Context (2026-08-02): BrokerFactory._instances was a process-lifetime dict with
no invalidation, so a credential or etoro_mode change never took effect until
the process restarted. In production this left the API process serving a broker
built before credentials existed, permanently falling back to the localhost
bridge. The cache entry now carries a fingerprint of the config it was built
from and is rebuilt whenever that config changes.
"""
import pytest
from unittest.mock import MagicMock, patch

from src.services.broker_factory import BrokerFactory


def _repo(values: dict) -> MagicMock:
    """Settings repo stub: two-positional-arg get(user_id, key)."""
    repo = MagicMock()
    repo.get.side_effect = lambda uid, key: values.get(key)
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

    def test_trading_mode_paper_override_changes_fingerprint(self):
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

    def test_fingerprint_does_not_store_credentials(self):
        """The cache must hold a hash, never the raw secret."""
        values = {"etoro_api_key": "super-secret-key", "etoro_user_key": "u", "etoro_mode": "demo"}
        with patch('src.services.broker_factory.AlchemySettingsRepository') as MockRepo, \
             patch('src.services.broker_factory.EtoroService') as MockEtoro:
            MockRepo.return_value = _repo(values)
            MockEtoro.side_effect = lambda **kw: MagicMock(name="broker")

            BrokerFactory.get_broker("u1", broker_type="etoro")
            fingerprint = BrokerFactory._instances["u1_etoro"][0]

            assert "super-secret-key" not in fingerprint
            assert len(fingerprint) == 64  # sha256 hexdigest
