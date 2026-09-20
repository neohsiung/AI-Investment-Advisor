"""
One registry mechanism for the project's extension points.

Three variants of this existed, each solving the same problem differently:

  * `src/data/ingestors/factory.py` — a `@register_ingestor("name")` decorator over
    a module-level dict, populated by importing a `strategies` module lazily.
  * `src/infrastructure/llm/provider_catalog.py` — YAML entries carrying a dotted
    `gateway_class`, resolved with importlib and checked against a base class.
  * `src/infrastructure/channels/channel_factory.py` and
    `src/services/market_data_service.py` — no registry at all: an if/elif chain
    and a list of hand-instantiated imports respectively.

This module keeps both good ideas and drops the fourth approach:

  DECORATOR for code shipped with the application. The class is in the repo, so
  naming it in a manifest adds nothing.

  DOTTED PATH for manifests, resolved through importlib and REQUIRED to subclass a
  declared base. That check is what makes a dotted path acceptable: a manifest
  cannot name `os.system` and have it accepted as a data provider.

Manifests for these registries are NOT UI-editable (unlike workflows and agents),
so a dotted path is a smaller exposure here — but the base-class check is enforced
regardless, because "not editable today" is not a security property.

專案原本有三種版本的同一個機制（decorator 註冊、YAML dotted path + importlib、
以及完全沒有註冊表的 if/elif 與手動 import 清單）。本模組保留前兩者：
隨應用出貨的類別用 decorator；manifest 用 dotted path，但強制要求繼承宣告的基底類別
——這個檢查才是 dotted path 可被接受的原因（manifest 無法把 os.system 當成資料源）。
"""
from __future__ import annotations

import importlib
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Generic, List, Optional, Type, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class PluginError(ValueError):
    """A plugin could not be registered or resolved."""


@dataclass
class Registry(Generic[T]):
    """
    A named collection of implementations of one interface.

    `base` is the interface every implementation must satisfy. It is not optional
    by design — without it, `resolve_dotted` would accept any importable callable.
    base 為必填：少了它，resolve_dotted 會接受任何可匯入的物件。
    """

    name: str
    base: Type[T]
    _impls: Dict[str, Type[T]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    # ── registration ──────────────────────────────────────────────────
    def register(self, key: str) -> Callable[[Type[T]], Type[T]]:
        """Decorator form, for implementations shipped in this repository."""
        def decorator(cls: Type[T]) -> Type[T]:
            self.add(key, cls)
            return cls
        return decorator

    def add(self, key: str, cls: Type[T]) -> None:
        normalised = key.strip().lower()
        if not issubclass(cls, self.base):
            raise PluginError(
                f"{self.name}: {cls.__module__}.{cls.__qualname__} must subclass "
                f"{self.base.__name__} to be registered as '{normalised}'"
            )
        with self._lock:
            existing = self._impls.get(normalised)
            if existing is not None and existing is not cls:
                raise PluginError(
                    f"{self.name}: '{normalised}' is already registered to "
                    f"{existing.__module__}.{existing.__qualname__}"
                )
            self._impls[normalised] = cls

    def resolve_dotted(self, path: str, key: str = "") -> Type[T]:
        """
        Import `path` ("pkg.module.ClassName") and verify it satisfies `base`.

        The base-class check is the security boundary. Without it a manifest could
        name any importable object and this would hand it back to be constructed.
        基底類別檢查即為安全邊界；少了它，manifest 可指名任何可匯入物件並被建構。
        """
        module_path, _, class_name = path.rpartition(".")
        if not module_path or not class_name:
            raise PluginError(
                f"{self.name}: '{path}' is not a dotted class path "
                f"(expected 'package.module.ClassName')"
            )
        try:
            module = importlib.import_module(module_path)
        except ImportError as exc:
            raise PluginError(
                f"{self.name}: cannot import {module_path} for '{key or path}': {exc}"
            ) from exc

        cls = getattr(module, class_name, None)
        if cls is None:
            raise PluginError(f"{self.name}: {class_name} not found in {module_path}")
        if not isinstance(cls, type) or not issubclass(cls, self.base):
            raise PluginError(
                f"{self.name}: {path} must be a class subclassing {self.base.__name__}"
            )
        return cls

    def register_dotted(self, key: str, path: str) -> Type[T]:
        """Resolve a dotted path and register the result."""
        cls = self.resolve_dotted(path, key=key)
        self.add(key, cls)
        return cls

    # ── lookup ────────────────────────────────────────────────────────
    def get(self, key: str) -> Type[T]:
        normalised = str(key).strip().lower()
        cls = self._impls.get(normalised)
        if cls is None:
            raise PluginError(
                f"{self.name}: unknown '{key}'. Registered: "
                f"{', '.join(sorted(self._impls)) or '(none)'}"
            )
        return cls

    def try_get(self, key: str) -> Optional[Type[T]]:
        return self._impls.get(str(key).strip().lower())

    def has(self, key: str) -> bool:
        return str(key).strip().lower() in self._impls

    def keys(self) -> List[str]:
        return sorted(self._impls)

    def items(self) -> List[tuple]:
        return sorted(self._impls.items())

    def create(self, key: str, *args, **kwargs) -> T:
        return self.get(key)(*args, **kwargs)

    def clear(self) -> None:
        """For tests only."""
        with self._lock:
            self._impls.clear()
