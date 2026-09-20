import logging
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
from src.domain.interfaces import IChannelAdapter

# Adapter classes are NOT imported here any more. Each was imported at module
# scope purely so an if-block could name it, which meant importing every channel's
# dependencies (the LINE SDK, httpx clients) even when no channel was enabled.
# The registry imports each adapter lazily, only when its manifest entry is
# actually built.
# 原本在模組層匯入所有適配器，只為了讓 if 區塊能指名它們——這會在完全沒有啟用任何
# 管道時也匯入每個管道的相依（LINE SDK 等）。registry 改為在實際建構時才匯入。

logger = logging.getLogger(__name__)

class ChannelFactory:
    """
    Factory pattern for creating Channel Adapters.
    Centralizes instantiation logic and configuration injection.
    """
    
    @staticmethod
    def _parse_setting(value: typing.Any) -> typing.Any:
        """
        Parses a setting value from its string/JSON-quoted representation.
        Handles: "true" -> True, "false" -> False, '"string"' -> 'string', '123' -> 123.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            return value
            
        # Standardize boolean strings
        lower_val = value.strip().lower().strip('"').strip("'")
        if lower_val == "true":
            return True
        if lower_val == "false":
            return False
            
        # Attempt JSON decoding for quoted strings or numbers
        import json
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            # Fallback to the original string after stripping quotes
            if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                return value[1:-1]
            return value

    # ── manifest-driven construction ──────────────────────────────────
    _MANIFEST_ENV = "CHANNELS_MANIFEST"
    _DEFAULT_MANIFEST = "config/channels.yaml"
    _registry = None
    _specs = None
    _mtime = None

    @staticmethod
    def manifest_path():
        import os
        from pathlib import Path

        explicit = os.getenv(ChannelFactory._MANIFEST_ENV)
        if explicit:
            return Path(explicit)
        return Path(__file__).resolve().parents[3] / ChannelFactory._DEFAULT_MANIFEST

    @staticmethod
    def _load_specs(force: bool = False) -> typing.List[dict]:
        """
        Channel declarations from config/channels.yaml, cached on mtime.

        Reloaded when the file changes so adding a channel does not need a worker
        restart — matching how workflows, agents and the settings schema behave.
        以 mtime 快取並重載：新增管道無須重啟 worker，與 workflow/agent/設定 schema 一致。
        """
        path = ChannelFactory.manifest_path()
        if not path.exists():
            logger.error(f"ChannelFactory: manifest missing at {path}")
            return []
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return ChannelFactory._specs or []

        if not force and ChannelFactory._mtime == mtime and ChannelFactory._specs is not None:
            return ChannelFactory._specs

        import yaml

        raw = yaml.safe_load(path.read_text()) or {}
        specs = []
        for entry in raw.get("channels") or []:
            if not entry.get("id") or not entry.get("class"):
                logger.error(f"ChannelFactory: channel entry needs `id` and `class`: {entry!r}")
                continue
            specs.append(entry)
        ChannelFactory._specs = specs
        ChannelFactory._mtime = mtime
        logger.info(f"ChannelFactory: loaded {len(specs)} channel specs")
        return specs

    @staticmethod
    def _get_registry():
        from src.plugins.registry import Registry

        if ChannelFactory._registry is None:
            # The base-class requirement is what makes the manifest's dotted
            # `class:` safe to import — it cannot name something that is not a
            # channel adapter.
            # 基底類別要求讓 manifest 的 dotted class 可安全匯入。
            ChannelFactory._registry = Registry("channels", IChannelAdapter)
        return ChannelFactory._registry

    @staticmethod
    def _is_enabled(parsed: dict, spec: dict) -> bool:
        if spec.get("always"):
            return True
        key = spec.get("enabled_setting")
        if not key:
            return False
        value = parsed.get(key)
        # `_parse_setting` already coerces "true"/"false", but settings written by
        # older code paths can still arrive as raw strings, so both are accepted —
        # this is what every one of the seven if-blocks used to repeat inline.
        # 兩種形式都接受；這正是原本七段 if 區塊各自重複的判斷。
        return value is True or (isinstance(value, str) and value.strip().lower() == "true")

    @staticmethod
    def create_adapters(settings: typing.Dict[str, typing.Any]) -> typing.List[IChannelAdapter]:
        """
        Build every enabled adapter, driven by config/channels.yaml.

        This was ~90 lines of seven near-identical if-blocks, each repeating the
        same enabled-check, the same `str(parsed.get(...) or "")` coercion and the
        same try/except. Adding a channel required another block plus a
        module-scope import; now it requires a manifest entry and an adapter file.

        A channel that fails to construct is logged and skipped, exactly as before:
        one misconfigured channel must not stop the others from being notified.

        原本是約 90 行、七段幾乎相同的 if 區塊，各自重複同樣的啟用判斷、
        同樣的字串強制轉換與同樣的 try/except。新增管道現在只需 manifest 條目加檔案。
        建構失敗的管道會記錄並略過（與原本一致）：單一管道設定錯誤不應讓其他管道收不到通知。
        """
        parsed = {k: ChannelFactory._parse_setting(v) for k, v in settings.items()}
        registry = ChannelFactory._get_registry()
        adapters: typing.List[IChannelAdapter] = []

        specs = ChannelFactory._load_specs()
        enabled_ids = []

        for spec in specs:
            channel_id = spec["id"]
            if not ChannelFactory._is_enabled(parsed, spec):
                continue
            try:
                cls = registry.try_get(channel_id)
                if cls is None:
                    cls = registry.register_dotted(channel_id, spec["class"])

                kwargs = {}
                arg_map = spec.get("args") or {}
                # `defaults` preserves the one place the old chain differed from
                # "empty when unset": email's port fell back to "587", and
                # EmailAdapter calls int() on it, so a missing key crashed the
                # adapter rather than yielding a disabled one.
                # defaults 保留舊程式碼唯一的非空預設：email port 的 "587"。
                defaults = spec.get("defaults") or {}
                if spec.get("nested_arg"):
                    # One adapter (email) takes a single config dict. Values are
                    # passed through un-stringified, as the old block did — the
                    # port must survive as something int() accepts.
                    kwargs[spec["nested_arg"]] = {
                        name: parsed.get(key, defaults.get(name)) if parsed.get(key) is not None
                        else defaults.get(name)
                        for name, key in arg_map.items()
                    }
                else:
                    for name, key in arg_map.items():
                        value = parsed.get(key)
                        if value is None:
                            value = defaults.get(name)
                        kwargs[name] = str(value or "")

                adapters.append(cls(**kwargs))
                enabled_ids.append(channel_id)
            except Exception as exc:
                logger.error(f"Failed to initialize {channel_id} adapter: {exc}")

        logger.info(
            f"ChannelFactory: built {len(adapters)} adapter(s) from {len(specs)} "
            f"declared channel(s): {', '.join(enabled_ids) or 'none'}"
        )
        return adapters

    @staticmethod
    def reset() -> None:
        """
        Drop the manifest and class caches.

        The registry caches each adapter class after the first build, which is
        right in production (the class never changes) but means a test patching
        `module.XAdapter` after a previous test already resolved it would silently
        get the real class. Tests that patch adapter classes must call this.
        registry 會快取適配器類別（生產環境正確），但測試若在別的測試已解析後才 patch
        模組屬性，會靜默拿到真實類別；需要 patch 的測試必須先呼叫本方法。
        """
        ChannelFactory._specs = None
        ChannelFactory._mtime = None
        if ChannelFactory._registry is not None:
            ChannelFactory._registry.clear()

    @staticmethod
    def declared_channels() -> typing.List[dict]:
        """Manifest entries, for the extensions UI."""
        return list(ChannelFactory._load_specs())
