"""
IntelligenceService — 使用 Tavily + LLM 生成繁體中文市場情報
"""
import asyncio
import httpx
import json
from typing import Optional, Dict, Any, List
from src.services.settings_service import SettingsService
from src.utils.logger import setup_logger

logger = setup_logger("IntelligenceService")

class IntelligenceService:
    def __init__(self, settings_service: Optional[SettingsService] = None, user_id: str = None):
        self.user_id = user_id or "system"
        self.settings = settings_service or SettingsService(user_id=self.user_id)

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
                except:
                    pass
            
            if timestamp:
                cached["observation_window"] = f"UPDATED: {timestamp}"
            return cached
            
        # Step 2: Fallback - 如果沒快取，則發送一個「生成中」的提示
        return {
            "executive_summary": "市場情報正在背景生成中，請稍候再試...",
            "recommendation": "系統初次啟動或正在更新數據。",
            "ai_note": "BACKGROUND_SYNC_PENDING",
            "observation_window": "INITIALIZING",
            "sentiment_metrics": [
                {"label": "處理進度", "value": 50, "color": "bg-secondary"}
            ]
        }

    async def compute_briefing(self) -> dict:
        """核心運算邏輯：真正執行 Tavily 搜尋與 LLM 生成 (耗時數十秒)"""
        tavily_key = self.settings.get_setting("source_tavily_api_key")
        api_key = self.settings.get_setting("API_KEY")
        model = self.settings.get_setting("AI_MODEL_SMART", "google/gemini-2.0-pro")
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
            briefing = await self._llm_generate(api_key, model, provider, news_items, positions_summary)
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
            from src.repositories.postgres_repositories import AlchemyTransactionRepository
            repo = AlchemyTransactionRepository(user_id=self.user_id)
            transactions = repo.get_all()
            if not transactions:
                return "當前尚未有任何持倉數據。"
            tickers = list(set([t.ticker for t in transactions]))
            return f"當前關鍵持倉標的包括：{', '.join(tickers[:15])}。請針對這些標的與目前市場情緒進行關聯分析。"
        except Exception as e:
            logger.warning(f"Failed to fetch transactions for intelligence: {e}")
            return "無法取得持倉資訊。"

    async def _llm_generate(self, api_key: str, model: str, provider: str, news: list, positions: str) -> dict:
        """用 LLM 生成繁體中文情報摘要"""
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
    {{"label": "市場多頭動能", "value": 65, "color": "bg-secondary"}},
    {{"label": "避險需求", "value": 30, "color": "bg-tertiary"}},
    {{"label": "波動風險", "value": 45, "color": "bg-error"}}
  ]
}}
"""

        endpoint = "https://openrouter.ai/api/v1/chat/completions"
        if provider == "google":
            endpoint = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/neohsiung",
            "X-Title": "Investment Advisor Swarm"
        }

        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.post(
                endpoint,
                headers=headers,
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    "response_format": {"type": "json_object"}
                }
            )
            
            if resp.status_code != 200:
                logger.error(f"LLM API Error: {resp.text}")
                return self._fallback_error(f"AI 供應商回傳錯誤 ({resp.status_code})")
                
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            
            # Ensure it's valid JSON
            try:
                # Remove markdown code blocks if present
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0].strip()
                    
                result = json.loads(content)
                # Keep original fields if missing in AI response
                if "observation_window" not in result: result["observation_window"] = "ANALYZED"
                return result
            except Exception as e:
                logger.error(f"Failed to parse AI JSON: {content}")
                return self._fallback_error("AI 回傳格式異常，無法解析。")

    def _fallback_error(self, message: str) -> dict:
        return {
            "executive_summary": message,
            "recommendation": "請檢查系統配置或稍後再試。",
            "ai_note": "ERROR_LOGGED",
            "observation_window": "OFFLINE",
            "sentiment_metrics": [
                {"label": "系統狀態", "value": 0, "color": "bg-error"}
            ]
        }
