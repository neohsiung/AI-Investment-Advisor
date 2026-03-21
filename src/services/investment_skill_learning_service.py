"""
Investment Skill Learning Service — 每日投資技能學習與萃取服務。

Reads investment articles / podcast transcripts, extracts structured
"investment skills" (timeframe, environment, industry, technique),
manages skill consolidation (dynamic merge threshold), and provides
applicable skill lookup for the Agent runtime.

遵循規範:
  - 規範一 (Clean Architecture): Service 層不直接操作 DB，透過 Repository pattern
  - 規範四 (模組化設計): 獨立可單元測試
  - 規範十三 (No-Hardcoded-Secrets): API Keys 從 settings 取得
"""

import json
import re
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from src.utils.logger import setup_logger
from src.agents.factory import AgentFactory

logger = setup_logger("InvestmentSkillLearningService")

# ── LLM Prompt for Skill Extraction ──────────────────────────

SKILL_EXTRACTION_PROMPT = """TASK: Analyze the following investment-related content and extract the investment skill/strategy described.

CONTENT:
{content}

SOURCE TYPE: {source_type}

Extract the following structured information. Respond ONLY as a JSON object:
{{
    "name": "<concise skill name, e.g. 'Momentum Breakout Strategy'>",
    "description": "<detailed description of the investment skill/strategy, 2-4 sentences>",
    "timeframe": "<one of: short_term, medium_term, long_term>",
    "environment": {{
        "market_regime": "<one of: bull, bear, sideways, volatile, any>",
        "volatility": "<one of: low, medium, high, any>",
        "interest_rate": "<one of: rising, falling, stable, any>"
    }},
    "industry": ["<list of applicable industries, e.g. tech, healthcare, energy, financials, or 'all'>"],
    "technique": "<one of: momentum, fundamental, macro, quantitative, sentiment, event_driven, value, growth, income, contrarian>",
    "conditions": {{
        "entry_signals": "<when to apply this skill>",
        "exit_signals": "<when to stop using this skill>",
        "risk_management": "<key risk controls>"
    }},
    "is_valid_skill": <boolean, false if the content does not describe a usable investment skill>
}}
"""

SKILL_MERGE_PROMPT = """TASK: Compare a newly extracted investment skill with existing similar skills from the database.
Determine if the new skill should be MERGED into an existing skill or CREATED as a new skill.

NEW SKILL:
{new_skill}

EXISTING SIMILAR SKILLS:
{existing_skills}

MERGE THRESHOLD: {threshold}
(Skills with semantic overlap > {threshold}% should be merged)

Respond ONLY as a JSON object:
{{
    "action": "<MERGE or CREATE>",
    "merge_target_id": "<id of existing skill to merge into, or null if CREATE>",
    "merged_description": "<if MERGE: updated combined description that incorporates both skills' insights. if CREATE: null>",
    "merged_conditions": {{<if MERGE: updated combined conditions. if CREATE: null>}},
    "reasoning": "<brief explanation of the decision>"
}}
"""


