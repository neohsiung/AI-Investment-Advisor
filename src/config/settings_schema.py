"""
Loader for config/settings_schema.yaml — the settings key registry.

This replaces three patterns that had all drifted:

  * a default re-declared at every read site (`target_cash_ratio` was read with
    0.1, 0.10 and 0.20 in four places);
  * encryption decided by regex-matching the key name, so a credential whose
    name lacked "key"/"token"/"secret" was stored in plaintext;
  * an untyped `Dict[str, Any]` passthrough on the save endpoint, which accepted
    any key with any value.

Deliberately NOT a pydantic model per key: the table also holds machine-written
rows (`alpha_spy_*` generated code, `cached_*`), so the registry has to describe
a known subset rather than close the world. `is_known()` is the seam — the HTTP
bulk-save path rejects unknown keys, while the internal single-key writer stays
permissive.

本模組取代三種已漂移的做法：各讀取點自帶預設值、用鍵名正則猜是否加密、
以及無型別的 Dict 直通儲存。刻意不為每個鍵建 pydantic model——同一張表還有
機器寫入的列，註冊表只描述已知子集。
"""
from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_SCHEMA_ENV = "SETTINGS_SCHEMA_PATH"
_DEFAULT_PATH = "config/settings_schema.yaml"

_lock = threading.Lock()
_cache: Optional["SettingsSchema"] = None
_cache_mtime: Optional[float] = None


class SettingsSchemaError(ValueError):
    """A value failed validation against its schema field."""


@dataclass(frozen=True)
class Group:
    id: str
    label_en: str
    label_zh: str = ""


@dataclass(frozen=True)
class Field:
    key: str
    group: str
    type: str
    default: Any = None
    label_en: str = ""
    label_zh: str = ""
    help_en: str = ""
    help_zh: str = ""
    enum: Optional[List[Any]] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    secret: bool = False
    danger: bool = False
    restart: bool = False
    depends: Optional[str] = None

    # ── validation ───────────────────────────────────────────────────────
    def coerce(self, value: Any) -> Any:
        """
        Coerce `value` to this field's type, or raise SettingsSchemaError.

        Coercion rather than strict typing because values arrive as JSON from a
        browser and as strings from the database's JSON column, so "true", true
        and 1 all legitimately mean the same thing for a bool.
        值可能來自瀏覽器 JSON 或資料庫 JSON 欄位，故採強制轉型而非嚴格型別。
        """
        t = self.type

        if value is None:
            return None

        try:
            if t == "bool":
                if isinstance(value, bool):
                    return value
                if isinstance(value, (int, float)):
                    return bool(value)
                s = str(value).strip().lower()
                if s in ("true", "1", "yes", "on"):
                    return True
                if s in ("false", "0", "no", "off", ""):
                    return False
                raise ValueError(f"not a boolean: {value!r}")

            if t == "int":
                v = int(float(value)) if not isinstance(value, bool) else int(value)
                self._check_range(v)
                return v

            if t == "float":
                v = float(value)
                self._check_range(v)
                return v

            if t == "enum":
                s = str(value)
                if self.enum and s not in [str(e) for e in self.enum]:
                    raise ValueError(f"must be one of {self.enum}, got {s!r}")
                return s

            if t in ("json", "list"):
                if isinstance(value, str):
                    try:
                        value = json.loads(value)
                    except json.JSONDecodeError as exc:
                        raise ValueError(f"not valid JSON: {exc}") from exc
                if t == "list" and not isinstance(value, list):
                    raise ValueError(f"expected a list, got {type(value).__name__}")
                if t == "json" and not isinstance(value, (dict, list)):
                    raise ValueError(f"expected an object or list, got {type(value).__name__}")
                return value

            if t == "time":
                s = str(value).strip()
                parts = s.split(":")
                if len(parts) != 2 or not all(p.isdigit() for p in parts):
                    raise ValueError(f"expected HH:MM, got {s!r}")
                hh, mm = int(parts[0]), int(parts[1])
                if not (0 <= hh <= 23 and 0 <= mm <= 59):
                    raise ValueError(f"not a valid time: {s!r}")
                return f"{hh:02d}:{mm:02d}"

            if t == "cron":
                s = str(value).strip()
                if len(s.split()) not in (5, 6):
                    raise ValueError(f"expected a 5- or 6-field cron expression, got {s!r}")
                return s

            # string | secret
            return str(value)

        except SettingsSchemaError:
            raise
        except (TypeError, ValueError) as exc:
            raise SettingsSchemaError(f"{self.key}: {exc}") from exc

    def _check_range(self, v: float) -> None:
        if self.minimum is not None and v < self.minimum:
            raise ValueError(f"must be >= {self.minimum}, got {v}")
        if self.maximum is not None and v > self.maximum:
            raise ValueError(f"must be <= {self.maximum}, got {v}")


