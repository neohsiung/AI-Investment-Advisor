"""
Cognitive Memory Manager — DIKW Distillation Engine.
認知記憶管理器 — DIKW 蒸餾引擎。

Orchestrates the Data → Information → Knowledge → Wisdom pipeline:

  D→I  (compact_stm_to_episodic):
    20 raw messages → 1 structured episodic summary
    Compression: ~20:1
    LLM tier: fast

  I→K  (distill_episodic_to_knowledge):
    50 episodes → 5-10 knowledge fragments
    Compression: ~10:1
    LLM tier: smart

  K→W  (crystallize_knowledge_to_wisdom):
    N knowledge fragments → 1 wisdom principle (per category)
    Compression: ~5:1
    LLM tier: smart

Cognitive science mapping:
  - Working Memory (Redis) → Hippocampus (PG) → Neocortex (Volume)
  - System 1 hot cache → System 2 deliberate processing → Crystallized intelligence
  - Sensory buffer → Episodic encoding → Semantic consolidation

遵循規範:
  - 規範一 (Clean Architecture): 依賴注入，不直接實例化 infra
  - 規範四 (模組化設計): 每層蒸餾獨立可測試
  - 規範十五 (AI-Support First): 結構化輸出供 Agent 消費
"""

import json
import logging
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────

EPISODIC_DISTILL_THRESHOLD = 50   # Episodes before Knowledge distillation
KNOWLEDGE_CRYSTALLIZE_THRESHOLD = 10  # Knowledge fragments before Wisdom