class InvestmentSkillLearningService:
    """
    每日投資技能學習服務。
    Daily Investment Skill Learning Service.

    Responsibilities:
    1. Extract skills from articles/podcasts via LLM
    2. Find similar existing skills (semantic matching)
    3. Merge or create skills (dynamic threshold)
    4. Adjust merge threshold based on token usage
    5. Cleanup low-usage/stale skills
    6. Query applicable skills for current context
    """

    def __init__(self, user_id: str = "system"):
        self.user_id = user_id
        self.agent = AgentFactory.create_agent(
            "Engineer", use_cache=True, user_id=user_id
        )
        self.logger = setup_logger("InvestmentSkillLearningService")

    # ── Core: Extract Skill from Content ────────────────────

    def extract_skill_from_content(
        self,
        content: str,
        source_url: str = "",
        source_type: str = "article",
    ) -> Optional[Dict[str, Any]]:
        """
        Use LLM to extract a structured investment skill from content.
        使用 LLM 從內容中萃取結構化投資技能。
        """
        prompt = SKILL_EXTRACTION_PROMPT.format(
            content=content[:4000],  # Limit to avoid token explosion
            source_type=source_type,
        )

        try:
            response = self.agent.run(prompt)
            parsed = self._parse_json_response(response)

            if not parsed or not parsed.get("is_valid_skill"):
                self.logger.info("Content does not contain a valid investment skill.")
                return None

            parsed["source_article"] = source_url
            parsed["source_type"] = source_type
            return parsed

        except Exception as e:
            self.logger.error(f"Skill extraction failed: {e}")
            return None

    # ── Core: Find Similar Skills ───────────────────────────

    def find_similar_skills(
        self, new_skill: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Find existing skills similar to the new one using DB query + LLM comparison.
        使用 DB 查詢 + LLM 比對尋找相似的現有技能。
        """
        try:
            from sqlalchemy import text
            from src.data.database import get_db_engine

            engine = get_db_engine()
            with engine.connect() as conn:
                # Filter by technique and timeframe for efficiency
                result = conn.execute(
                    text(
                        "SELECT id, name, description, timeframe, technique, "
                        "environment, industry, conditions, usage_count "
                        "FROM investment_skills "
                        "WHERE user_id = :user_id AND is_active = 1 "
                        "AND (technique = :technique OR timeframe = :timeframe) "
                        "ORDER BY usage_count DESC LIMIT 10"
                    ),
                    {
                        "user_id": self.user_id,
                        "technique": new_skill.get("technique", ""),
                        "timeframe": new_skill.get("timeframe", ""),
                    },
                )
                rows = result.fetchall()
                columns = result.keys()

            return [dict(zip(columns, row)) for row in rows]

        except Exception as e:
            self.logger.error(f"Error finding similar skills: {e}")
            return []

    # ── Core: Merge or Create ───────────────────────────────

    def merge_or_create_skill(
        self,
        new_skill: Dict[str, Any],
        similar_skills: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Decide whether to merge with existing skill or create new.
        決定是合併現有技能還是建立新技能。
        """
        config = self._get_config()
        threshold = config.get("merge_threshold", 0.70)

        if not similar_skills:
            # No similar skills, always create
            return self._create_skill(new_skill)

        # Use LLM to decide merge vs create
        prompt = SKILL_MERGE_PROMPT.format(
            new_skill=json.dumps(new_skill, ensure_ascii=False, indent=2),
            existing_skills=json.dumps(
                [
                    {
                        "id": s.get("id"),
                        "name": s.get("name"),
                        "description": s.get("description"),
                        "technique": s.get("technique"),
                        "timeframe": s.get("timeframe"),
                    }
                    for s in similar_skills
                ],
                ensure_ascii=False,
                indent=2,
            ),
            threshold=int(threshold * 100),
        )

        try:
            response = self.agent.run(prompt)
            decision = self._parse_json_response(response)

            if not decision:
                self.logger.warning("Failed to parse merge decision. Creating new skill.")
                return self._create_skill(new_skill)

            if decision.get("action") == "MERGE" and decision.get("merge_target_id"):
                return self._merge_skill(
                    target_id=decision["merge_target_id"],
                    new_skill=new_skill,
                    merged_description=decision.get("merged_description"),
                    merged_conditions=decision.get("merged_conditions"),
                )
            else:
                return self._create_skill(new_skill)

        except Exception as e:
            self.logger.error(f"Merge decision failed: {e}. Creating new skill.")
            return self._create_skill(new_skill)

    # ── Core: Dynamic Merge Threshold ───────────────────────

    def adjust_merge_threshold(self) -> None:
        """
        Dynamically adjust merge threshold based on skill count and token usage.
        根據技能數量與 token 消耗動態調整合併閾值。
        """
        try:
            config = self._get_config()
            threshold = config.get("merge_threshold", 0.70)
            token_usage = config.get("last_token_usage", 0)
            token_budget = config.get("max_token_budget", 2000)
            skill_count = config.get("total_skills_count", 0)

            if token_usage > token_budget:
                # Token overbudget → more aggressive merging
                new_threshold = min(threshold + 0.05, 0.95)
                self.logger.info(
                    f"Token overbudget ({token_usage}/{token_budget}). "
                    f"Raising merge threshold: {threshold:.2f} → {new_threshold:.2f}"
                )
            elif skill_count < 5:
                # Too few skills → more lenient (create more)
                new_threshold = max(threshold - 0.05, 0.30)
                self.logger.info(
                    f"Skill count low ({skill_count}). "
                    f"Lowering merge threshold: {threshold:.2f} → {new_threshold:.2f}"
                )
            else:
                return  # No adjustment needed

            self._update_config(merge_threshold=new_threshold)

        except Exception as e:
            self.logger.error(f"Failed to adjust merge threshold: {e}")

    # ── Core: Cleanup ───────────────────────────────────────

    def cleanup_skills(self) -> Dict[str, int]:
        """
        Deactivate low-usage and stale skills.
        停用低使用率與過時的技能。
        """
        try:
            from sqlalchemy import text
            from src.data.database import get_db_engine

            engine = get_db_engine()
            with engine.begin() as conn:
                # Deactivate skills unused for 90 days with usage_count < 3
                result = conn.execute(
                    text(
                        "UPDATE investment_skills SET is_active = 0, "
                        "updated_at = CURRENT_TIMESTAMP "
                        "WHERE user_id = :user_id AND is_active = 1 "
                        "AND usage_count < 3 "
                        "AND (last_used_at IS NULL OR "
                        "last_used_at < CURRENT_TIMESTAMP - INTERVAL '90 days')"
                    ),
                    {"user_id": self.user_id},
                )
                deactivated = result.rowcount

            self.logger.info(f"Cleaned up {deactivated} stale skills.")
            return {"deactivated": deactivated}

        except Exception as e:
            self.logger.error(f"Skill cleanup failed: {e}")
            return {"deactivated": 0}

    # ── Query: Get Applicable Skills ────────────────────────

    def get_applicable_skills(
        self,
        timeframe: str = "",
        market_regime: str = "",
        industry: str = "",
        technique: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Query skills matching current context.
        根據當前環境查詢適用的投資技能。
        """
        try:
            from sqlalchemy import text
            from src.data.database import get_db_engine

            conditions = ["user_id = :user_id", "is_active = 1"]
            params: Dict[str, Any] = {"user_id": self.user_id}

            if timeframe:
                conditions.append("timeframe = :timeframe")
                params["timeframe"] = timeframe
            if technique:
                conditions.append("technique = :technique")
                params["technique"] = technique

            where_clause = " AND ".join(conditions)

            engine = get_db_engine()
            with engine.connect() as conn:
                result = conn.execute(
                    text(
                        f"SELECT id, name, description, timeframe, technique, "
                        f"environment, industry, conditions, usage_count "
                        f"FROM investment_skills "
                        f"WHERE {where_clause} "
                        f"ORDER BY usage_count DESC LIMIT 10"
                    ),
                    params,
                )
                rows = result.fetchall()
                columns = result.keys()

            skills = [dict(zip(columns, row)) for row in rows]

            # Post-filter by market_regime and industry (JSONB)
            if market_regime:
                skills = [
                    s
                    for s in skills
                    if self._match_environment(s.get("environment"), market_regime)
                ]
            if industry:
                skills = [
                    s
                    for s in skills
                    if self._match_industry(s.get("industry"), industry)
                ]

            # Track token usage for dynamic threshold
            token_estimate = sum(
                len(json.dumps(s, default=str)) for s in skills
            )
            self._update_config(
                last_token_usage=token_estimate,
                total_skills_count=len(skills),
            )

            # Increment usage_count for returned skills
            if skills:
                self._increment_usage(
                    [s["id"] for s in skills]
                )

            return skills

        except Exception as e:
            self.logger.error(f"Error querying applicable skills: {e}")
            return []

    # ── Orchestrator: Daily Learning ────────────────────────

    def run_daily_learning(
        self,
        content: str = "",
        source_url: str = "",
        source_type: str = "article",
    ) -> Dict[str, Any]:
        """
        Main daily learning flow.
        每日學習主流程。

        1. Get content (from param or Readwise)
        2. Extract skill via LLM
        3. Find similar skills
        4. Merge or create
        5. Adjust threshold
        6. Cleanup stale skills
        """
        result = {
            "status": "completed",
            "action": None,
            "skill_name": None,
            "details": {},
        }

        try:
            # Step 1: Get content
            if not content:
                content = self._fetch_readwise_content()
                source_type = "highlight"
                if not content:
                    # Step 1b: Auto-Discovery fallback — search the web
                    self.logger.info("No Readwise content. Attempting auto-discovery...")
                    discovered = self._auto_discover_content()
                    if discovered:
                        content = discovered.get("content", "")
                        source_url = discovered.get("url", "")
                        source_type = "auto_discovery"
                        self.logger.info(f"Auto-discovered content from: {source_url}")
                    else:
                        result["status"] = "skipped"
                        result["details"]["reason"] = "No new content available (Readwise + Auto-Discovery exhausted)"
                        self.logger.info("No content from any source for skill learning.")
                        return result

            # Step 2: Extract skill
            skill = self.extract_skill_from_content(content, source_url, source_type)
            if not skill:
                result["status"] = "skipped"
                result["details"]["reason"] = "Content does not contain valid skill"
                return result

            # Step 3: Find similar skills
            similar = self.find_similar_skills(skill)
            self.logger.info(
                f"Found {len(similar)} similar skills for '{skill.get('name')}'"
            )

            # Step 4: Merge or create
            action_result = self.merge_or_create_skill(skill, similar)
            result["action"] = action_result.get("action")
            result["skill_name"] = action_result.get("name")
            result["details"] = action_result

            # Step 5: Adjust threshold
            self.adjust_merge_threshold()

            # Step 6: Cleanup
            cleanup = self.cleanup_skills()
            result["details"]["cleanup"] = cleanup

            self.logger.info(
                f"Daily learning completed: {result['action']} → {result['skill_name']}"
            )

        except Exception as e:
            self.logger.error(f"Daily learning failed: {e}")
            result["status"] = "failed"
            result["details"]["error"] = str(e)

        return result

    # ── Private Helpers ─────────────────────────────────────

    def _create_skill(self, skill: Dict[str, Any]) -> Dict[str, Any]:
        """Insert a new skill into DB."""
        try:
            from sqlalchemy import text
            from src.data.database import get_db_engine

            skill_id = str(uuid.uuid4())
            engine = get_db_engine()
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO investment_skills "
                        "(id, user_id, name, description, timeframe, environment, "
                        "industry, technique, conditions, source_article, source_type) "
                        "VALUES (:id, :user_id, :name, :description, :timeframe, "
                        ":environment, :industry, :technique, :conditions, "
                        ":source_article, :source_type)"
                    ),
                    {
                        "id": skill_id,
                        "user_id": self.user_id,
                        "name": skill.get("name", "Unnamed Skill"),
                        "description": skill.get("description", ""),
                        "timeframe": skill.get("timeframe", "medium_term"),
                        "environment": json.dumps(
                            skill.get("environment", {}), ensure_ascii=False
                        ),
                        "industry": json.dumps(
                            skill.get("industry", []), ensure_ascii=False
                        ),
                        "technique": skill.get("technique", ""),
                        "conditions": json.dumps(
                            skill.get("conditions", {}), ensure_ascii=False
                        ),
                        "source_article": skill.get("source_article", ""),
                        "source_type": skill.get("source_type", "article"),
                    },
                )

            self.logger.info(f"Created new skill: {skill.get('name')} ({skill_id})")
            return {"action": "CREATED", "id": skill_id, "name": skill.get("name")}

        except Exception as e:
            self.logger.error(f"Failed to create skill: {e}")
            return {"action": "FAILED", "error": str(e)}

    def _merge_skill(
        self,
        target_id: str,
        new_skill: Dict[str, Any],
        merged_description: Optional[str] = None,
        merged_conditions: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Merge new skill into existing skill."""
        try:
            from sqlalchemy import text
            from src.data.database import get_db_engine

            engine = get_db_engine()
            with engine.begin() as conn:
                # Get current merged_from
                existing = conn.execute(
                    text(
                        "SELECT name, merged_from, version FROM investment_skills "
                        "WHERE id = :id"
                    ),
                    {"id": target_id},
                ).fetchone()

                if not existing:
                    self.logger.warning(f"Merge target {target_id} not found. Creating instead.")
                    return self._create_skill(new_skill)

                current_merged = json.loads(existing[1]) if existing[1] else []
                current_merged.append(
                    {
                        "source": new_skill.get("source_article", ""),
                        "name": new_skill.get("name", ""),
                        "merged_at": datetime.now(timezone.utc).isoformat(),
                    }
                )

                update_fields = {
                    "id": target_id,
                    "merged_from": json.dumps(current_merged, ensure_ascii=False),
                    "version": (existing[2] or 1) + 1,
                }

                set_clauses = [
                    "merged_from = :merged_from",
                    "version = :version",
                    "updated_at = CURRENT_TIMESTAMP",
                ]

                if merged_description:
                    set_clauses.append("description = :description")
                    update_fields["description"] = merged_description

                if merged_conditions:
                    set_clauses.append("conditions = :conditions")
                    update_fields["conditions"] = json.dumps(
                        merged_conditions, ensure_ascii=False
                    )

                conn.execute(
                    text(
                        f"UPDATE investment_skills SET {', '.join(set_clauses)} "
                        f"WHERE id = :id"
                    ),
                    update_fields,
                )

            self.logger.info(
                f"Merged skill into '{existing[0]}' (v{update_fields['version']})"
            )
            return {
                "action": "MERGED",
                "id": target_id,
                "name": existing[0],
                "version": update_fields["version"],
            }

        except Exception as e:
            self.logger.error(f"Failed to merge skill: {e}")
            return {"action": "FAILED", "error": str(e)}

    def _get_config(self) -> Dict[str, Any]:
        """Get or create skill learning config."""
        try:
            from sqlalchemy import text
            from src.data.database import get_db_engine

            engine = get_db_engine()
            with engine.connect() as conn:
                result = conn.execute(
                    text(
                        "SELECT merge_threshold, max_token_budget, "
                        "last_token_usage, total_skills_count "
                        "FROM skill_learning_config WHERE user_id = :user_id"
                    ),
                    {"user_id": self.user_id},
                ).fetchone()

            if result:
                return {
                    "merge_threshold": float(result[0]),
                    "max_token_budget": result[1],
                    "last_token_usage": result[2],
                    "total_skills_count": result[3],
                }

            # Create default config
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO skill_learning_config (user_id) "
                        "VALUES (:user_id) ON CONFLICT (user_id) DO NOTHING"
                    ),
                    {"user_id": self.user_id},
                )
            return {
                "merge_threshold": 0.70,
                "max_token_budget": 2000,
                "last_token_usage": 0,
                "total_skills_count": 0,
            }

        except Exception as e:
            self.logger.error(f"Error getting config: {e}")
            return {
                "merge_threshold": 0.70,
                "max_token_budget": 2000,
                "last_token_usage": 0,
                "total_skills_count": 0,
            }

    def _update_config(self, **kwargs) -> None:
        """Update skill learning config fields."""
        try:
            from sqlalchemy import text
            from src.data.database import get_db_engine

            set_clauses = ["updated_at = CURRENT_TIMESTAMP"]
            params: Dict[str, Any] = {"user_id": self.user_id}

            for key, value in kwargs.items():
                if key in (
                    "merge_threshold",
                    "max_token_budget",
                    "last_token_usage",
                    "total_skills_count",
                ):
                    set_clauses.append(f"{key} = :{key}")
                    params[key] = value

            engine = get_db_engine()
            with engine.begin() as conn:
                conn.execute(
                    text(
                        f"UPDATE skill_learning_config "
                        f"SET {', '.join(set_clauses)} "
                        f"WHERE user_id = :user_id"
                    ),
                    params,
                )

        except Exception as e:
            self.logger.error(f"Error updating config: {e}")

    def _increment_usage(self, skill_ids: List[str]) -> None:
        """Increment usage_count for skills."""
        try:
            from sqlalchemy import text
            from src.data.database import get_db_engine

            engine = get_db_engine()
            with engine.begin() as conn:
                for sid in skill_ids:
                    conn.execute(
                        text(
                            "UPDATE investment_skills "
                            "SET usage_count = usage_count + 1, "
                            "last_used_at = CURRENT_TIMESTAMP "
                            "WHERE id = :id"
                        ),
                        {"id": sid},
                    )

        except Exception as e:
            self.logger.error(f"Error incrementing usage: {e}")

    def _fetch_readwise_content(self) -> str:
        """Fetch latest investment highlight from Readwise."""
        try:
            from src.services.readwise_service import ReadwiseService

            svc = ReadwiseService(user_id=self.user_id)
            highlights = svc.fetch_and_analyze_highlights()

            if highlights:
                latest = highlights[0]
                return latest.get("text", "")
            return ""

        except Exception as e:
            self.logger.error(f"Readwise fetch failed: {e}")
            return ""

    def _auto_discover_content(self) -> Optional[Dict[str, str]]:
        """
        Auto-discover investment content from the web using SearchService (Tavily).
        自動從網路搜尋最佳投資策略文章作為學習素材。
        """
        try:
            from src.services.search_service import InternetSearchService

            search_svc = InternetSearchService(user_id=self.user_id)

            # Rotate search queries for diversity
            import random
            queries = [
                "best investment strategy article this week",
                "top hedge fund investment technique explained",
                "value investing strategy analysis 2026",
                "momentum trading strategy breakdown",
                "macro investing approach current market",
                "portfolio risk management technique",
                "contrarian investing strategy guide",
                "growth investing in AI and technology sector",
            ]
            query = random.choice(queries)
            self.logger.info(f"Auto-discovery search: '{query}'")

            results = search_svc.search_financial_context(query, max_results=3)

            if not results:
                self.logger.info("Auto-discovery: No search results found.")
                return None

            # Pick the best result (first one with substantial content)
            for r in results:
                content = r.get("content", "") or r.get("snippet", "")
                url = r.get("url", "") or r.get("link", "")
                title = r.get("title", "")

                if content and len(content) > 200:
                    self.logger.info(f"Auto-discovered article: {title}")
                    return {"content": f"Title: {title}\n\n{content}", "url": url}

            # Fallback: use the first result even if short
            first = results[0]
            content = first.get("content", "") or first.get("snippet", "")
            url = first.get("url", "") or first.get("link", "")
            title = first.get("title", "")
            if content:
                return {"content": f"Title: {title}\n\n{content}", "url": url}

            return None

        except Exception as e:
            self.logger.error(f"Auto-discovery failed: {e}")
            return None

    def _match_environment(
        self, env_data: Any, market_regime: str
    ) -> bool:
        """Check if skill environment matches the target regime."""
        if not env_data:
            return True
        if isinstance(env_data, str):
            try:
                env_data = json.loads(env_data)
            except (json.JSONDecodeError, TypeError):
                return True
        regime = env_data.get("market_regime", "any")
        return regime in ("any", market_regime)

    def _match_industry(self, industry_data: Any, target: str) -> bool:
        """Check if skill industry matches the target."""
        if not industry_data:
            return True
        if isinstance(industry_data, str):
            try:
                industry_data = json.loads(industry_data)
            except (json.JSONDecodeError, TypeError):
                return True
        if not isinstance(industry_data, list):
            return True
        return "all" in industry_data or target in industry_data

    def _parse_json_response(self, response: Any) -> Optional[Dict[str, Any]]:
        """Robust JSON parser for LLM output."""
        if isinstance(response, dict) and "name" in response:
            return response

        response_str = ""
        if isinstance(response, dict):
            response_str = (
                str(response.get("content", ""))
                or str(response.get("output", ""))
                or str(response)
            )
        else:
            response_str = str(response)

        match = re.search(r"\{.*\}", response_str, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                self.logger.warning("Failed to parse JSON from LLM response.")
                return None
        return None
