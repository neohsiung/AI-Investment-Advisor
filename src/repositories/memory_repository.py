import typing
import logging
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
import pandas as pd
from sqlalchemy import text
import uuid
from src.data.database import BaseRepository, get_db_engine
from src.domain.interfaces import IMemoryRepository
from src.domain.entities import ReportMemoryItem

# 2026-07-14: this module referenced `logger` in exception handlers without
# ever defining it — a latent NameError waiting on any actual failure path
# (never triggered before since the old filesystem-only AgentState code
# rarely raised; the new Postgres-backed path surfaced it immediately in
# tests against a DB without the agent_rules table).
logger = logging.getLogger(__name__)

class AlchemyMemoryRepository(BaseRepository, IMemoryRepository):
    """
    Implementation of IMemoryRepository using SQLAlchemy.
    使用 SQLAlchemy 實作的 IMemoryRepository。
    """
    def __init__(self, engine: Any = None):
        """
        Initialize the repository.
        初始化儲存庫。
        """
        BaseRepository.__init__(self, engine or get_db_engine())

    def get_recent_reports(self, user_id: str, report_type: str, limit: int) -> List[ReportMemoryItem]:
        """
        Get recent reports for a specific user and report type.
        取得特定使用者與報告類型的近期報告。
        """
        with self.engine.connect() as conn:
            query = text("""
                SELECT id, user_id, created_at, content, summary, report_type 
                FROM reports 
                WHERE user_id = :uid AND report_type = :rtype 
                ORDER BY created_at DESC 
                LIMIT :limit
            """)
            rows = conn.execute(query, {"uid": user_id, "rtype": report_type, "limit": limit}).fetchall()
            
            items = []
            for row in rows:
                item = ReportMemoryItem(
                    user_id=row.user_id,
                    report_type=row.report_type if row.report_type else report_type,
                    report_date=row.created_at,
                    full_content=row.content,
                    compressed_summary=row.summary
                )
                items.append(item)
            return items

    def save_report(self, item: ReportMemoryItem) -> None:
        """
        Save a report memory item.
        儲存報告記憶項目。
        """
        with self.engine.begin() as conn:
            new_id = str(uuid.uuid4())
            query = text("""
                INSERT INTO reports (id, user_id, created_at, title, content, summary, report_type) 
                VALUES (:id, :uid, :created_at, :title, :content, :summary, :rtype)
            """)
            # Create a user-friendly default title
            date_str = item.report_date.strftime("%Y-%m-%d") if hasattr(item.report_date, "strftime") else str(item.report_date)
            title = f"{item.report_type.capitalize()} Analysis Report ({date_str})"
            conn.execute(query, {
                "id": new_id,
                "uid": item.user_id,
                "created_at": item.report_date,
                "title": title,
                "content": item.full_content,
                "summary": item.compressed_summary,
                "rtype": item.report_type
            })

# Legacy alias removed in v4.1.7
# @deprecated: Use AlchemyMemoryRepository


