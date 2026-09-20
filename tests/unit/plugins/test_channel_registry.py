"""
Notification channels as a manifest (M7-3).

`ChannelFactory.create_adapters` was seven near-identical if-blocks: each repeated
the same `is True or == "true"` enabled test, the same `str(... or "")` coercion
and the same try/except, and each needed a module-scope import so the block could
name its class. Adding a channel meant editing the factory.

What these tests hold:
  - the manifest is the only place a channel is declared, and every settings key
    it references exists in the settings schema (otherwise the key can never be
    saved — `save_settings_bulk` rejects unknown keys, which is how email's
    recipient address came to be unsettable)
  - credentials are typed `secret`, so `settings_repository` encrypts them at rest
  - Discord — added with a manifest entry and an adapter file only — proves the
    factory no longer has to change
  - one channel failing to construct still leaves the others delivering

本檔驗證：manifest 是宣告管道的唯一位置、其引用的設定鍵都存在於 schema（否則永遠無法儲存）、
憑證為 secret 型別（落地加密）、Discord 證明新增管道無須改動 factory、
單一管道建構失敗不影響其他管道送達。
"""
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from src.domain.interfaces import IChannelAdapter
from src.infrastructure.channels.channel_factory import ChannelFactory

REPO = Path(__file__).resolve().parents[3]
MANIFEST = REPO / "config" / "channels.yaml"
FACTORY = REPO / "src" / "infrastructure" / "channels" / "channel_factory.py"
SCHEMA = REPO / "config" / "settings_schema.yaml"


@pytest.fixture(autouse=True)
def _reset():
    ChannelFactory.reset()
    yield
    ChannelFactory.reset()


@pytest.fixture(scope="module")
def manifest():
    return yaml.safe_load(MANIFEST.read_text())


@pytest.fixture(scope="module")
def schema_keys():
    data = yaml.safe_load(SCHEMA.read_text())
    return {s["key"]: s for s in data["settings"]}


def _factory_source_without_comments():
    lines = []
    for line in FACTORY.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines)


class TestManifestShape:

    def test_every_channel_declares_id_and_class(self, manifest):
        for entry in manifest["channels"]:
            assert entry.get("id"), entry
            assert entry.get("class"), entry

    def test_ids_are_unique(self, manifest):
        ids = [c["id"] for c in manifest["channels"]]
        assert len(ids) == len(set(ids))

    def test_every_channel_is_gated_or_explicitly_always(self, manifest):
        """
        A channel with neither `enabled_setting` nor `always` would be declared
        but unreachable — silently dead, which is the failure mode this project
        treats as worse than a crash.
        既無 enabled_setting 也無 always 的管道會靜默無法啟用。
        """
        for entry in manifest["channels"]:
            assert entry.get("enabled_setting") or entry.get("always"), entry["id"]

    def test_only_the_event_log_is_always_on(self, manifest):
        always = [c["id"] for c in manifest["channels"] if c.get("always")]
        assert always == ["web"]

    def test_classes_resolve_to_channel_adapters(self, manifest):
        """The registry's subclass check is the reason a dotted path is safe."""
        registry = ChannelFactory._get_registry()
        for entry in manifest["channels"]:
            cls = registry.register_dotted(entry["id"], entry["class"])
            assert issubclass(cls, IChannelAdapter), entry["id"]


class TestSettingsKeysAreReachable:

    def test_every_referenced_key_exists_in_the_schema(self, manifest, schema_keys):
        """
        The bug this catches, found when writing it: `channel_email_to_address`
        was referenced by the factory but absent from the schema, so bulk save
        rejected it as unknown — email could be enabled but never given a
        recipient.
        """
        missing = []
        for entry in manifest["channels"]:
            keys = list((entry.get("args") or {}).values())
            if entry.get("enabled_setting"):
                keys.append(entry["enabled_setting"])
            missing += [k for k in keys if k not in schema_keys]
        assert missing == [], f"not settable through the UI: {missing}"

    def test_enabled_settings_are_boolean_and_default_off(self, manifest, schema_keys):
        for entry in manifest["channels"]:
            key = entry.get("enabled_setting")
            if not key:
                continue
            field = schema_keys[key]
            assert field["type"] == "bool", key
            assert field.get("default") in (False, None), key

    def test_credential_args_are_typed_secret(self, manifest, schema_keys):
        """
        `type: secret` is what drives encryption at rest. A token stored plaintext
        because its schema entry said `string` is a real leak, not a cosmetic one.
        secret 型別驅動落地加密；誤標 string 的 token 會以明文存放。
        """
        credential = re.compile(r"token|secret|pass|webhook_url|api_key", re.I)
        wrong = []
        for entry in manifest["channels"]:
            for key in (entry.get("args") or {}).values():
                if credential.search(key) and schema_keys[key]["type"] != "secret":
                    wrong.append(key)
        assert wrong == [], f"credentials not typed secret: {wrong}"

    def test_secret_typed_channel_keys_are_encrypted_by_the_repository(self, manifest, schema_keys):
        from src.repositories.settings_repository import AlchemySettingsRepository

        repo = AlchemySettingsRepository(engine=MagicMock())
        for entry in manifest["channels"]:
            for key in (entry.get("args") or {}).values():
                if schema_keys[key]["type"] == "secret":
                    assert repo._should_encrypt(key) is True, key


