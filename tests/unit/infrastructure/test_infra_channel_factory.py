"""
ChannelFactory behaviour.

These tests used to patch `channel_factory.LineBotAdapter` and five siblings,
because the factory imported every adapter class at module scope so its if-chain
could name them. The manifest-driven factory imports lazily through the plugin
registry, and that registry rejects anything that is not an `IChannelAdapter`
subclass — so a `MagicMock` patched over a class name is refused, by design.

The patches were never load-bearing anyway: every adapter constructor tolerates
empty credentials (LINE drops to mock mode, the rest just hold empty strings), so
the real classes can be built directly. Where a failure *is* the subject, it is
injected by making the real class's `__init__` raise, which keeps the registry's
type check satisfied.

原本的 patch 針對模組層匯入的類別；manifest 版改為經 registry 延遲匯入，
而 registry 會拒絕非 IChannelAdapter 子類（MagicMock 因此被拒——這是刻意設計）。
那些 patch 本來也非必要：所有適配器建構子都容許空憑證。
"""
import pytest
from unittest.mock import patch

from src.infrastructure.channels.channel_factory import ChannelFactory
from src.infrastructure.channels.web_adapter import WebAdapter


@pytest.fixture(autouse=True)
def _reset_factory_caches():
    """The registry caches classes process-wide; keep tests independent."""
    ChannelFactory.reset()
    yield
    ChannelFactory.reset()


def test_parse_setting():
    assert ChannelFactory._parse_setting("true") is True
    assert ChannelFactory._parse_setting("false") is False
    assert ChannelFactory._parse_setting('"hello"') == "hello"
    assert ChannelFactory._parse_setting("123") == 123
    assert ChannelFactory._parse_setting(None) is None
    assert ChannelFactory._parse_setting(42) == 42


def test_create_adapters_none_enabled():
    adapters = ChannelFactory.create_adapters({})

    # WebAdapter is `always: true` in the manifest — it feeds the dashboard event
    # log, so it is not gated on a setting.
    assert len(adapters) == 1
    assert isinstance(adapters[0], WebAdapter)


def test_create_adapters_all_enabled():
    settings = {
        "channel_line_enabled": "true",
        "channel_line_access_token": "token",
        "channel_slack_enabled": "true",
        "channel_telegram_enabled": "true",
        "channel_email_enabled": "true",
        "channel_messenger_enabled": "true",
        "channel_google_chat_enabled": "true",
    }

    adapters = ChannelFactory.create_adapters(settings)

    # Six enabled + the always-on WebAdapter. Discord is declared in the manifest
    # but not enabled here, which is the point: declaring a channel does not
    # activate it.
    assert len(adapters) == 7
    names = {type(a).__name__ for a in adapters}
    assert "DiscordAdapter" not in names


def test_create_adapters_with_errors():
    """One channel failing to construct must not cost the others their delivery."""
    from src.infrastructure.channels.line_adapter import LineBotAdapter

    settings = {"channel_line_enabled": "true", "channel_telegram_enabled": "true"}

    with patch.object(LineBotAdapter, "__init__", side_effect=Exception("Init Error")):
        adapters = ChannelFactory.create_adapters(settings)

    names = {type(a).__name__ for a in adapters}
    assert "LineBotAdapter" not in names
    assert "TelegramAdapter" in names
    assert "WebAdapter" in names
