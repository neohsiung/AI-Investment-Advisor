"""
Wisdom Vault — File-Based Semantic Cold Storage (Tier 3).
智慧金庫 — 基於檔案的語意冷存儲（第三層）。

Stores crystallized wisdom as YAML-frontmatter Markdown files,
mirroring the Persona/Skill file convention.

Cognitive mapping:
  - Human brain: Neocortex (語意記憶 / semantic memory)
  - DIKW: Wisdom layer — abstract principles distilled from experience
  - Kahneman: System 2 結晶 — 不再需要思考的深層知識

Storage layout:
  data/wisdom/{user_id}/
    ├── risk_profile.md       # 風險偏好
    ├── market_patterns.md    # 市場觀察模式
    ├── decision_habits.md    # 決策行為模式
    ├── ticker_insights.md    # 個股累積洞察
    └── meta.yaml             # 索引 + 統計

遵循規範:
  - 規範一 (Clean Architecture): 純檔案 I/O，無 DB 依賴
  - 規範四 (模組化設計): 可獨立替換為 S3 adapter
  - 規範十五 (AI-Support First): YAML + MD 格式 Agent 可直讀
"""

import os
import yaml
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Default Configuration ────────────────────────────────
WISDOM_BASE_PATH = os.getenv(
    "WISDOM_VAULT_PATH",
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "wisdom"),
)

# Predefined wisdom categories (maps to file names)
WISDOM_CATEGORIES = [
    "risk_profile",       # 風險偏好特徵
    "market_patterns",    # 市場觀察模式
    "decision_habits",    # 決策行為模式
    "ticker_insights",    # 個股累積洞察
    "conversation_style", # 對話偏好
    "tone_preference",    # 語氣偏好 (簡潔 vs 詳細)
    "reporting_style",    # 回報格式偏好 (表格 vs 敘述)
    "capability_gaps",    # [Phase 4] 能力缺口記錄
]


@dataclass
class WisdomEntry:
    """
    A single wisdom principle with metadata.
    單一智慧原則及其元資料。
    """
    category: str
    principle: str                    # The wisdom text itself
    confidence: float = 0.5           # 0.0 ~ 1.0
    evidence_count: int = 0           # How many episodes back this up
    tags: List[str] = field(default_factory=list)
    last_updated: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d")
    )
    source_episodes: List[str] = field(default_factory=list)  # episode IDs

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WisdomFile:
    """
    A parsed wisdom file (YAML frontmatter + Markdown body).
    已解析的智慧檔案（YAML 前言 + Markdown 主體）。
    """
    category: str
    entries: List[WisdomEntry] = field(default_factory=list)
    last_updated: str = ""
    total_evidence: int = 0

    @property
    def body_text(self) -> str:
        """Render entries as markdown bullet points."""
        if not self.entries:
            return ""
        lines = []
        for e in self.entries:
            conf_bar = "●" * int(e.confidence * 5) + "○" * (5 - int(e.confidence * 5))
            lines.append(
                f"- [{conf_bar}] {e.principle} "
                f"(evidence: {e.evidence_count})"
            )
        return "\n".join(lines)