class TestFactoryIsNoLongerHandWritten:

    def test_no_per_channel_if_blocks_remain(self):
        source = _factory_source_without_comments()
        assert 'channel_line_enabled' not in source
        assert 'LineBotAdapter' not in source
        assert re.search(r'if parsed\.get\("channel_', source) is None

    def test_no_adapter_is_imported_at_module_scope(self):
        """
        Module-scope imports pulled in every channel's dependencies (the LINE SDK
        among them) even when no channel was enabled.
        """
        source = _factory_source_without_comments()
        module_imports = re.findall(
            r'^from src\.infrastructure\.channels\.\w+ import (\w+)', source, re.M
        )
        assert module_imports == []

    def test_adding_a_channel_needs_no_factory_edit(self, manifest):
        """
        Discord is the proof: it is reachable through the manifest alone, and the
        factory source does not mention it.
        """
        assert "discord" in [c["id"] for c in manifest["channels"]]
        assert "discord" not in _factory_source_without_comments().lower()


class TestConstruction:

    def test_nothing_enabled_yields_only_the_event_log(self):
        adapters = ChannelFactory.create_adapters({})
        assert [type(a).__name__ for a in adapters] == ["WebAdapter"]

    def test_bool_and_string_true_both_enable(self):
        for flag in (True, "true", "True", "TRUE"):
            ChannelFactory.reset()
            names = {type(a).__name__ for a in ChannelFactory.create_adapters(
                {"channel_discord_enabled": flag,
                 "channel_discord_webhook_url": "https://discord.com/api/webhooks/a/b"}
            )}
            assert "DiscordAdapter" in names, flag

    def test_falsy_values_do_not_enable(self):
        for flag in (False, "false", "", None, 0):
            ChannelFactory.reset()
            names = {type(a).__name__ for a in ChannelFactory.create_adapters(
                {"channel_discord_enabled": flag}
            )}
            assert "DiscordAdapter" not in names, flag

    def test_missing_args_become_empty_strings_not_none(self):
        """
        Adapters guard on falsiness, not on None. Passing None where the old code
        passed "" would flip `is_active()` in adapters that call `.strip()`.
        """
        adapters = ChannelFactory.create_adapters({"channel_discord_enabled": True})
        discord = [a for a in adapters if type(a).__name__ == "DiscordAdapter"][0]
        assert discord.webhook_url == ""
        # `is_active` is an attribute set in __init__, not a method.
        assert discord.is_active is False

    def test_email_port_keeps_its_587_default(self):
        """
        The one non-empty default in the old chain: `parsed.get(key, "587")`.
        EmailAdapter calls int() on the port, so dropping it turned a missing
        setting into a construction failure.
        舊程式碼唯一的非空預設；EmailAdapter 會對 port 呼叫 int()。
        """
        adapters = ChannelFactory.create_adapters({
            "channel_email_enabled": True,
            "channel_email_smtp_server": "smtp.example.com",
        })
        assert any(type(a).__name__ == "EmailAdapter" for a in adapters)

    def test_email_port_override_is_honoured(self):
        adapters = ChannelFactory.create_adapters({
            "channel_email_enabled": True,
            "channel_email_smtp_server": "smtp.example.com",
            "channel_email_smtp_port": "2525",
        })
        email = [a for a in adapters if type(a).__name__ == "EmailAdapter"][0]
        # EmailAdapter forwards the config into an EmailNotifier rather than
        # keeping it; the port is where the int() coercion happens.
        assert str(email.notifier.smtp_port) == "2525"

    def test_one_broken_channel_does_not_stop_the_others(self):
        from src.infrastructure.channels.telegram_adapter import TelegramAdapter

        settings = {
            "channel_telegram_enabled": True,
            "channel_discord_enabled": True,
            "channel_discord_webhook_url": "https://discord.com/api/webhooks/a/b",
        }
        with patch.object(TelegramAdapter, "__init__", side_effect=RuntimeError("boom")):
            names = {type(a).__name__ for a in ChannelFactory.create_adapters(settings)}
        assert "TelegramAdapter" not in names
        assert {"DiscordAdapter", "WebAdapter"} <= names

    def test_an_unresolvable_class_is_skipped_not_fatal(self, tmp_path, monkeypatch):
        bad = tmp_path / "channels.yaml"
        bad.write_text(
            "version: 1\nchannels:\n"
            "  - id: ghost\n    class: src.infrastructure.channels.nope.GhostAdapter\n"
            "    enabled_setting: channel_ghost_enabled\n"
            "  - id: web\n    class: src.infrastructure.channels.web_adapter.WebAdapter\n"
            "    always: true\n"
        )
        monkeypatch.setenv("CHANNELS_MANIFEST", str(bad))
        ChannelFactory.reset()
        adapters = ChannelFactory.create_adapters({"channel_ghost_enabled": True})
        assert [type(a).__name__ for a in adapters] == ["WebAdapter"]

    def test_a_non_adapter_class_is_refused(self, tmp_path, monkeypatch):
        """The manifest must not be a route to importing arbitrary callables."""
        bad = tmp_path / "channels.yaml"
        bad.write_text(
            "version: 1\nchannels:\n"
            "  - id: evil\n    class: os.system\n"
            "    enabled_setting: channel_evil_enabled\n"
        )
        monkeypatch.setenv("CHANNELS_MANIFEST", str(bad))
        ChannelFactory.reset()
        assert ChannelFactory.create_adapters({"channel_evil_enabled": True}) == []

    def test_a_missing_manifest_is_loud_and_non_fatal(self, tmp_path, monkeypatch, caplog):
        monkeypatch.setenv("CHANNELS_MANIFEST", str(tmp_path / "absent.yaml"))
        ChannelFactory.reset()
        with caplog.at_level("ERROR"):
            assert ChannelFactory.create_adapters({}) == []
        assert any("manifest missing" in r.message for r in caplog.records)


