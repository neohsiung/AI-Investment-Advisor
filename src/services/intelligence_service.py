"""
IntelligenceService — 使用 Tavily + LLM 生成繁體中文市場情報
"""
import asyncio
import httpx
import json
from typing import Optional
from src.utils.logger import setup_logger
from src.domain.interfaces import Message, LLMConfig
from src.infrastructure.llm.llm_gateway import LLMGatewayFactory, RetryLLMGateway, LoggingLLMGateway
from src.services.settings_service import SettingsService  # pre-existing missing import fix

logger = setup_logger("IntelligenceService")

class IntelligenceService:
    def __init__(self, settings_service: Optional[SettingsService] = None, user_id: str = None):
        self.user_id = user_id or "system"
        self.settings = settings_service or SettingsService(user_id=self.user_id)
        self._llm_gateway = self._create_gateway()

    def _create_gateway(self):
        """建立符合標準規範的 LLM 閘道，包含重試與計費監控"""
        provider = self.settings.get_setting("AI_PROVIDER", "OpenRouter")
        inner = LLMGatewayFactory.create(provider)
        retrying = RetryLLMGateway(inner=inner, max_retries=2)
        return LoggingLLMGateway(
            inner=retrying,
            agent_name="IntelligenceService",
            tier="smart", # 預設智慧型，權限不足時 gateway 會自動降級
            user_id=self.user_id
        )

    async def get_latest_briefing(self) -> dict:
        """從快取讀取最新情報 (毫秒級)"""
        # Step 1: 從 Settings 讀取快取 JSON
        cached = self.settings.get_setting("cached_intelligence_briefing")
        timestamp = self.settings.get_setting("last_intelligence_timestamp")
        
        if cached:
            # v2.2: Ensure the UI knows how fresh this data is
            if isinstance(cached, str):
                try:
                    cached = json.loads(cached)
                except Exception as e:
                    logger.warning(f"Failed to parse cached intelligence: {e}")
            
            if isinstance(cached, dict):
                if timestamp:
                    cached["observation_window"] = f"UPDATED: {timestamp}"
                return cached
            
            # If we reach here, it was either non-JSON string or non-dict
            logger.warning("Cached intelligence is invalid format. Falling back.")
            
        # Step 2: Fallback - 如果沒快取，則發送一個「生成中」的提示
        return {
            "executive_summary": "市場情報正在背景生成中，請稍候再試...",
            "recommendation": "系統初次啟動或正在更新數據。",
            "ai_note": "BACKGROUND_SYNC_PENDING",
            "observation_window": "INITIALIZING",
            "sentiment_metrics": [
                {"label": "處理進度", "score": 50.0, "trend": "stable"}
            ]
        }

    async def compute_briefing(self) -> dict:
        """核心運算邏輯：真正執行 Tavily 搜尋與 LLM 生成 (耗時數十秒)"""
        tavily_key = self.settings.get_setting("source_tavily_api_key")
        api_key = self.settings.get_setting("API_KEY")
        
        # Use tier-aware routing (smart tier for intelligence)
        from src.infrastructure.llm.tier_config import SettingsAwareModelRouter, TierConfig
        from src.repositories.settings_repository import AlchemySettingsRepository
        settings_repo = AlchemySettingsRepository()
        model_router = SettingsAwareModelRouter(settings_repo)
        if self.user_id:
            model = model_router.get_model(self.user_id, "smart")
        else:
            tier_config = TierConfig()
            model = tier_config.resolve("smart")
        
        provider = self.settings.get_setting("AI_PROVIDER", "OpenRouter").lower()

        if not api_key:
            return self._fallback_error("未配置 AI API Key，請前往設定頁面完成配置。")

        # Step 1: Tavily 搜尋
        news_items = []
        if tavily_key:
            news_items = await self._tavily_search(tavily_key)
        else:
            logger.warning("Missing Tavily API Key, skipping search.")

        # Step 2: 整合現有持倉資訊 (Mocked for now or fetched from Repo)
        positions_summary = self._get_positions_summary()

        # Step 3: LLM 生成報告 (強制繁體中文)
        try:
            briefing = await self._llm_generate(news_items, positions_summary)
            return briefing
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            return self._fallback_error(f"情報生成途中發生錯誤：{str(e)}")

    async def _tavily_search(self, api_key: str) -> list:
        """呼叫 Tavily 搜尋最新市場事件"""
        queries = ["美股市場今日重要事件", "聯準會政策最新動態", "科技股龍頭財報分析", "Crypto Market Sentiment"]
        results = []
        async with httpx.AsyncClient(timeout=10) as client:
            # Parallel search for efficiency
            tasks = [client.post(
                "https://api.tavily.com/search",
                json={"api_key": api_key, "query": q, "max_results": 3, "search_depth": "basic"}
            ) for q in queries]
            
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            for resp in responses:
                if isinstance(resp, httpx.Response) and resp.status_code == 200:
                    results.extend(resp.json().get("results", []))
        
        return results[:8]

    def _get_positions_summary(self) -> str:
        """從 DB 取得當前持倉摘要"""
        try:
            from src.repositories.transaction_repository import AlchemyTransactionRepository
            repo = AlchemyTransactionRepository()
            transactions = repo.get_all_by_user(self.user_id)
            if not transactions:
                return "當前尚未有任何持倉數據。"
            import re
            tickers = list(set([re.sub(r'[*_]', '', t.ticker) for t in transactions]))
            return f"當前關鍵持倉標的包括：{', '.join(tickers[:15])}。請針對這些標的與目前市場情緒進行關聯分析。"
        except Exception as e:
            logger.warning(f"Failed to fetch transactions for intelligence: {e}")
            return "無法取得持倉資訊。"

    async def _llm_generate(self, news: list, positions: str) -> dict:
        """用 LLM 生成繁體中文情報摘要 (透過標準 Gateway)"""
        news_text = "\n".join([f"- {n.get('title', '')}: {n.get('content', '')[:300]}" for n in news])
        
        system_prompt = "你是一位專業的台灣機構投資人首席投資官（CIO）助理。你擅長從繁雜的新聞中提取對投資組合有價值的洞見。"
        prompt = f"""請根據以下市場新聞和投資組合資訊，用**繁體中文**撰寫一份簡潔的市場情報簡報（Intelligence Briefing）。

【當前持倉摘要】
{positions}

【最新市場焦點事件】
{news_text}

---
【輸出要求】
1. 必須嚴格遵守以下 JSON 格式回傳。
2. 所有內容文字必須使用「繁體中文」（台灣用語習慣）。
3. executive_summary 需在 250 字內，總結今日市場對投資組合的最重要影響。
4. recommendation 需具體，指示明確的操作方向。
5. ai_note 應提供具前瞻性的觀察。
6. sentiment_metrics 需包含三個維度：多頭動能、避險需求、波動風險。數值為 0-100。

【輸出 JSON 範例】
{{
  "executive_summary": "今日市場受到...影響，預計...",
  "recommendation": "建議保持...",
  "ai_note": "觀察到...",
  "observation_window": "ACTIVE SESSION",
  "sentiment_metrics": [
    {{"label": "市場多頭動能", "score": 65, "trend": "up"}},
    {{"label": "避險需求", "score": 30, "trend": "stable"}},
    {{"label": "波動風險", "score": 45, "trend": "down"}}
  ]
}}
"""
        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=prompt)
        ]
        
        config = LLMConfig(
            provider=self.settings.get_setting("AI_PROVIDER", "OpenRouter"),
            model=model,  # Already resolved with tier-aware routing above
            api_key=self.settings.get_setting("API_KEY", ""),
            temperature=0.3,
            timeout_seconds=45
        )

        content = await self._llm_gateway.chat(messages, config)
        
        if not content:
            return self._fallback_error("AI 回傳內容為空。")

        # Ensure it's valid JSON
        try:
            # Remove markdown code blocks if present
            clean_content = content
            if "```json" in content:
                clean_content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                clean_content = content.split("```")[1].split("```")[0].strip()
                
            result = json.loads(clean_content)
            
            # 如果是降級生成的，保留 LLM Gateway 可能添加的筆記 (雖然 JSON 可能會被破壞，我們試著合併)
            if "*(注意" in content and "ai_note" in result:
                result["ai_note"] = "(FALLBACK) " + result["ai_note"]
                
            # Keep original fields if missing in AI response
            if "observation_window" not in result: result["observation_window"] = "ANALYZED"
            return result
        except Exception as e:
            logger.error(f"Failed to parse AI JSON: {content}")
            # 如果解析失敗但有原始文字，至少回傳摘要
            return self._fallback_error(f"解析 AI 回報時發生錯誤，原始內容：{content[:100]}...")

    def _fallback_error(self, message: str) -> dict:
        return {
            "executive_summary": message,
            "recommendation": "請檢查系統配置或稍後再試。",
            "ai_note": "ERROR_LOGGED",
            "observation_window": "OFFLINE",
            "sentiment_metrics": [
                {"label": "系統狀態", "score": 0, "trend": "stable"}
            ]
        }