class WisdomVault:
    """
    File-based semantic wisdom storage.
    基於檔案的語意智慧存儲。

    Each user gets a directory under base_path.
    Each category is a separate .md file with YAML frontmatter.

    Usage:
        vault = WisdomVault()
        vault.store_wisdom("user1", "risk_profile", "偏好 VIX > 25 時減碼 20%", 0.8)
        principles = vault.load_wisdom("user1", categories=["risk_profile"])
        summary = vault.get_wisdom_summary("user1")  # For system prompt injection
    """

    def __init__(self, base_path: str = None):
        self._base_path = Path(base_path or WISDOM_BASE_PATH).resolve()
        self._base_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"WisdomVault: Initialized at {self._base_path}")

    def _user_dir(self, user_id: str) -> Path:
        """Get/create user's wisdom directory."""
        d = self._base_path / self._sanitize_id(user_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _category_file(self, user_id: str, category: str) -> Path:
        return self._user_dir(user_id) / f"{category}.md"

    @staticmethod
    def _sanitize_id(user_id: str) -> str:
        """Sanitize user_id for filesystem safety."""
        return user_id.replace("@", "_at_").replace("/", "_").replace("\\", "_")

    # ── CRUD Operations ──────────────────────────────────

    def store_wisdom(
        self,
        user_id: str,
        category: str,
        principle: str,
        confidence: float = 0.5,
        evidence_count: int = 1,
        tags: List[str] = None,
        source_episodes: List[str] = None,
    ) -> WisdomEntry:
        """
        Store or append a wisdom principle to the appropriate category file.
        將智慧原則存入對應的類別檔案。

        If the principle is similar to an existing one, it merges
        (increases evidence_count and updates confidence).
        """
        entry = WisdomEntry(
            category=category,
            principle=principle,
            confidence=min(1.0, confidence),
            evidence_count=evidence_count,
            tags=tags or [],
            source_episodes=source_episodes or [],
        )

        # Load existing entries
        existing = self._load_category_file(user_id, category)

        # Check for similar existing principle (simple dedup)
        merged = False
        for existing_entry in existing:
            if self._is_similar(existing_entry.principle, principle):
                # Merge: boost confidence and evidence count
                existing_entry.evidence_count += evidence_count
                existing_entry.confidence = min(
                    1.0,
                    existing_entry.confidence + 0.05 * evidence_count
                )
                existing_entry.tags = list(
                    set(existing_entry.tags + (tags or []))
                )
                existing_entry.source_episodes.extend(source_episodes or [])
                existing_entry.last_updated = datetime.now(timezone.utc).strftime(
                    "%Y-%m-%d"
                )
                merged = True
                entry = existing_entry
                logger.info(
                    f"WisdomVault: Merged into existing principle "
                    f"(evidence now: {existing_entry.evidence_count})"
                )
                break

        if not merged:
            existing.append(entry)

        # Write back
        self._write_category_file(user_id, category, existing)
        self._update_meta(user_id)

        return entry

    def supersede_wisdom(
        self,
        user_id: str,
        category: str,
        old_principle: str,
        new_principle: str,
        confidence: float = 0.5,
        evidence_count: int = 1,
        tags: List[str] = None,
        source_episodes: List[str] = None,
    ) -> WisdomEntry:
        """
        Supersede an existing wisdom principle with a new one.
        將既有的智慧原則替換為新原則（用於處理衝突）。

        Lowers the confidence of the old principle and stores the new one.
        """
        existing = self._load_category_file(user_id, category)
        
        # Lower confidence of the old one
        for entry in existing:
            # [Fix 3X-5] Use fuzzy/substring matching to find the principle to supersede
            if entry.principle == old_principle or old_principle in entry.principle or entry.principle in old_principle:
                entry.confidence = 0.1
                if "superseded" not in entry.tags:
                    entry.tags.append("superseded")
                entry.last_updated = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                logger.info(f"WisdomVault: Superseded old principle (fuzzy match): {entry.principle}")
                break

        # Write the modification back first
        self._write_category_file(user_id, category, existing)

        # Then store the new one (store_wisdom will reload the now-updated file)
        return self.store_wisdom(
            user_id=user_id,
            category=category,
            principle=new_principle,
            confidence=confidence,
            evidence_count=evidence_count,
            tags=tags,
            source_episodes=source_episodes
        )

    def load_wisdom(
        self,
        user_id: str,
        categories: List[str] = None,
    ) -> List[WisdomEntry]:
        """
        Load wisdom entries for a user, optionally filtered by category.
        載入使用者的智慧條目，可選擇按類別過濾。
        """
        cats = categories or WISDOM_CATEGORIES
        entries = []
        for cat in cats:
            entries.extend(self._load_category_file(user_id, cat))
        return entries

    def get_wisdom_summary(
        self,
        user_id: str,
        max_entries: int = 15,
    ) -> str:
        """
        Get a formatted wisdom summary for system prompt injection.
        取得格式化的智慧摘要，供 system prompt 注入使用。

        Returns the top principles sorted by confidence × evidence.
        """
        all_entries = self.load_wisdom(user_id)

        if not all_entries:
            return ""

        # Sort by confidence * evidence_count (most validated first)
        all_entries.sort(
            key=lambda e: e.confidence * e.evidence_count,
            reverse=True,
        )

        # Take top N
        top = all_entries[:max_entries]

        lines = ["## 累積智慧 (Learned Wisdom)\n"]
        current_cat = None
        for entry in top:
            if entry.category != current_cat:
                current_cat = entry.category
                cat_label = {
                    "risk_profile": "🛡️ 風險偏好",
                    "market_patterns": "📊 市場模式",
                    "decision_habits": "🧠 決策習慣",
                    "ticker_insights": "📈 個股洞察",
                    "conversation_style": "💬 對話偏好",
                    "tone_preference": "🎭 語氣風格",
                    "reporting_style": "📊 報告格式",
                }.get(current_cat, f"📋 {current_cat}")
                lines.append(f"\n### {cat_label}")

            conf_pct = f"{entry.confidence:.0%}"
            lines.append(
                f"- {entry.principle} ({conf_pct}, "
                f"evidence×{entry.evidence_count})"
            )

        return "\n".join(lines)

    def has_wisdom(self, user_id: str) -> bool:
        """Check if any wisdom exists for this user."""
        user_dir = self._base_path / self._sanitize_id(user_id)
        if not user_dir.exists():
            return False
        return any(user_dir.glob("*.md"))

    def list_users(self) -> List[str]:
        """List all user IDs with stored wisdom."""
        return [
            d.name for d in self._base_path.iterdir()
            if d.is_dir() and not d.name.startswith("_")
        ]

    # ── File I/O ─────────────────────────────────────────

    def _load_category_file(
        self, user_id: str, category: str
    ) -> List[WisdomEntry]:
        """Parse a category .md file into WisdomEntry list."""
        path = self._category_file(user_id, category)
        if not path.exists():
            return []

        try:
            raw = path.read_text(encoding="utf-8")
            # Parse YAML frontmatter
            if raw.startswith("---"):
                parts = raw.split("---", 2)
                if len(parts) >= 3:
                    frontmatter = yaml.safe_load(parts[1]) or {}
                    entries_data = frontmatter.get("entries", [])
                    return [
                        WisdomEntry(category=category, **e)
                        for e in entries_data
                        if isinstance(e, dict)
                    ]
            return []
        except Exception as e:
            logger.error(
                f"WisdomVault: Failed to load {path}: {e}"
            )
            return []

    def _write_category_file(
        self,
        user_id: str,
        category: str,
        entries: List[WisdomEntry],
    ) -> None:
        """Write entries to category .md file with YAML frontmatter."""
        path = self._category_file(user_id, category)

        # Build frontmatter
        frontmatter = {
            "category": category,
            "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "entry_count": len(entries),
            "total_evidence": sum(e.evidence_count for e in entries),
            "entries": [
                {
                    "principle": e.principle,
                    "confidence": round(e.confidence, 3),
                    "evidence_count": e.evidence_count,
                    "tags": e.tags,
                    "last_updated": e.last_updated,
                    "source_episodes": e.source_episodes[-5:],  # Keep last 5 refs
                }
                for e in entries
            ],
        }

        # Build markdown body
        cat_label = {
            "risk_profile": "風險偏好特徵",
            "market_patterns": "市場觀察模式",
            "decision_habits": "決策行為模式",
            "ticker_insights": "個股累積洞察",
            "conversation_style": "對話偏好",
            "tone_preference": "語氣風格偏好",
            "reporting_style": "報告格式偏好",
        }.get(category, category)

        body_lines = [f"# {cat_label}\n"]
        for entry in entries:
            conf_bar = "●" * int(entry.confidence * 5) + "○" * (
                5 - int(entry.confidence * 5)
            )
            body_lines.append(
                f"- [{conf_bar}] {entry.principle}"
            )
            if entry.tags:
                body_lines.append(f"  - Tags: {', '.join(entry.tags)}")

        # Write file
        yaml_str = yaml.dump(
            frontmatter,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
        content = f"---\n{yaml_str}---\n\n" + "\n".join(body_lines) + "\n"

        path.write_text(content, encoding="utf-8")
        logger.debug(f"WisdomVault: Wrote {len(entries)} entries to {path}")

    def _update_meta(self, user_id: str) -> None:
        """Update the meta.yaml index file for a user."""
        user_dir = self._user_dir(user_id)
        meta_path = user_dir / "meta.yaml"

        categories_info = {}
        total_entries = 0
        for cat in WISDOM_CATEGORIES:
            entries = self._load_category_file(user_id, cat)
            if entries:
                categories_info[cat] = {
                    "count": len(entries),
                    "avg_confidence": round(
                        sum(e.confidence for e in entries) / len(entries), 3
                    ),
                    "total_evidence": sum(e.evidence_count for e in entries),
                }
                total_entries += len(entries)

        meta = {
            "user_id": user_id,
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "total_entries": total_entries,
            "categories": categories_info,
        }

        meta_path.write_text(
            yaml.dump(meta, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )

    @staticmethod
    def _is_similar(a: str, b: str, threshold: float = 0.6) -> bool:
        """
        Simple similarity check between two principles.
        簡單的原則相似度檢查。

        Uses character-level overlap ratio as a fast heuristic.
        Production could upgrade to embedding cosine similarity.
        """
        if not a or not b:
            return False

        # Normalize
        a_lower = a.lower().strip()
        b_lower = b.lower().strip()

        if a_lower == b_lower:
            return True

        # Character n-gram overlap (fast heuristic)
        def ngrams(text, n=3):
            return set(text[i: i + n] for i in range(len(text) - n + 1))

        a_ng = ngrams(a_lower)
        b_ng = ngrams(b_lower)

        if not a_ng or not b_ng:
            return False

        overlap = len(a_ng & b_ng) / max(len(a_ng | b_ng), 1)
        return overlap >= threshold
