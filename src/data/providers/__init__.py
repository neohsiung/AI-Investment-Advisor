"""
Market data provider registry.

This file was EMPTY. Providers were discovered by nothing: market_data_service.py
imported all eight classes at module scope, constructed them one per line,
assigned each one's `.id` imperatively after construction, and then hand-ordered
four separate priority lists over those attributes.

Now the manifest (config/data_providers.yaml) declares them and this module
resolves it. Adding a provider is: write the class, add a manifest entry. No edit
to market_data_service, no fourth priority list to remember, and the credentials
and enable-switch become visible to the settings UI automatically.

本檔原本是空的：供應商沒有任何探索機制——market_data_service 在模組層匯入八個類別、
逐行建構、建構後才補指派 .id，然後手排四份獨立的優先序清單。
現在由 config/data_providers.yaml 宣告、本模組解析。
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.data.providers.base import MarketDataProvider
from src.plugins.registry import PluginError, Registry

logger = logging.getLogger(__name__)

_MANIFEST_ENV = "DATA_PROVIDERS_MANIFEST"
_DEFAULT_MANIFEST = "config/data_providers.yaml"

# Every registered implementation must satisfy MarketDataProvider — that check is
# what makes the manifest's dotted `class:` safe to import.
# 所有實作都必須滿足 MarketDataProvider；此檢查讓 manifest 的 dotted class 可安全匯入。
registry: Registry[MarketDataProvider] = Registry("data_providers", MarketDataProvider)

_lock = threading.Lock()
_specs: Dict[str, "ProviderSpec"] = {}
_mtime: Optional[float] = None

# Capabilities a provider may declare. A provider is only consulted for one it
# declares, so a typo here silently drops it from that route — hence the
# validation in _load().
# 供應商只會被用於它宣告過的 capability；拼錯會讓它靜默退出該路徑，故 _load() 會驗證。
CAPABILITIES = ("quote", "quote_batch", "history", "indicators", "news", "fundamentals")


@dataclass
class ProviderSpec:
    id: str
    class_path: str
    label: str = ""
    asset_classes: List[str] = field(default_factory=list)
    enabled_setting: Optional[str] = None
    credentials: List[str] = field(default_factory=list)
    capabilities: Dict[str, int] = field(default_factory=dict)
    needs_user_id: bool = False

    @property
    def equity_only(self) -> bool:
        """Replaces the EQUITY_ONLY_PROVIDER_IDS frozenset constant."""
        return self.asset_classes == ["equity"]


def manifest_path() -> Path:
    explicit = os.getenv(_MANIFEST_ENV)
    if explicit:
        return Path(explicit)
    return Path(__file__).resolve().parents[3] / _DEFAULT_MANIFEST


def _load(force: bool = False) -> Dict[str, ProviderSpec]:
    global _mtime
    path = manifest_path()
    if not path.exists():
        logger.error("data provider manifest missing at %s", path)
        return {}

    try:
        stat_mtime = path.stat().st_mtime
    except OSError:
        return dict(_specs)

    with _lock:
        if not force and _mtime == stat_mtime and _specs:
            return dict(_specs)

        import yaml

        raw = yaml.safe_load(path.read_text()) or {}
        specs: Dict[str, ProviderSpec] = {}
        for entry in raw.get("providers") or []:
            pid = entry.get("id")
            class_path = entry.get("class")
            if not pid or not class_path:
                logger.error("provider entry needs both `id` and `class`: %r", entry)
                continue

            caps = entry.get("capabilities") or {}
            unknown = set(caps) - set(CAPABILITIES)
            if unknown:
                # Rejected, not ignored: an unknown capability name would remove
                # the provider from the route the author meant to add it to,
                # while looking like a successful edit.
                # 未知的 capability 名稱會讓供應商從作者想加入的路徑中消失，
                # 卻看起來像編輯成功，故一律拒絕。
                logger.error(
                    "provider %s declares unknown capabilities %s (valid: %s) — skipped",
                    pid, sorted(unknown), ", ".join(CAPABILITIES),
                )
                continue

            specs[pid] = ProviderSpec(
                id=pid,
                class_path=class_path,
                label=entry.get("label", pid),
                asset_classes=list(entry.get("asset_classes") or []),
                enabled_setting=entry.get("enabled_setting"),
                credentials=list(entry.get("credentials") or []),
                capabilities={k: int(v) for k, v in caps.items()},
                needs_user_id=bool(entry.get("needs_user_id", False)),
            )

        _specs.clear()
        _specs.update(specs)
        _mtime = stat_mtime
        logger.info("loaded %d data provider specs", len(specs))
        return dict(_specs)


def list_specs(force: bool = False) -> List[ProviderSpec]:
    return list(_load(force=force).values())


def get_spec(provider_id: str) -> Optional[ProviderSpec]:
    return _load().get(provider_id)


def capability_order(capability: str) -> List[ProviderSpec]:
    """
    Specs declaring `capability`, in priority order (lower number first).

    Replaces four hand-ordered Python lists — one per capability — that had to be
    kept mutually consistent by hand.
    取代四份需人工維持一致的手排清單。
    """
    if capability not in CAPABILITIES:
        raise PluginError(
            f"unknown capability '{capability}' (valid: {', '.join(CAPABILITIES)})"
        )
    specs = [s for s in _load().values() if capability in s.capabilities]
    return sorted(specs, key=lambda s: (s.capabilities[capability], s.id))


def build(spec: ProviderSpec, *, settings_service: Any, user_id: Optional[str] = None) -> MarketDataProvider:
    """
    Instantiate one provider.

    `id` is set on the instance because the provider classes do not carry it
    themselves — that was true before this registry too (market_data_service
    assigned `.id` after construction). Doing it here means the id comes from the
    manifest rather than from a line of imperative code that could disagree with
    the priority lists.
    id 由 manifest 提供並在此設定（供應商類別本身不帶 id，這在本註冊表之前亦然），
    避免它由一行可能與優先序清單不一致的命令式程式碼決定。
    """
    cls = registry.try_get(spec.id)
    if cls is None:
        cls = registry.register_dotted(spec.id, spec.class_path)

    kwargs: Dict[str, Any] = {"settings_service": settings_service}
    if spec.needs_user_id:
        kwargs["user_id"] = user_id

    instance = cls(**kwargs)
    instance.id = spec.id
    return instance


def build_all(*, settings_service: Any, user_id: Optional[str] = None) -> Dict[str, MarketDataProvider]:
    """Every declared provider, keyed by id. Failures are logged, not fatal."""
    out: Dict[str, MarketDataProvider] = {}
    for spec in list_specs():
        try:
            out[spec.id] = build(spec, settings_service=settings_service, user_id=user_id)
        except Exception as exc:
            # One broken provider must not take the whole market data service
            # down — it degrades to the remaining providers in each chain.
            # 單一供應商壞掉不應讓整個行情服務停擺，會降級為其餘供應商。
            logger.error("could not construct provider %s: %s", spec.id, exc)
    return out