class TestHotReload:

    def test_manifest_changes_are_picked_up_without_a_restart(self, tmp_path, monkeypatch):
        path = tmp_path / "channels.yaml"
        path.write_text(
            "version: 1\nchannels:\n"
            "  - id: web\n    class: src.infrastructure.channels.web_adapter.WebAdapter\n"
            "    always: true\n"
        )
        monkeypatch.setenv("CHANNELS_MANIFEST", str(path))
        ChannelFactory.reset()
        assert len(ChannelFactory.create_adapters({})) == 1

        path.write_text(
            "version: 1\nchannels:\n"
            "  - id: web\n    class: src.infrastructure.channels.web_adapter.WebAdapter\n"
            "    always: true\n"
            "  - id: discord\n"
            "    class: src.infrastructure.channels.discord_adapter.DiscordAdapter\n"
            "    enabled_setting: channel_discord_enabled\n"
            "    args:\n      webhook_url: channel_discord_webhook_url\n"
        )
        # mtime granularity: force the reload the way a real edit seconds later would
        import os
        stat = path.stat()
        os.utime(path, (stat.st_atime, stat.st_mtime + 10))

        names = {type(a).__name__ for a in ChannelFactory.create_adapters(
            {"channel_discord_enabled": True,
             "channel_discord_webhook_url": "https://discord.com/api/webhooks/a/b"}
        )}
        assert "DiscordAdapter" in names


class TestDiscordAdapter:

    def test_it_is_a_channel_adapter(self):
        from src.infrastructure.channels.discord_adapter import DiscordAdapter

        assert issubclass(DiscordAdapter, IChannelAdapter)

    def test_signature_verification_fails_closed(self):
        """
        Discord webhooks are outbound only; there is no shared secret to verify an
        inbound request with. Returning True would let anything through.
        Discord webhook 僅單向外送，沒有可驗證入向請求的共享密鑰；回 True 等於全開。
        """
        from src.infrastructure.channels.discord_adapter import DiscordAdapter

        adapter = DiscordAdapter(webhook_url="https://discord.com/api/webhooks/a/b")
        assert adapter.verify_signature(b"{}", {"x-signature": "anything"}) is False

    def test_content_is_truncated_below_the_hard_limit(self):
        """
        Discord rejects a payload over 2000 chars outright rather than trimming it,
        so an over-long alert would not arrive truncated — it would not arrive.
        Discord 對超過 2000 字元的內容直接拒收（不是截斷），過長的警示不會截斷送達，是根本不會送達。
        """
        import asyncio
        from unittest.mock import AsyncMock

        from src.infrastructure.channels.discord_adapter import DiscordAdapter

        adapter = DiscordAdapter(webhook_url="https://discord.com/api/webhooks/a/b")
        captured = {}

        class _Response:
            status_code = 204
            text = ""

        class _Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def post(self, url, json=None):
                captured["payload"] = json
                return _Response()

        with patch("httpx.AsyncClient", lambda *a, **kw: _Client()):
            sent = asyncio.run(adapter.send_alert("u", "t" * 500, "x" * 5000))

        assert sent is True
        embed = captured["payload"]["embeds"][0]
        assert len(embed["description"]) < 2000
        assert len(embed["title"]) <= 256
