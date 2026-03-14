import json
import re
from src.agents.base_agent import BaseAgent

class ActionExtractorAgent(BaseAgent):
    """
    Extract structured trades from free-form AI text decisions.
    從非結構化 AI 委員會決策文字中提取結構化交易指令。
    """
    def __init__(self, use_cache=True, user_id=None, tier="fast", **kwargs):
        # We don't need a specific identity or prompt file for this simple NLP task.
        # But BaseAgent requires a prompt_path. (但 BaseAgent 需要 prompt_path。)
        super().__init__(
            name="ActionExtractor", 
            prompt_path="prompts/action_extractor.md", # Placeholder (佔位符)
            use_cache=use_cache, 
            ttl_hours=1, 
            tier=tier, 
            user_id=user_id,
            **kwargs
        )

    def _load_prompt(self):
        """Override to skip loading from file since it's hardcoded in run()."""
        return "Action Extraction Intelligence"

    def run(self, context) -> list:
        """
        Extract structured trades from free-form AI text.
        從非結構化 AI 文字中提取結構化交易指令。

        context is expected to be a string (the CIO decision).
        context 預期為字串（CIO 決策文字）。

        Returns a list of dicts: [{"ticker": "AAPL", "action": "BUY", "quantity": 10, "confidence": 8, "reason": "..."}].
        回傳字典列表：[{"ticker": "AAPL", "action": "BUY", "quantity": 10, "confidence": 8, "reason": "..."}]。
        """
        if not context or not isinstance(context, str):
            return []
            
        prompt = f"""
        You are an Action Extraction AI.
        Analyze the following investment council decision and extract any explicit trade recommendations or portfolio allocation changes.
        
        Rules:
        1. Only extract explicit trade recommendations (buying, selling, trimming, adding).
        2. 'action' must be exactly "BUY" or "SELL".
        3. 'quantity' should be a numeric float/int representing shares or contract amount (default to 1 if unspecified). Do not use percentages.
        4. 'confidence' must be an integer between 1 and 10, where 10 is highest conviction. Infer based on the language (e.g. "strong conviction" = 9, "consider trimming" = 5).
        5. Output ONLY a valid JSON array of objects, with NO surrounding markdown block quotes. If no explicit trades are found, output an empty array [].
        
        Example Output:
        [
            {{"ticker": "NVDA", "action": "SELL", "quantity": 10, "confidence": 8, "reason": "AI council recommends taking profit due to systemic risks."}}
        ]
        
        Decision Text:
        {context}
        """
        try:
            response = self.run_tool_loop(prompt)
            # clean up markdown and surrounding text if any
            # 優先搜尋符合 JSON 陣列特徵的區塊
            response_clean = response.strip()
            
            # Use regex to find the first '[' followed by '{' and the first ']' following a '}'
            # 使用非貪婪模式找尋第一個符合 [ { ... } ] 的區塊
            match = re.search(r'\[\s*\{.*?\}\s*\]', response_clean, re.DOTALL)
            if match:
                response_clean = match.group(0)
            else:
                # Fallback to markdown cleaning (備援方案：Markdown 清理)
                if response_clean.startswith("```json"):
                    response_clean = response_clean[7:-3].strip()
                elif response_clean.startswith("```"):
                    response_clean = response_clean[3:-3].strip()
            
            trades = json.loads(response_clean)
            if isinstance(trades, list):
                return trades
            else:
                self.logger.warning(f"ActionExtractorAgent returned non-list JSON: {trades}")
                return []
        except json.JSONDecodeError as j_err:
            self.logger.error(f"ActionExtractorAgent JSON Parse Error: {j_err}. Raw output: {response[:200]}")
            return []
        except Exception as e:
            self.logger.error(f"ActionExtractorAgent failed to parse trades: {e}")
            return []