@dataclass
class SettingsSchema:
    version: int
    groups: List[Group] = field(default_factory=list)
    fields: Dict[str, Field] = field(default_factory=dict)

    def get(self, key: str) -> Optional[Field]:
        return self.fields.get(key)

    def is_known(self, key: str) -> bool:
        return key in self.fields

    def default(self, key: str, fallback: Any = None) -> Any:
        f = self.fields.get(key)
        return f.default if f is not None else fallback

    def is_secret(self, key: str) -> bool:
        f = self.fields.get(key)
        return bool(f and f.secret)

    def coerce(self, key: str, value: Any) -> Any:
        f = self.fields.get(key)
        return f.coerce(value) if f else value

    def defaults(self) -> Dict[str, Any]:
        """Every key with a non-None default — the seed catalogue."""
        return {k: f.default for k, f in self.fields.items() if f.default is not None}

    def by_group(self) -> List[Dict[str, Any]]:
        """Groups in declaration order, each with its fields. Drives the UI."""
        out = []
        for g in self.groups:
            out.append({
                "id": g.id,
                "label_en": g.label_en,
                "label_zh": g.label_zh,
                "fields": [f for f in self.fields.values() if f.group == g.id],
            })
        return out


def _schema_path() -> Path:
    explicit = os.getenv(_SCHEMA_ENV)
    if explicit:
        return Path(explicit)
    here = Path(__file__).resolve()
    # src/config/settings_schema.py -> repo root
    return here.parents[2] / _DEFAULT_PATH


def _parse(raw: Dict[str, Any]) -> SettingsSchema:
    groups = [
        Group(id=g["id"], label_en=g.get("label_en", g["id"]), label_zh=g.get("label_zh", ""))
        for g in raw.get("groups", [])
    ]
    known_groups = {g.id for g in groups}

    fields: Dict[str, Field] = {}
    for entry in raw.get("settings", []):
        key = entry["key"]
        group = entry.get("group", "system")
        if group not in known_groups:
            raise SettingsSchemaError(f"{key}: unknown group {group!r}")
        ftype = entry.get("type", "string")
        fields[key] = Field(
            key=key,
            group=group,
            type=ftype,
            default=entry.get("default"),
            label_en=entry.get("label_en", key),
            label_zh=entry.get("label_zh", ""),
            help_en=entry.get("help_en", ""),
            help_zh=entry.get("help_zh", ""),
            enum=entry.get("enum"),
            minimum=entry.get("min"),
            maximum=entry.get("max"),
            secret=(ftype == "secret"),
            danger=bool(entry.get("danger", False)),
            restart=bool(entry.get("restart", False)),
            depends=entry.get("depends"),
        )
    return SettingsSchema(version=int(raw.get("version", 1)), groups=groups, fields=fields)


def load_schema(force: bool = False) -> SettingsSchema:
    """
    Parsed schema, cached and reloaded when the file's mtime changes.

    mtime-keyed rather than load-once so editing the YAML takes effect without
    restarting the API — the point of a low-code registry is that adding a knob
    does not need a deploy.
    以 mtime 快取：編輯 YAML 後無須重啟 API 即生效。
    """
    global _cache, _cache_mtime
    path = _schema_path()

    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = None

    with _lock:
        if _cache is not None and not force and mtime == _cache_mtime:
            return _cache

        if mtime is None:
            # A missing schema must not take the application down: every caller
            # degrades to "unknown key, no default", i.e. the old behaviour.
            # 缺少 schema 不應讓應用停擺，退回「未知鍵、無預設值」的舊行為。
            logger.error("settings schema not found at %s — running without it", path)
            _cache, _cache_mtime = SettingsSchema(version=0), None
            return _cache

        import yaml

        with path.open() as fh:
            raw = yaml.safe_load(fh) or {}
        _cache = _parse(raw)
        _cache_mtime = mtime
        logger.info(
            "settings schema loaded: %d fields in %d groups (v%d)",
            len(_cache.fields), len(_cache.groups), _cache.version,
        )
        return _cache


# ── module-level conveniences ────────────────────────────────────────────
def schema_default(key: str, fallback: Any = None) -> Any:
    return load_schema().default(key, fallback)


def is_secret_key(key: str) -> bool:
    return load_schema().is_secret(key)


def is_known_key(key: str) -> bool:
    return load_schema().is_known(key)


def coerce_value(key: str, value: Any) -> Any:
    return load_schema().coerce(key, value)
