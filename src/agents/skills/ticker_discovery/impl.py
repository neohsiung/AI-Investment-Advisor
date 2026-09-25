import json
import re
import os
import logging
from typing import List, Dict, Any, Optional

from src.utils.logger import setup_logger
from src.services.search_service import InternetSearchService
from src.domain.interfaces import Message

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
        sector_str = f" {sectors[0]}" if (sectors and len(sectors) > 0) else ""
        query = f"best {strategy}{sector_str} stocks to buy 2026 ticker symbol"
        
        # 3. Search
        search_results = await search_svc.search_financial_context(query, max_results=5)
        if not search_results:
            logger.warning(f"No search results for query: {query}")
            return json.dumps({"status": "no_results", "tickers": []})

        # 4. Extract Tickers via ResilientLLMPipeline (Fast Tier)
        # 透過具備自動備援與重試的 ResilientLLMPipeline 提取候選標的，嚴格遵守無硬編碼金鑰規範
        context = "\n".join([f"- {r.get('title', '')}: {r.get('snippet', '')}" for r in search_results])

        from src.infrastructure.llm.llm_config_chain import build_config_chain
        from src.infrastructure.llm.resilient_pipeline import ResilientLLMPipeline

        system_prompt = (
            "You are a professional financial data extractor. "
            "Extract distinct stock ticker symbols (US Market) mentioned or discussed in the following search results. "
            "Return a JSON list of objects: [{\"ticker\": \"...\", \"reason\": \"...\", \"source\": \"...\"}]. "
            "If prominent companies are mentioned by name without explicit tickers (e.g. Amazon, Nvidia, Apple), infer their standard US ticker symbol (e.g. AMZN, NVDA, AAPL). "
            "Focus on high-potential tickers. Limit to top 10. "
            "If no tickers or companies are found, return exactly []."
        )
        
        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=f"Search Results:\n{context}")
        ]
        
        chain = build_config_chain(user_id=user_id, tier="fast")
        if not chain:
            logger.error(f"User {user_id} has no LLM candidates configured for fast tier.")
            return json.dumps({"status": "error", "error": "No LLM candidates found for fast tier."})

        pipeline = ResilientLLMPipeline(
            config_chain=chain,
            user_id=user_id,
            agent_name="ticker_discovery",
            tier="fast",
        )
        exec_res = await pipeline.execute(messages)
        llm_response = exec_res[0] if isinstance(exec_res, tuple) else str(exec_res)
        
        # 5. Parse and Filter
        # Clean JSON from markdown if exists
        clean_json = re.sub(r'```json\s*|\s*```', '', llm_response).strip()
        discovered = None
        try:
            discovered = json.loads(clean_json)
        except (json.JSONDecodeError, ValueError):
            pass

        if discovered is None:
            # Locate first '[' or '{'
            start_bracket = clean_json.find('[')
            start_brace = clean_json.find('{')
            start_idx = -1
            if start_bracket != -1 and (start_brace == -1 or start_bracket < start_brace):
                start_idx = start_bracket
            elif start_brace != -1:
                start_idx = start_brace

            if start_idx != -1:
                try:
                    obj, _ = json.JSONDecoder().raw_decode(clean_json[start_idx:])
                    discovered = obj
                except Exception:
                    pass

        if discovered is None:
            # Fallback regex for list
            match = re.search(r'\[.*?\]', clean_json, re.DOTALL)
            if match:
                try:
                    discovered = json.loads(match.group(0))
                except Exception:
                    pass

        if discovered is None:
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
