"""
Conversation Agent — Channel-Facing Conversational AI.
對話 Agent — 頻道對話 AI。

Specialized agent for interactive Q&A on Telegram/LINE channels.
Uses:
  - PersonaProvider for personality injection
  - ChannelMemoryManager for short-term + long-term context
  - MCP Skills for real-time data retrieval

遵循規範:
  - 規範一 (Clean Architecture): 繼承 BaseAgent 抽象
  - 規範四 (模組化設計): 獨立可單元測試
  - 規範五 (Context Assembly Engine): 整合 persona + memory + tools
"""

import asyncio
import logging
import os
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class ConversationAgent:
    """
    Channel-facing conversational AI agent with persona and memory.
    具有人格和記憶的頻道對話 AI Agent。

    Unlike BaseAgent which processes batch context, ConversationAgent
    is optimized for interactive, multi-turn conversations.
    """

    def __init__(
        self,
        user_id: str,
        channel_type: str = "",
        channel_id: str = "",
        persona_provider=None,
        channel_memory=None,
        tier: str = "smart",
    ):
        """
        Args:
            user_id: System user ID
            channel_type: "telegram" | "line"
            channel_id: Channel-specific user/chat ID
            persona_provider: PersonaProvider instance
            channel_memory: ChannelMemoryManager instance
            tier: LLM tier to use ("fast", "smart", "advanced")
        """
        self.user_id = user_id
        self.channel_type = channel_type
        self.channel_id = channel_id
        self.tier = tier

        # Load persona
        self._persona = None
        if persona_provider:
            self._persona = persona_provider.get_or_default("conversation")

        # Memory manager (Redis STM + pgvector LTM)
        self._channel_memory = channel_memory
        self._memory = channel_memory # Keep alias for compatibility if needed elsewhere
        self._wisdom_context = ""  # Cached wisdom for this user

        # Phase 2 Components
        from src.agents.skill_router import SkillRouter
        from src.agents.conversation_task_decomposer import ConversationTaskDecomposer
        from src.agents.swarm.swarm_orchestrator import SwarmOrchestrator
        from src.infrastructure.memory.wisdom_vault import WisdomVault
        from src.services.experience_replay_service import ExperienceReplayService
        from src.agents.skills.gap_detector import GapDetector
        from src.agents.skills.skill_scaffolder import SkillScaffolder
        
        self._skill_router = SkillRouter(user_id=self.user_id)
        self._decomposer = ConversationTaskDecomposer(user_id=self.user_id)
        self._swarm = SwarmOrchestrator()
        self._swarm.user_id = self.user_id # Ensure user_id is set
        
        self._wisdom_vault = WisdomVault()
        self._replay_service = ExperienceReplayService(
            user_id=self.user_id,
            wisdom_vault=self._wisdom_vault
        )

        # [Phase 5A] Unified Memory
        from src.services.settings_service import SettingsService
        from src.services.unified_memory_service import UnifiedMemoryService
        
        self._settings_service = SettingsService(user_id=self.user_id)
        self._unified_memory = UnifiedMemoryService(
            memory_manager=self._channel_memory,
            settings_service=self._settings_service
        )

        # [Phase 4] Skill Auto-Expansion
        self._gap_detector = GapDetector()
        self._skill_scaffolder = SkillScaffolder()

        # [Phase 5C] Evolution Observability
        from src.services.evolution_metrics import EvolutionMetrics
        self._evolution_metrics = EvolutionMetrics()

        # Core BaseAgent (Lazy-init)
        self._agent = None
        self._tools_registered = False

    async def _ensure_agent(self):
        """Lazy-init the BaseAgent instance and register MCP skills."""
        if self._agent is not None:
            return

        from src.agents.factory import AgentFactory

        self._agent = AgentFactory.create_agent(
            "Conversation",
            tier=self.tier,
            user_id=self.user_id,
            use_cache=True,
            persona=self._persona,
        )

        # Ensure channel-facing skills are bound
        if not self._tools_registered:
            await self._register_channel_skills()
            self._tools_registered = True

        # [Cognitive Architecture] Prime with crystallized wisdom
        # 認知架構: 從智慧金庫注入結晶化知識
        if not self._wisdom_context and self._memory:
            self._wisdom_context = self._memory.get_wisdom_context(
                self.user_id
            )

    async def _register_channel_skills(self):
        """
        Register MCP skills and external MCP tools relevant to channel conversations dynamically.
        v8.2: Added B2C user-isolated external MCP discovery.
        """
        
        
                
        # 1. Bind local skills (Registry-based)
                
        # 2. [Task 8.2] Discover and bind External MCP Servers (Per-user settings)
        try:
            # We use the already initialized SettingsService
            mcp_servers_json = self._settings_service.get_setting("external_mcp_servers", "[]")
            import json
            if isinstance(mcp_servers_json, str):
                try:
                    mcp_urls = json.loads(mcp_servers_json)
                except json.JSONDecodeError:
                    mcp_urls = []
            else:
                mcp_urls = mcp_servers_json if isinstance(mcp_servers_json, list) else []

            if mcp_urls:
                from src.tools.mcp_client_adapter import get_mcp_client
                for url in mcp_urls:
                    try:
                        client = await get_mcp_client(url, self.user_id)
                        tools = client.list_tools()
                        for tool in tools:
                            from src.tools.mcp_server import McpTool
                            # Wrap the tool call
                            mcp_tool = McpTool(
                                name=f"ext_{tool.name}", # Namespace external tools
                                description=f"[External] {tool.description}",
                                func=functools.partial(client.call_tool, tool.name)
                            )
                            self._agent.register_tool(mcp_tool)
                        logger.info(f"ConversationAgent ({self.user_id}): Bound {len(tools)} tools from {url}")
                    except Exception as e:
                        logger.warning(f"ConversationAgent: Failed to bind external MCP {url}: {e}")
        except Exception as e:
            logger.error(f"ConversationAgent: Error during external MCP discovery: {e}")
        
        logger.info("ConversationAgent: Skills and External tools bound via Registry/Gateway.")

    async def respond(
        self,
        user_message: str,
        channel_context: Dict[str, Any] = None,
    ) -> str:
        """
        Generate a response to user's message with full context.
        使用完整上下文產生回覆。

        Flow:
          1. Load short-term memory (recent messages)
          2. Search long-term memory for relevant context
          3. Build messages with persona + memory
          4. Run LLM with tool access
          5. Store conversation turn
          6. Check compaction threshold

        Args:
            user_message: The user's text input
            channel_context: Additional channel metadata

        Returns:
            Agent's response text
        """
        await self._ensure_agent()

        try:
            # 0. [Phase 3 & 5A] Check persistent pending clarification from unified memory
            self._pending_clarification = self._unified_memory.get_unified_metadata(
                self.user_id, "pending_clarification"
            )

            # 1. [Phase 5A] Fetch unified short-term memory (STM) across channels
            recent_messages = self._unified_memory.get_unified_short_term(
                self.user_id, limit_per_channel=5
            )

            # 2. Search long-term memory
            relevant_memories = []
            if self._memory:
                relevant_memories = self._memory.search_long_term(
                    user_message, self.user_id, limit=3
                )

            # 3. Build context
            # [Phase 3] Load crystallized wisdom
            self._wisdom_context = self._wisdom_vault.get_wisdom_summary(self.user_id)
            
            context = self._build_conversation_context(
                user_message, recent_messages, relevant_memories, channel_context
            )
            # Inject wisdom into context for prompt template expansion
            context["wisdom_context"] = self._wisdom_context

            # [Fix 3X-2] Handle confirmation if there's a pending clarification
            if self._pending_clarification and user_message:
                conf = self._check_confirmation(user_message)
                if conf == "yes":
                    draft = self._pending_clarification
                    self._replay_service.record_feedback(
                        self.user_id,
                        draft["category"],
                        draft["principle"],
                        draft.get("conflicts_with")
                    )
                    logger.info(f"ConversationAgent: Wisdom confirmed and stored: {draft['principle']}")
                    self._channel_memory.delete_metadata(self.channel_id, "pending_clarification")
                    self._pending_clarification = None
                    # Optionally we could return an immediate response, but we continue 
                    # to process the actual user message.
                elif conf == "no":
                    logger.info("ConversationAgent: Wisdom rejected by user.")
                    self._channel_memory.delete_metadata(self.channel_id, "pending_clarification")
                    self._pending_clarification = None

            # --- Phase 2: Team Agent Flow ---
            
            # 3.1. Fast Path: Skill Router
            direct_result = await self._skill_router.route(user_message, context)
            if direct_result:
                logger.info(f"ConversationAgent: SkillRouter match! Returning direct result.")
                await self._store_memory(user_message, direct_result)
                return direct_result

            # 3.2. Decomposer Path: Swarm / Team Mode
            sub_tasks = await self._decomposer.decompose(user_message, context.get("conversation_history", ""))
            
            if sub_tasks and len(sub_tasks) > 1:
                logger.info(f"ConversationAgent: Team Mode activated with {len(sub_tasks)} tasks")
                team_results = await self._swarm.run_subtasks(sub_tasks, context)
                result = await self._synthesize_team_result(user_message, team_results, context)
            else:
                # 4. [Phase 4] Gap Detection before Single Mode
                gap_confirmation = self._check_gap_confirmation(user_message)
                if gap_confirmation:
                    result = await self._execute_gap_confirmation(gap_confirmation)
                else:
                    gap_report = await self._gap_detector.detect(
                        user_message, self._get_skill_metadata(), context
                    )
                    if gap_report.is_gap:
                        result = await self._handle_gap(user_message, gap_report, context)
                    else:
                        logger.info("ConversationAgent: Falling back to Single Mode")
                        result = await self._run_agent_async(context)

            # 5. [Phase 3] Feedback Distillation
            # Awaiting to allow appending [智取] or clarification question to the response
            feedback_suffix = await self._handle_feedback_loop(user_message, result)
            if feedback_suffix:
                result += feedback_suffix
            
            # [Fix 3X-1] Store memory (STM) after Team/Single mode
            await self._store_memory(user_message, result)

            return result

        except Exception as e:
            logger.error(f"ConversationAgent.respond error: {e}", exc_info=True)
            return f"⚠️ 抱歉，處理您的訊息時發生錯誤。請稍後再試。"

    # ── Phase 4: Gap Detection Handlers ──────────────────────

    def _get_skill_metadata(self):
        """Get current registered skill metadata for gap detection."""
        try:
            from src.agents.skills.skill_loader import SkillLoader
            loader = SkillLoader()
            loader.discover_skills()
            return loader._metadata_cache
        except Exception:
            return {}

    def _check_gap_confirmation(self, user_message: str):
        """Check if user is confirming a pending gap scaffold request."""
        if not self._channel_memory:
            return None
        pending = self._channel_memory.get_metadata(self.channel_id, "pending_gap")
        if not pending:
            return None
        msg_lower = user_message.strip().lower()
        if msg_lower in ["建立", "是", "yes", "好", "確認", "create"]:
            return pending
        elif msg_lower in ["不要", "否", "no", "取消", "cancel"]:
            self._channel_memory.delete_metadata(self.channel_id, "pending_gap")
            return "rejected"
        return None

    async def _handle_gap(self, user_message: str, gap_report, context):
        """
        Handle a detected capability gap:
        1. Record gap in WisdomVault
        2. Answer with Single Mode (best effort)
        3. Suggest creating a new skill
        """
        from src.agents.skills.gap_detector import GapReport

        # 1. Record gap
        self._wisdom_vault.store_wisdom(
            self.user_id, "capability_gaps",
            f"缺少 Skill: {gap_report.suggested_skill_name} ({gap_report.reasoning})",
            confidence=0.6
        )
        self._evolution_metrics.record_event("gap_detected", {"skill": gap_report.suggested_skill_name})

        # 2. Best-effort answer
        result = await self._run_agent_async(context)

        # 3. Suggest skill creation
        result += (
            f"\n\n💡 **[能力偵測]** 我注意到您的問題可能需要新的分析工具"
            f" `{gap_report.suggested_skill_name}`。\n"
            f"📝 原因: {gap_report.reasoning}\n"
        )
        if gap_report.existing_similar:
            result += f"🔗 最接近的現有工具: `{gap_report.existing_similar}`\n"
        result += "是否要我自動建立此工具？（回覆 **建立** 確認 / **取消** 略過）"

        # 4. Store pending gap for confirmation
        if self._channel_memory:
            self._channel_memory.set_metadata(
                self.channel_id, "pending_gap", gap_report.to_dict()
            )

        return result

    async def _execute_gap_confirmation(self, pending):
        """Execute gap scaffold after user confirmation."""
        from src.agents.skills.gap_detector import GapReport
        

        if pending == "rejected":
            self._evolution_metrics.record_event("user_rejected_scaffold", {})
            return "✅ 已取消建立新工具。"

        try:
            gap = GapReport(**pending)
            from src.services.mcp_installation_guard import MCPBackgroundCheckService
            guard = MCPBackgroundCheckService(user_id=self.user_id)

            # [Phase 3] 1. Verify Purpose Alignment before generating code
            is_aligned, purpose_reason = await guard.verify_purpose_alignment(
                gap.suggested_skill_name, gap.reasoning, gap.reasoning
            )
            if not is_aligned:
                logger.warning(f"ConversationAgent: Purpose mismatch for {gap.suggested_skill_name}: {purpose_reason}")
                return f"🛡️ **[資安攔截]** 拒絕建立新工具 `{gap.suggested_skill_name}`。\n原因：{purpose_reason}"

            # [User Decision Q1] Generate impl with LLM
            impl_code = await self._generate_impl_code(gap)

            # Scaffold with generated code
            path = self._skill_scaffolder.scaffold(
                gap, user_context="", impl_code=impl_code
            )

            # [Phase 3] 2. Verify Security Clearance of generated code
            # Use the actual path returned by scaffold (usually in _pending/)
            impl_path = os.path.join(path, "impl.py")
            is_safe, sec_reason = await guard.verify_security_clearance(impl_path)
            if not is_safe:
                logger.error(f"ConversationAgent: Security breach in generated code: {sec_reason}")
                # [Phase 4] Cleanup malicious directory
                try:
                    import shutil
                    if os.path.exists(path):
                        shutil.rmtree(path)
                        logger.info(f"ConversationAgent: Malicious skill directory {path} deleted.")
                except Exception as cleanup_err:
                    logger.error(f"ConversationAgent: Failed to cleanup malicious directory: {cleanup_err}")
                
                return f"🛡️ **[資安攔截]** 自動產生的程式碼未通過背景調查。\n原因：{sec_reason}\n出於安全考量，已將產生的原始碼自動刪除。"

            # Smart Model review of generated code

            # Smart Model review of generated code
            review_result = await self._review_generated_impl(gap, impl_code)

            # Activate and hot-reload
            self._skill_scaffolder.approve_and_activate(gap.suggested_skill_name)
            self._evolution_metrics.record_event("skill_hot_reloaded", {"skill": gap.suggested_skill_name})

            # Clear pending
            if self._channel_memory:
                self._channel_memory.delete_metadata(self.channel_id, "pending_gap")

            logger.info(
                f"ConversationAgent: Skill '{gap.suggested_skill_name}' "
                f"auto-generated and activated."
            )

            result = (
                f"✅ 新工具 `{gap.suggested_skill_name}` 已自動建立並啟用！\n"
                f"📂 位置: `src/agents/skills/{gap.suggested_skill_name}/`\n"
            )
            if review_result:
                result += f"🔍 Smart Model 審查結果: {review_result}\n"
            result += "下次詢問相關問題時將自動使用此工具。"

            return result

        except Exception as e:
            logger.error(f"ConversationAgent: Gap scaffold failed: {e}")
            if self._channel_memory:
                self._channel_memory.delete_metadata(self.channel_id, "pending_gap")
            return f"⚠️ 建立新工具時發生錯誤: {e}"

    async def _generate_impl_code(self, gap) -> str:
        """Use Fast-tier LLM to generate skill implementation code."""
        try:
            import os
            from src.domain.interfaces import Message, LLMConfig
            from src.infrastructure.llm.llm_gateway import LLMGatewayFactory

            prompt = f"""Generate a Python skill implementation for an investment analysis agent.

Skill name: {gap.suggested_skill_name}
Category: {gap.suggested_category}
Purpose: {gap.reasoning}
Similar existing skill: {gap.existing_similar or 'None'}

Requirements:
- Function must be named `{gap.suggested_skill_name}(user_id: str, **kwargs) -> str`
- Include proper error handling with try/except
- Include logging with `logger = logging.getLogger(__name__)`
- Return a formatted string result
- Import only stdlib and src.* modules
- Do NOT use hardcoded API keys

Return ONLY the Python code, no explanations."""

            # [Phase 4] Multi-tenant isolation: Load credentials from SettingsService
            llm_settings = self._settings_service.get_all_settings()
            
            # Use tier-aware model routing
            from src.infrastructure.llm.tier_config import SettingsAwareModelRouter
            model_router = SettingsAwareModelRouter()
            
            provider = llm_settings.get("AI_PROVIDER", os.getenv("AI_PROVIDER", "OpenRouter"))
            
            # Use tier-aware routing (fast tier for code generation)
            from src.infrastructure.llm.tier_config import TierConfig
            tier_config = TierConfig()
            if self.user_id:
                model = model_router.get_model(self.user_id, "fast")
            else:
                model = tier_config.resolve("fast")
            api_key = llm_settings.get("API_KEY", os.getenv("API_KEY", ""))

            gateway = LLMGatewayFactory.create(provider)
            config = LLMConfig(
                provider=provider,
                model=model,
                api_key=api_key,
                temperature=0.2,
                max_tokens=1500,
            )
            messages = [
                Message(role="system", content="You are a Python code generator. Output only valid Python code."),
                Message(role="user", content=prompt),
            ]
            code = await gateway.chat(messages, config)
            # Strip markdown code fences
            code = code.replace("```python", "").replace("```", "").strip()
            return code
        except Exception as e:
            logger.warning(f"ConversationAgent: Impl generation failed, using stub: {e}")
            return ""

    async def _review_generated_impl(self, gap, impl_code: str) -> str:
        """Use Smart-tier LLM to review generated implementation for correctness."""
        if not impl_code:
            return "⚠️ Using stub implementation (manual review required)"
        try:
            import os
            from src.domain.interfaces import Message, LLMConfig
            from src.infrastructure.llm.llm_gateway import LLMGatewayFactory
            from src.utils.async_utils import to_thread

            prompt = f"""Review this auto-generated Python skill implementation for an investment analysis agent.

```python
{impl_code}
```

Check for:
1. Security issues (hardcoded secrets, SQL injection, unsafe eval)
2. Import errors (non-existent modules)
3. Logic correctness
4. Error handling completeness

Respond in ONE sentence: either "PASS: looks good" or "WARN: <specific issue>"."""
            # [Phase 4] Multi-tenant isolation: Load credentials from SettingsService
            llm_settings = self._settings_service.get_all_settings()
            
            # Use tier-aware model routing
            from src.infrastructure.llm.tier_config import SettingsAwareModelRouter
            model_router = SettingsAwareModelRouter()
            
            provider = llm_settings.get("AI_PROVIDER", os.getenv("AI_PROVIDER", "OpenRouter"))
            
            # Use tier-aware routing (smart tier for code review)
            from src.infrastructure.llm.tier_config import TierConfig
            tier_config = TierConfig()
            if self.user_id:
                model = model_router.get_model(self.user_id, "smart")
            else:
                model = tier_config.resolve("smart")
            api_key = llm_settings.get("API_KEY", os.getenv("API_KEY", ""))

            gateway = LLMGatewayFactory.create(provider)
            config = LLMConfig(
                provider=provider,
                model=model,
                api_key=api_key,
                temperature=0.0,
                max_tokens=200,
            )
            messages = [
                Message(role="user", content=prompt),
            ]
            review = await to_thread(gateway.chat, messages, config)
            return review.strip()
        except Exception as e:
            logger.warning(f"ConversationAgent: Review failed: {e}")
            return "⚠️ Review skipped due to error"

    async def _handle_feedback_loop(self, user_message: str, agent_response: str) -> str:
        """
        Extracts and records behavioral feedback from conversation turn.
        從對話中提煉並記錄行為回饋。 Returns a suffix to append to the response.
        """
        try:
            feedback = await self._replay_service.distill_feedback(
                user_message=user_message,
                last_ai_response=agent_response,
                user_id=self.user_id
            )
            
            if feedback:
                action = feedback.get("action")
                if action == "store":
                    # Directly record high-confidence wisdom
                    self._replay_service.record_feedback(
                        user_id=self.user_id,
                        category=feedback.get("category"),
                        principle=feedback.get("principle"),
                        confidence=feedback.get("confidence"),
                        conflicts_with=feedback.get("conflicts_with")
                    )
                    logger.info(f"ConversationAgent: Wisdom stored for {self.user_id}")
                    return "\n\n> [智取：已記錄您的偏好]"
                    
                elif action == "clarify":
                    # Middle-confidence: need clarification
                    question = feedback.get("question", "我注意到您可能對我的回覆方式有特殊偏向，請問我應該記住這個偏向嗎？")
                    
                    # [Fix 3X-2] Store draft in persistent metadata for confirmation in next turn
                    self._channel_memory.set_metadata(self.channel_id, "pending_clarification", feedback)
                    
                    logger.info(f"ConversationAgent: Clarification suggested and stored: {question}")
                    return f"\n\n💡 {question}"

        except Exception as e:
            logger.error(f"Feedback loop error: {e}")
        
        return ""

    def _check_confirmation(self, text: str) -> str:
        """[Fix 3X-2] Check if user message is a confirmation (yes/no)."""
        text = text.strip().lower()
        yes_keywords = ["是", "好", "可以", "沒問題", "沒錯", "對", "確定", "yes", "ok", "confirm", "y"]
        no_keywords = ["不", "否", "不用", "取消", "不要", "不要記", "no", "n", "cancel"]
        
        # Priority on 'no' if both present (conservative approach)
        if any(kw in text for kw in no_keywords):
            return "no"
        if any(kw in text for kw in yes_keywords):
            return "yes"
        return "unclear"

    async def _store_memory(self, user_msg: str, agent_res: str):
        """Helper to store turn in memory."""
        if self._memory:
            self._memory.append_short_term(
                self.channel_id, "user", user_msg, self.channel_type
            )
            self._memory.append_short_term(
                self.channel_id, "assistant", agent_res, self.channel_type
            )
            
            # [Fix B-3] Check compaction with error-safe task
            if self._memory.should_compact(self.channel_id):
                task = asyncio.create_task(
                    self._memory.compact_to_long_term(
                        self.channel_id, self.user_id
                    )
                )
                task.add_done_callback(self._on_compaction_done)

    @staticmethod
    def _on_compaction_done(task: asyncio.Task):
        """[Fix B-3] Log errors from background compaction tasks."""
        if task.exception():
            logger.error(f"ConversationAgent: Memory compaction failed: {task.exception()}")

    async def _synthesize_team_result(self, user_message: str, team_results: Dict[str, str], context: Dict[str, Any]) -> str:
        """
        Final synthesis of multiple sub-agent findings by the CIO.
        由 CIO 進行最終的多子 Agent 發現彙整。
        """
        self._ensure_agent()
        
        # Build synthesis context
        transcript = ""
        for tid, res in team_results.items():
            transcript += f"\n### Task ID: {tid}\n{res}\n"
        
        synthesis_context = context.copy()
        synthesis_context["council_transcript"] = transcript
        synthesis_context["report_focus"] = "Team Synthesis"
        synthesis_context["user_request"] = user_message # Ensure the synthesis knows the original goal
        
        # Run CIO agent for final synthesis
        from src.agents.factory import AgentFactory
        cio = AgentFactory.create_cio_agent(mode="daily", user_id=self.user_id)
        
        # Wrap sync run in to_thread
        from src.utils.async_utils import to_thread
        result = await to_thread(cio.run, synthesis_context)
        
        return str(result)

    def _build_conversation_context(
        self,
        user_message: str,
        recent_messages: List[Dict],
        relevant_memories: List[Dict],
        channel_context: Dict = None,
    ) -> Dict[str, Any]:
        """
        Build the full context for the LLM call.
        構建 LLM 調用的完整上下文。
        """
        context = {
            "user_message": user_message,
            "channel_type": self.channel_type,
            "user_id": self.user_id,
        }

        # Inject conversation history
        if recent_messages:
            history = "\n".join(
                [f"[{m['role']}] {m['content']}" for m in recent_messages[-6:]]
            )
            context["conversation_history"] = history

        # Inject relevant long-term memories
        if relevant_memories:
            mem_text = "\n".join(
                [f"- {m['content']}" for m in relevant_memories if m.get('content')]
            )
            context["relevant_memories"] = mem_text

        # [Cognitive Architecture] Inject crystallized wisdom
        # 認知架構: 注入結晶化智慧（類似人類語意記憶自動啟動工作記憶）
        if self._wisdom_context:
            context["wisdom_context"] = self._wisdom_context

        # Inject persona info
        if self._persona:
            context["persona_name"] = self._persona.display_name
            context["persona_tone"] = self._persona.tone

        if channel_context:
            context.update(channel_context)

        return context

    async def _run_agent_async(self, context: Dict[str, Any]) -> str:
        """
        Run the underlying BaseAgent in async context.
        在異步上下文中執行底層 BaseAgent。
        """
        from src.utils.async_utils import to_thread

        # BaseAgent.run() is synchronous — wrap in thread
        result = await to_thread(self._agent.run, context)

        if isinstance(result, dict):
            return str(
                result.get("content")
                or result.get("output")
                or result.get("response")
                or result
            )
        return str(result)