class CognitiveMemoryManager:
    """
    Orchestrates the DIKW distillation pipeline across 3 memory tiers.
    協調三層記憶之間的 DIKW 蒸餾管線。

    Tiers:
      1. STM (Redis)  — raw conversation data
      2. Episodic (PG) — compressed information (summaries)
      3. Wisdom (Files) — crystallized principles

    Usage:
        cmm = CognitiveMemoryManager(stm=redis_store, episodic=hybrid_mem, wisdom=vault)
        await cmm.compact_stm_to_episodic("ch_123", "user_001")
        await cmm.distill_episodic_to_knowledge("user_001")
        await cmm.crystallize_knowledge_to_wisdom("user_001")
        context = cmm.prime_with_wisdom("user_001")
    """

    def __init__(
        self,
        stm=None,          # RedisSTMStore
        episodic=None,      # HybridMemory / ILongTermMemory
        wisdom=None,        # WisdomVault
    ):
        self._stm = stm
        self._episodic = episodic
        self._wisdom = wisdom

    # ═════════════════════════════════════════════════════
    # D → I : Data to Information (STM → Episodic)
    # 對話壓縮 → 情節記憶
    # ═════════════════════════════════════════════════════

    async def compact_stm_to_episodic(
        self,
        channel_id: str,
        user_id: str,
    ) -> Optional[str]:
        """
        Compress raw STM messages into a structured episodic entry.
        將原始 STM 訊息壓縮為結構化情節記憶條目。

        Unlike simple summarization, this extracts:
          - entities: mentioned tickers, people, events
          - decisions: any investment decisions discussed
          - sentiment: overall emotional tone
          - summary: compressed narrative

        Returns memory_id if successful.
        """
        if not self._stm or not self._episodic:
            logger.warning("CognitiveMemory: STM or Episodic not configured")
            return None

        messages = self._stm.get_all_and_clear(channel_id)
        if not messages:
            return None

        # Build transcript
        transcript = "\n".join(
            [f"[{m.role}] {m.content}" for m in messages]
        )

        # Use LLM to extract structured episode
        episode = await self._extract_episode(transcript)

        # Store in PostgreSQL
        memory_id = str(uuid.uuid4())
        try:
            metadata = {
                "source_type": "channel_conversation",
                "memory_tier": "episodic",
                "channel_id": channel_id,
                "message_count": len(messages),
                "entities": episode.get("entities", []),
                "decisions": episode.get("decisions", []),
                "sentiment": episode.get("sentiment", "neutral"),
                "compacted_at": datetime.now(timezone.utc).isoformat(),
            }

            self._episodic.add_memory(
                memory_id=memory_id,
                user_id=user_id,
                content=episode.get("summary", transcript[:500]),
                metadata=metadata,
            )

            logger.info(
                f"CognitiveMemory: D→I compacted {len(messages)} msgs "
                f"→ episode {memory_id} "
                f"(entities: {len(episode.get('entities', []))}, "
                f"decisions: {len(episode.get('decisions', []))})"
            )
            return memory_id

        except Exception as e:
            logger.error(f"CognitiveMemory: D→I storage failed: {e}")
            return None

    async def _extract_episode(self, transcript: str) -> Dict[str, Any]:
        """
        Use LLM (fast tier) to extract structured episode from transcript.
        使用快速 LLM 從對話記錄中萃取結構化情節。
        """
        try:
            from src.agents.factory import AgentFactory

            agent = AgentFactory.create_agent(
                "Sentiment", tier="fast", user_id=None, use_cache=True
            )

            prompt = (
                "分析以下對話記錄，回傳 JSON 格式的結構化摘要。\n"
                "**僅回傳 JSON，不要包含其他文字。**\n\n"
                "需要的欄位:\n"
                '- "summary": 2-3 句話的對話精華摘要\n'
                '- "entities": 提到的標的/公司/指標（陣列）\n'
                '- "decisions": 討論的投資決策（陣列）\n'
                '- "sentiment": 整體語氣 ("bullish"/"bearish"/"neutral"/"cautious")\n'
                '- "key_numbers": 提到的關鍵數字（如 RSI, 價格）\n\n'
                f"對話記錄:\n{transcript[:2000]}"
            )

            result = agent.run({"user_request": prompt})
            raw = str(
                result.get("content") or result.get("output") or result
                if isinstance(result, dict)
                else result
            )

            # Parse JSON from response
            return self._parse_json_response(raw)

        except Exception as e:
            logger.error(f"CognitiveMemory: Episode extraction failed: {e}")
            return {"summary": transcript[:500], "entities": [], "decisions": []}

    # ═════════════════════════════════════════════════════
    # I → K : Information to Knowledge (Episodic → Knowledge)
    # 情節歸納 → 知識片段
    # ═════════════════════════════════════════════════════

    async def distill_episodic_to_knowledge(
        self,
        user_id: str,
        force: bool = False,
    ) -> List[str]:
        """
        Distill episodic memories into knowledge fragments.
        將情節記憶蒸餾為知識片段。

        Reads unprocessed episodic entries, identifies patterns,
        and creates higher-level knowledge fragments.

        Returns list of new knowledge memory_ids.
        """
        if not self._episodic:
            return []

        # Get recent episodic entries
        episodes = self._get_episodic_entries(user_id)

        if not force and len(episodes) < EPISODIC_DISTILL_THRESHOLD:
            logger.debug(
                f"CognitiveMemory: {len(episodes)} episodes "
                f"< {EPISODIC_DISTILL_THRESHOLD} threshold, skipping"
            )
            return []

        # Use LLM to find patterns across episodes
        knowledge_fragments = await self._extract_knowledge(episodes, user_id)

        # Store knowledge fragments
        new_ids = []
        for fragment in knowledge_fragments:
            kid = str(uuid.uuid4())
            try:
                self._episodic.add_memory(
                    memory_id=kid,
                    user_id=user_id,
                    content=fragment["insight"],
                    metadata={
                        "source_type": "knowledge_distillation",
                        "memory_tier": "knowledge",
                        "category": fragment.get("category", "general"),
                        "evidence_episodes": fragment.get("episode_ids", []),
                        "confidence": fragment.get("confidence", 0.5),
                        "distilled_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                new_ids.append(kid)
            except Exception as e:
                logger.error(f"CognitiveMemory: I→K storage failed: {e}")

        logger.info(
            f"CognitiveMemory: I→K distilled {len(episodes)} episodes "
            f"→ {len(new_ids)} knowledge fragments"
        )
        return new_ids

    async def _extract_knowledge(
        self, episodes: List[Dict], user_id: str
    ) -> List[Dict]:
        """
        Use LLM (smart tier) to identify patterns across episodes.
        使用 smart LLM 識別跨情節的模式。
        """
        try:
            from src.agents.factory import AgentFactory

            agent = AgentFactory.create_agent(
                "Conversation", tier="smart", user_id=user_id, use_cache=True
            )

            # Build episodes digest
            episodes_text = "\n\n".join(
                [
                    f"Episode {i+1} ({e.get('metadata', {}).get('compacted_at', 'N/A')}):\n"
                    f"{e['content']}"
                    for i, e in enumerate(episodes[:30])  # Cap input
                ]
            )

            prompt = (
                "你是一位認知科學家。分析以下投資對話的情節記憶，\n"
                "找出重複出現的**模式、偏好和行為規律**。\n\n"
                "**回傳 JSON 陣列**，每個元素包含:\n"
                '- "insight": 歸納出的知識/規律（一句話）\n'
                '- "category": 分類 ("risk_profile"/"market_patterns"/"decision_habits"/"ticker_insights")\n'
                '- "confidence": 信心度 0.0~1.0（根據支持的 episode 數量）\n'
                '- "episode_ids": 支持這個結論的 episode 編號（陣列）\n\n'
                "只回傳 JSON 陣列，不要其他文字。\n\n"
                f"情節記憶:\n{episodes_text[:3000]}"
            )

            result = agent.run({"user_request": prompt})
            raw = str(
                result.get("content") or result.get("output") or result
                if isinstance(result, dict)
                else result
            )

            parsed = self._parse_json_response(raw)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict) and "insights" in parsed:
                return parsed["insights"]
            return []

        except Exception as e:
            logger.error(f"CognitiveMemory: Knowledge extraction failed: {e}")
            return []

    # ═════════════════════════════════════════════════════
    # K → W : Knowledge to Wisdom (PG → Volume Files)
    # 知識結晶 → 智慧原則
    # ═════════════════════════════════════════════════════

    async def crystallize_knowledge_to_wisdom(
        self,
        user_id: str,
        force: bool = False,
    ) -> int:
        """
        Crystallize knowledge fragments into wisdom principles.
        將知識片段結晶為智慧原則。

        Reads knowledge-tier entries from PostgreSQL,
        synthesizes them into high-level principles,
        and writes to WisdomVault (file system).

        Returns count of new/updated wisdom entries.
        """
        if not self._episodic or not self._wisdom:
            return 0

        # Get knowledge-tier entries
        knowledge = self._get_knowledge_entries(user_id)

        if not force and len(knowledge) < KNOWLEDGE_CRYSTALLIZE_THRESHOLD:
            logger.debug(
                f"CognitiveMemory: {len(knowledge)} knowledge frags "
                f"< {KNOWLEDGE_CRYSTALLIZE_THRESHOLD} threshold, skipping"
            )
            return 0

        # Group by category
        by_category: Dict[str, List[Dict]] = {}
        for k in knowledge:
            cat = k.get("metadata", {}).get("category", "general")
            by_category.setdefault(cat, []).append(k)

        # Crystallize each category
        total_new = 0
        for category, fragments in by_category.items():
            wisdom_entries = await self._synthesize_wisdom(
                fragments, category, user_id
            )
            for entry in wisdom_entries:
                source_ids = [
                    f.get("id", "") for f in fragments[:5]
                ]
                self._wisdom.store_wisdom(
                    user_id=user_id,
                    category=category,
                    principle=entry["principle"],
                    confidence=entry.get("confidence", 0.6),
                    evidence_count=len(fragments),
                    tags=entry.get("tags", []),
                    source_episodes=source_ids,
                )
                total_new += 1

        logger.info(
            f"CognitiveMemory: K→W crystallized {len(knowledge)} knowledge "
            f"→ {total_new} wisdom principles for {user_id}"
        )
        return total_new

    async def _synthesize_wisdom(
        self,
        fragments: List[Dict],
        category: str,
        user_id: str,
    ) -> List[Dict]:
        """
        Use LLM (smart tier) to synthesize knowledge into wisdom.
        使用 smart LLM 將知識合成為智慧。
        """
        try:
            from src.agents.factory import AgentFactory

            agent = AgentFactory.create_agent(
                "Conversation", tier="smart", user_id=user_id, use_cache=True
            )

            knowledge_text = "\n".join(
                [f"- {f['content']}" for f in fragments[:20]]
            )

            cat_instruction = {
                "risk_profile": "歸納此使用者的風險偏好和容忍度",
                "market_patterns": "歸納此使用者觀察到的市場規律",
                "decision_habits": "歸納此使用者的決策行為模式",
                "ticker_insights": "歸納此使用者對個股的累積觀點",
            }.get(category, "歸納核心原則")

            prompt = (
                f"你是認知科學家。以下是關於 '{category}' 的知識片段。\n"
                f"請{cat_instruction}。\n\n"
                "將多個相似的知識片段**合併成一條抽象原則**。\n"
                "原則應該是永恆的、不依賴特定時間的觀察。\n\n"
                "**回傳 JSON 陣列**，每元素:\n"
                '- "principle": 一條簡潔的智慧原則\n'
                '- "confidence": 信心度 0.0~1.0\n'
                '- "tags": 關鍵標籤（陣列）\n\n'
                "只回傳 JSON，不要其他文字。\n\n"
                f"知識片段:\n{knowledge_text[:2000]}"
            )

            result = agent.run({"user_request": prompt})
            raw = str(
                result.get("content") or result.get("output") or result
                if isinstance(result, dict)
                else result
            )

            parsed = self._parse_json_response(raw)
            if isinstance(parsed, list):
                return parsed
            return []

        except Exception as e:
            logger.error(f"CognitiveMemory: Wisdom synthesis failed: {e}")
            return []

    # ═════════════════════════════════════════════════════
    # Prime: Wisdom → Context Injection
    # 智慧 → 上下文注入
    # ═════════════════════════════════════════════════════

    def prime_with_wisdom(self, user_id: str) -> str:
        """
        Load wisdom principles for system prompt injection.
        載入智慧原則供 system prompt 注入。

        This is called at agent startup to inject crystallized
        intelligence into the conversation context —
        like how human long-term semantic memory primes
        working memory automatically.
        """
        if not self._wisdom:
            return ""

        try:
            return self._wisdom.get_wisdom_summary(user_id)
        except Exception as e:
            logger.error(f"CognitiveMemory: Wisdom priming failed: {e}")
            return ""

    # ═════════════════════════════════════════════════════
    # Full Pipeline: Run All Stages
    # ═════════════════════════════════════════════════════

    async def run_full_pipeline(
        self,
        channel_id: str,
        user_id: str,
    ) -> Dict[str, Any]:
        """
        Run the complete D→I→K→W pipeline.
        執行完整的 D→I→K→W 管線。

        Typically called by a scheduled job or after compaction threshold.
        """
        results = {
            "episodic_id": None,
            "knowledge_ids": [],
            "wisdom_count": 0,
        }

        # D→I
        results["episodic_id"] = await self.compact_stm_to_episodic(
            channel_id, user_id
        )

        # I→K (check threshold internally)
        results["knowledge_ids"] = await self.distill_episodic_to_knowledge(
            user_id
        )

        # K→W (check threshold internally)
        results["wisdom_count"] = await self.crystallize_knowledge_to_wisdom(
            user_id
        )

        logger.info(f"CognitiveMemory: Full pipeline results: {results}")
        return results

    # ═════════════════════════════════════════════════════
    # Helpers
    # ═════════════════════════════════════════════════════

    def _get_episodic_entries(self, user_id: str) -> List[Dict]:
        """Fetch episodic-tier entries from PostgreSQL."""
        if not self._episodic:
            return []
        try:
            # Search for episodic entries (use keyword search as fallback)
            results = self._episodic.search(
                query_text="episodic",
                user_id=user_id,
                limit=100,
            )
            return [
                r for r in results
                if isinstance(r.get("metadata"), dict)
                and r["metadata"].get("memory_tier") == "episodic"
            ]
        except Exception as e:
            logger.error(f"CognitiveMemory: Failed to fetch episodes: {e}")
            return []

    def _get_knowledge_entries(self, user_id: str) -> List[Dict]:
        """Fetch knowledge-tier entries from PostgreSQL."""
        if not self._episodic:
            return []
        try:
            results = self._episodic.search(
                query_text="knowledge",
                user_id=user_id,
                limit=100,
            )
            return [
                r for r in results
                if isinstance(r.get("metadata"), dict)
                and r["metadata"].get("memory_tier") == "knowledge"
            ]
        except Exception as e:
            logger.error(f"CognitiveMemory: Failed to fetch knowledge: {e}")
            return []

    @staticmethod
    def _parse_json_response(raw: str) -> Any:
        """Parse JSON from LLM response, handling common formatting issues."""
        # Strip markdown code fences
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            # Remove first and last lines (fences)
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Try to find JSON block
            import re
            json_match = re.search(r'[\[{].*[\]}]', cleaned, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass

        logger.warning(f"CognitiveMemory: Failed to parse JSON from: {raw[:200]}...")
        return {"summary": raw[:500], "entities": [], "decisions": []}
