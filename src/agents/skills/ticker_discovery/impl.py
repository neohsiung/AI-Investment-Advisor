import json
import re
import os
import logging
from typing import List, Dict, Any, Optional

from src.utils.logger import setup_logger
from src.services.search_service import InternetSearchService
from src.infrastructure.llm.llm_gateway import LLMGatewayFactory, LoggingLLMGateway
from src.domain.interfaces import Message, LLMConfig
from src.repositories.settings_repository import AlchemySettingsRepository

logger = setup_logger("skill_ticker_discovery")

async def ticker_discovery(
    user_id: str,
    strategy: str = "growth",
    sectors: List[str] = None
) -> str:
    """
    Ticker Discovery Skill — Automated search and filter for investment candidates.
    搜尋網際網路上的熱門或具潛力的投資標的，並透過 LLM 提取有效的股票代號。
    """
    logger.info(f"User {user_id} starting ticker discovery (Strategy: {strategy}, Sectors: {sectors})")
    
    try:
        # 1. Initialize Search
        search_svc = InternetSearchService(user_id=user_id)
        
        # 2. Construct Search Query
        sector_str = " ".join(sectors) if sectors else "high-potential"
        query = f"top {strategy} {sector_str} stocks to buy 2025 2026 analysis ticker"
        
        # 3. Search
        search_results = await search_svc.search_financial_context(query, max_results=5)
        if not search_results:
            logger.warning(f"No search results for query: {query}")
            return json.dumps({"status": "no_results", "tickers": []})

        # 4. Extract Tickers via LLM (Fast Tier)
        context = "\n".join([f"- {r['title']}: {r['snippet']}" for r in search_results])
        
        settings_repo = AlchemySettingsRepository()
        # Fallback to env if DB key not set
        api_key = settings_repo.get(user_id, "source_gemini_api_key", os.environ.get("GEMINI_API_KEY"))
        
        if not api_key:
            logger.error(f"User {user_id} has no Gemini API key for ticker discovery.")
            return json.dumps({"status": "error", "error": "No Gemini API key found for extraction."})
            
        # Use simple config for extraction (tier-aware routing)
        from src.infrastructure.llm.tier_config import TierConfig
        tier_config = TierConfig()
        model = tier_config.resolve("fast")  # Fast & reliable for extraction
        
        config = LLMConfig(
            provider="gemini",
            model=model,
            api_key=api_key,
            temperature=0.0
        )
        
        gateway = LLMGatewayFactory.create(config.provider)
        
        system_prompt = (
            "You are a professional financial data extractor. "
            "Extract distinct stock ticker symbols (US Market) mentioned in the following search results. "
            "Return a JSON list of objects: [{\"ticker\": \"...\", \"reason\": \"...\", \"source\": \"...\"}]. "
            "Focus on high-potential tickers. Limit to top 10. "
            "If no tickers are found, return exactly []."
        )
        
        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=f"Search Results:\n{context}")
        ]
        
        # Run chat
        llm_response = await gateway.chat(messages, config)
        
        # 5. Parse and Filter
        # Clean JSON from markdown if exists
        clean_json = re.sub(r'```json\n?|\n?```', '', llm_response).strip()
        try:
            discovered = json.loads(clean_json)
        except json.JSONDecodeError:
            # Try a second attempt at extracting just the list part
            match = re.search(r'\[.*\]', clean_json, re.DOTALL)
            if match:
                discovered = json.loads(match.group(0))
            else:
                logger.error(f"Failed to parse LLM response: {llm_response}")
                return json.dumps({"status": "parse_error", "raw": llm_response})
        
        if not isinstance(discovered, list):
            # Fallback if it returned an object with a field
            if isinstance(discovered, dict) and "tickers" in discovered:
                discovered = discovered["tickers"]
            else:
                discovered = []
        
        # Simple regex validation: Uppercase, 1-5 letters
        valid_tickers = []
        seen = set()
        for item in discovered:
            ticker = item.get("ticker", "").upper()
            if ticker and re.match(r'^[A-Z]{1,5}$', ticker) and ticker not in seen:
                valid_tickers.append({
                    "ticker": ticker,
                    "reason": item.get("reason", "Potential investment candidate."),
                    "source": item.get("source", "Web discovery")
                })
                seen.add(ticker)

        logger.info(f"User {user_id} discovered {len(valid_tickers)} unique tickers.")
        return json.dumps({"status": "success", "tickers": valid_tickers}, ensure_ascii=False)

    except Exception as e:
        logger.error(f"Ticker Discovery Failed: {e}", exc_info=True)
        return json.dumps({"status": "error", "error": str(e)})