class AgentState:
    """
    Manages loading and parsing agent-level STATE.md.
    """
    def __init__(self, workspace_root: str = "workspace"):
        self.workspace_root = workspace_root

    def get_state_path(self, agent_name: str) -> str:
        workspace_map = {
            "CIO": "captain",
            "Macro": "macro-evaluator",
            "Risk": "risk-assessor",
            "Sentiment": "sentiment-analyst",
            "Momentum": "market-scanner",
            "Fundamental": "data-prep",
            "Thematic": "portfolio-manager",
            "Engineer": "system-engineer",
            "Evaluator Judge": "evaluator-judge",
            "Sensory Watchdog": "sensory-watchdog"
        }
        mapped_name = workspace_map.get(agent_name, agent_name.lower().replace(" ", "-"))
        return f"{self.workspace_root}/{mapped_name}/STATE.md"

    def load_general_rules(self, agent_name: str, user_id: str = "system") -> str:
        """
        Load General Rules for (user_id, agent_name).

        2026-07-14: Postgres (agent_rules table) is now the source of
        truth, per-user isolated — the old STATE.md-only storage had no
        user_id at all, so rules were effectively global across every
        tenant. Falls back to STATE.md (pre-migration data, or DB
        unavailable) if no DB row exists.

        2026-07-14 (B-P2.1): agent_rules can now hold MULTIPLE atomic
        active rows per (user, agent) — added via add_rule() for
        per-rule citation/scoring — in addition to the single blob row
        save_general_rules() writes. All active rows are joined, newest
        last.
        """
        try:
            from sqlalchemy import text
            from src.data.database import get_db_engine
            engine = get_db_engine()
            with engine.connect() as conn:
                rows = conn.execute(
                    text("""
                        SELECT rule_text FROM agent_rules
                        WHERE user_id = :uid AND agent_name = :name AND status = 'active'
                        ORDER BY created_at ASC
                    """),
                    {"uid": user_id, "name": agent_name},
                ).fetchall()
                if rows:
                    return "\n".join(r[0] for r in rows if r[0])
        except Exception as e:
            logger.warning(f"AgentState: DB read failed for {agent_name} (falling back to STATE.md): {e}")
        return self._load_from_file(agent_name)

    def get_active_rules(self, agent_name: str, user_id: str = "system") -> List[Dict[str, Any]]:
        """
        Return active rules as individual {id, rule_text, score} dicts —
        the per-rule granularity load_general_rules' joined-string return
        can't provide. Used by citation tracking and rule curation.
        Returns [] (not a STATE.md fallback) if the DB is unavailable —
        citation/curation is a pure enhancement, never a hard dependency.
        """
        try:
            from sqlalchemy import text
            from src.data.database import get_db_engine
            engine = get_db_engine()
            with engine.connect() as conn:
                rows = conn.execute(
                    text("""
                        SELECT id, rule_text, score FROM agent_rules
                        WHERE user_id = :uid AND agent_name = :name AND status = 'active'
                        ORDER BY created_at ASC
                    """),
                    {"uid": user_id, "name": agent_name},
                ).fetchall()
                return [{"id": r[0], "rule_text": r[1], "score": r[2]} for r in rows]
        except Exception as e:
            logger.warning(f"AgentState: get_active_rules failed for {agent_name}: {e}")
            return []

    def add_rule(
        self, agent_name: str, rule_text: str, user_id: str = "system",
        source_decision_id: Optional[str] = None,
        status: str = "active",
    ) -> Optional[int]:
        """
        Insert ONE new atomic rule. Refreshes the STATE.md render cache to the
        full joined active set ONLY if status == 'active'. Returns the new rule's id, or None on failure.
        """
        new_id = None
        db_ok = False
        try:
            from sqlalchemy import text
            from src.data.database import get_db_engine
            engine = get_db_engine()
            with engine.begin() as conn:
                row = conn.execute(
                    text("""
                        INSERT INTO agent_rules (user_id, agent_name, rule_text, status, source_decision_id)
                        VALUES (:uid, :name, :rule_text, :status, :source_decision_id)
                        RETURNING id
                    """),
                    {
                        "uid": user_id, 
                        "name": agent_name, 
                        "rule_text": rule_text, 
                        "status": status,
                        "source_decision_id": source_decision_id
                    },
                ).fetchone()
                new_id = row[0] if row else None
                db_ok = True
        except Exception as e:
            logger.warning(f"AgentState: add_rule DB write failed for {agent_name}: {e}")

        # Refresh the render cache ONLY if status is 'active'
        if status == "active":
            if db_ok:
                self._save_to_file(agent_name, self.load_general_rules(agent_name, user_id=user_id))
            else:
                existing = self._load_from_file(agent_name)
                merged = f"{existing}\n{rule_text}" if existing else rule_text
                self._save_to_file(agent_name, merged)
        return new_id

    def save_general_rules(self, agent_name: str, rules: str, user_id: str = "system") -> None:
        """
        Persist General Rules for (user_id, agent_name).

        Writes Postgres first (source of truth, supersedes rather than
        overwrites the previous active row so history survives for future
        rule-lifecycle work). Always ALSO writes the STATE.md render cache
        — prompts elsewhere may still read the file directly, and
        wal_protocol._preserve_general_rules relies on the
        "## General Rules" section existing there across WAL flushes.
        """
        try:
            from sqlalchemy import text
            from src.data.database import get_db_engine
            engine = get_db_engine()
            with engine.begin() as conn:
                conn.execute(
                    text("""
                        UPDATE agent_rules SET status = 'superseded', updated_at = NOW()
                        WHERE user_id = :uid AND agent_name = :name AND status = 'active'
                    """),
                    {"uid": user_id, "name": agent_name},
                )
                conn.execute(
                    text("""
                        INSERT INTO agent_rules (user_id, agent_name, rule_text, status, version)
                        VALUES (
                            :uid, :name, :rules, 'active',
                            COALESCE((SELECT MAX(version) FROM agent_rules WHERE user_id = :uid AND agent_name = :name), 0) + 1
                        )
                    """),
                    {"uid": user_id, "name": agent_name, "rules": rules},
                )
        except Exception as e:
            logger.warning(f"AgentState: DB write failed for {agent_name} (STATE.md render cache still updated): {e}")

        self._save_to_file(agent_name, rules)

    # ── STATE.md render cache (private) ──────────────────────────────────

    def _load_from_file(self, agent_name: str) -> str:
        import os
        import re
        path = self.get_state_path(agent_name)
        if not os.path.exists(path):
            return ""
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            pattern = re.compile(
                r"^##\s*General\s*Rules\b(.*?)(?=\n#+|\Z)",
                re.DOTALL | re.MULTILINE | re.IGNORECASE
            )
            match = pattern.search(content)
            if match:
                return match.group(1).strip()
            return ""
        except Exception as e:
            logger.warning(f"Failed to load STATE.md for {agent_name}: {e}")
            return ""

    def _save_to_file(self, agent_name: str, rules: str) -> None:
        import os
        import re
        path = self.get_state_path(agent_name)
        os.makedirs(os.path.dirname(path), exist_ok=True)

        content = ""
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                logger.warning(f'Exception in memory_repository.py: {e}', exc_info=True)

        rule_section = f"## General Rules\n{rules}"

        if not content.strip() or "## General Rules" not in content:
            if content.strip():
                content = content.rstrip() + f"\n\n{rule_section}\n"
            else:
                content = f"# STATE\n\n{rule_section}\n"
        else:
            pattern = re.compile(r"^##\s*General\s*Rules\b(.*?)(?=\n#+|\Z)", re.DOTALL | re.MULTILINE | re.IGNORECASE)
            content = pattern.sub(f"## General Rules\n{rules}", content)

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            logger.warning(f"Failed to save STATE.md for {agent_name}: {e}")
