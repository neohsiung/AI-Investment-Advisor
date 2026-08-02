"""
Regression tests for eToro credential handling.
測試 eToro 憑證對應與快取隔離。

Context (2026-08-02): two defects took eToro sync down.

1. A hardcoded `api_key.startswith("sdgdskld")` "mock credential" detector
   matched a REAL eToro Public API Key and nulled BOTH credentials, forcing the
   http://localhost:8000 bridge fallback and the self-deadlock guard. eToro
   issues opaque keys with arbitrary prefixes, so no prefix is a safe mock
   marker.
2. The portfolio cache was a CLASS attribute keyed by nothing, so demo/real
   instances — and different users — served each other's portfolios.

Header mapping was confirmed empirically against the live eToro API:
  x-api-key  <- etoro_api_key   (opaque key)
  x-user-key <- etoro_user_key  (JWT)
"""
import pytest
from unittest.mock import patch

from src.services.etoro_service import EtoroService


@pytest.fixture(autouse=True)
def _no_db(monkeypatch):
    """Keep EtoroService.__init__ off the DB/filesystem for these unit tests."""
    monkeypatch.setattr(EtoroService, "_load_credentials_from_db", lambda self, uid: None)
    monkeypatch.delenv("ETORO_API_KEY", raising=False)
    monkeypatch.delenv("ETORO_USER_KEY", raising=False)
    monkeypatch.delenv("ETORO_API_BASE_URL", raising=False)


class TestCredentialHeaderMapping:

    def test_headers_map_api_key_and_user_key_to_correct_slots(self):
        svc = EtoroService(api_key="OPAQUE-KEY", user_key="JWT-VALUE", mode="real")
        headers = svc._get_headers()

        assert headers["x-api-key"] == "OPAQUE-KEY"
        assert headers["x-user-key"] == "JWT-VALUE"
        assert "x-request-id" in headers

    def test_headers_strip_json_quoting(self):
        svc = EtoroService(api_key='"quoted-api"', user_key='"quoted-user"', mode="real")
        headers = svc._get_headers()

        assert headers["x-api-key"] == "quoted-api"
        assert headers["x-user-key"] == "quoted-user"


class TestPlaceholderDetection:

    def test_sdgdskld_prefix_is_no_longer_treated_as_mock(self):
        """
        The regression that caused the outage: a real eToro key beginning
        'sdgdskld' must be kept, not silently discarded.
        """
        svc = EtoroService(api_key="sdgdskldFPLG-real-key", user_key="jwt", mode="real")

        assert svc.api_key == "sdgdskldFPLG-real-key"
        assert svc.user_key == "jwt"
        assert svc.base_url == "https://public-api.etoro.com/api/v1"

    def test_explicit_placeholder_still_detected(self):
        svc = EtoroService(api_key="PLACEHOLDER-value", user_key="jwt", mode="real")

        assert svc.api_key is None
        assert svc.user_key is None
        assert svc.base_url == "http://localhost:8000"

    def test_absent_credentials_fall_back_to_local_bridge(self):
        svc = EtoroService(mode="real")

        assert svc.base_url == "http://localhost:8000"


class TestPortfolioCacheIsolation:

    def test_cache_is_per_instance_not_shared_across_instances(self):
        """
        demo and real instances must not share a portfolio cache — a class-level
        cache leaked demo data into real mode (and across users).
        """
        a = EtoroService(api_key="k1", user_key="u1", mode="demo")
        b = EtoroService(api_key="k2", user_key="u2", mode="real")

        a._cached_portfolio = {"clientPortfolio": {"credit": 111}}
        a._cached_time = 9_999_999_999.0

        assert b._cached_portfolio is None
        assert not hasattr(EtoroService, "_cached_portfolio")

    def test_fresh_instance_starts_with_empty_cache(self):
        svc = EtoroService(api_key="k", user_key="u", mode="real")

        assert svc._cached_portfolio is None
        assert svc._cached_time == 0.0
