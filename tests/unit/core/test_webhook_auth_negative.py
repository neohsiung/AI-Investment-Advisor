"""
Negative-path tests for webhook X-API-Key authentication.
測試 webhook X-API-Key 認證的失敗路徑。

Context (2026-08-02): a live 403 storm went undiagnosed because coverage here
was effectively absent — test_heartbeat_webhook asserts
`status_code in (200, 401)`, which passes whether auth works or not. The actual
cause was one n8n node still carrying a 17-char 'your_api_key_here' placeholder
while the other three had the real key.

These lock the contract: missing header -> 401, wrong key -> 403, right key ->
resolves. They also cover the fingerprint diagnostic, which must never log the
secret itself.
"""
import pytest
from unittest.mock import MagicMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.services.webhook_service import webhook_router, WebhookService

app = FastAPI()
app.include_router(webhook_router, prefix="/webhook")
client = TestClient(app)


class TestWebhookAuthStatusCodes:

    def test_missing_api_key_returns_401(self):
        response = client.get("/webhook/rss-sources")
        assert response.status_code == 401

    def test_wrong_api_key_returns_403(self):
        with patch.object(WebhookService, 'settings_service', create=True) as mock_settings:
            mock_settings.find_user_by_webhook_secret.return_value = None
            response = client.get("/webhook/rss-sources", headers={"X-API-Key": "wrong-key"})
        assert response.status_code == 403

    def test_401_and_403_are_distinguishable(self):
        """Missing and invalid must not collapse to the same code — the whole
        point of the diagnostic is telling 'no key sent' from 'wrong key'."""
        missing = client.get("/webhook/rss-sources")
        with patch.object(WebhookService, 'settings_service', create=True) as mock_settings:
            mock_settings.find_user_by_webhook_secret.return_value = None
            wrong = client.get("/webhook/rss-sources", headers={"X-API-Key": "nope"})

        assert missing.status_code == 401
        assert wrong.status_code == 403

    def test_valid_api_key_resolves_user(self):
        with patch('src.services.webhook_service.WebhookService._resolve_user',
                   return_value="test_user") as mock_resolve:
            mock_resolve.side_effect = None
            with patch('src.services.webhook_service.WebhookService._resolve_user',
                       new=_async_return("test_user")):
                response = client.get("/webhook/rss-sources", headers={"X-API-Key": "correct"})
        assert response.status_code == 200


def _async_return(value):
    async def _inner(self, request):
        return value
    return _inner


class TestWebhookSecretDiagnostic:
    """The mismatch diagnostic must be useful AND must not leak the secret."""

    @staticmethod
    def _repo(rows, decrypted):
        """
        Build a repository whose `session` property (read-only on
        BaseRepository) is stubbed to return canned rows.
        """
        from src.repositories.settings_repository import AlchemySettingsRepository

        session = MagicMock()
        session.execute.return_value.fetchall.return_value = rows

        class _Stub(AlchemySettingsRepository):
            session = property(lambda self: session)

            def close_session(self):
                pass

            def _decrypt(self, value):
                return decrypted

        repo = _Stub.__new__(_Stub)
        return repo

    def test_mismatch_logs_lengths_not_secret_or_digest(self, caplog):
        """
        The diagnostic must reveal neither the secret nor a digest of it.

        2026-08-02: this used to log a truncated SHA-256 as `fp=`. It carried
        no diagnostic value the length and `still_enc` flag don't already give,
        and running a secret through a fast hash is the pattern static analysis
        flags (py/weak-sensitive-data-hashing) — so it was removed rather than
        suppressed. Asserting the digest's absence keeps it removed.
        原本會記錄截斷 SHA-256；那對診斷沒有貢獻，且把秘密送進快速雜湊會被靜態
        分析標記，故直接移除而非抑制。這裡斷言雜湊確實不再出現。
        """
        import hashlib

        presented = "the-presented-secret"
        stored = "the-real-stored-secret"
        repo = self._repo([("user-1", "ENC:stored")], stored)

        with caplog.at_level("WARNING"):
            result = repo.find_user_by_webhook_secret(presented)

        assert result is None
        logged = caplog.text
        assert presented not in logged
        assert stored not in logged
        for value in (presented, stored):
            for algo in ("md5", "sha1", "sha256", "sha512"):
                assert hashlib.new(algo, value.encode()).hexdigest()[:8] not in logged
        # The signal an operator actually needs is still there.
        assert "candidates=" in logged
        assert f"presented(len={len(presented)})" in logged
        assert f"len={len(stored)}" in logged
        assert "still_enc=" in logged

    def test_diagnostic_flags_undecrypted_ciphertext(self, caplog):
        """still_enc=True is the APP_SECRET_KEY-rotation signature."""
        # decrypt failed and returned the raw ciphertext
        repo = self._repo([("user-1", "ENC:blob")], "ENC:blob")

        with caplog.at_level("WARNING"):
            repo.find_user_by_webhook_secret("anything")

        assert "still_enc=True" in caplog.text

    def test_matching_secret_returns_user_and_logs_nothing(self, caplog):
        repo = self._repo([("user-1", "ENC:stored")], "shared-secret")

        with caplog.at_level("WARNING"):
            result = repo.find_user_by_webhook_secret("shared-secret")

        assert result == "user-1"
        assert "mismatch" not in caplog.text

    def test_no_rows_reported_as_zero_candidates(self, caplog):
        repo = self._repo([], None)

        with caplog.at_level("WARNING"):
            result = repo.find_user_by_webhook_secret("anything")

        assert result is None
        assert "candidates=0" in caplog.text
