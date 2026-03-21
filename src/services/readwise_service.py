import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
import json
import re

from src.data.providers.readwise_provider import ReadwiseProvider
from src.agents.factory import AgentFactory
from src.utils.logger import setup_logger

class ReadwiseService:
    """
    Readwise Service to process highlights and determine if they are investment-related or require actions.
    Readwise 服務，用來處理畫線筆記並判斷是否與投資相關或需要觸發行動。
    """
    
    def __init__(self, user_id: str = "system", readwise_provider: ReadwiseProvider = None):
        self.logger = setup_logger("ReadwiseService")
        self.user_id = user_id
        self.provider = readwise_provider or ReadwiseProvider(user_id=user_id)
        # Using a general agent for analysis
        self.agent = AgentFactory.create_agent("Engineer", use_cache=True, user_id=user_id)
        
    def fetch_and_analyze_highlights(self, updated_after: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Fetch highlights and analyze them for investment relevance.
        獲取畫線筆記並分析其投資相關性。
        """
        try:
            highlights = self.provider.fetch_highlights(updated_after=updated_after)
            analyzed_highlights = []
            
            for highlight in highlights:
                text = highlight.get("text", "")
                if not text:
                    continue
                    
                # /highlights endpoint does not return book title, use book_id if needed
                # For basic analysis, the text itself and the user's note is usually sufficient
                book_id = highlight.get("book_id", "Unknown Book ID")
                
                analysis = self.analyze_highlight(text, book_id=str(book_id), note=highlight.get("note", ""))
                
                # Ensure analysis is a dict before calling .get()
                if isinstance(analysis, dict) and analysis.get("is_investment_related"):
                    analyzed_highlights.append({
                        "id": highlight.get("id"),
                        "text": text,
                        "note": highlight.get("note", ""),
                        "book_id": book_id,
                        "source_url": highlight.get("url", ""),
                        "highlighted_at": highlight.get("highlighted_at"),
                        "analysis": analysis
                    })
                        
            return analyzed_highlights
        except Exception as e:
            self.logger.error(f"Failed to fetch and analyze highlights: {e}")
            return []

    def analyze_highlight(self, highlight_text: str, book_id: str = "", note: str = "") -> Dict[str, Any]:
        """
        Analyze a specific highlight text using LLM.
        使用 LLM 分析特定的畫線內容。
        """
        prompt = f"""
        TASK:
        Analyze the following user highlight from Readwise.
        Determine:
        1. Is this highlight directly or indirectly related to investment, macroeconomics, business strategy, trading, or finance?
        2. Does this highlight imply a need to trigger any investment decisions, actions, or portfolio adjustments?

        BOOK ID: {book_id}
        USER NOTE: {note}
        HIGHLIGHT TEXT:
        {highlight_text}

        Provide the response ONLY as a JSON object with the following keys, no markdown blocks:
        {{
            "is_investment_related": <boolean>,
            "requires_action": <boolean>,
            "reasoning": "<string describing why>",
            "suggested_action": "<string describing what action to take, or null if none>"
        }}
        """
        
        try:
            response = self.agent.run(prompt)
            return self._parse_json_response(response)
        except Exception as e:
            self.logger.error(f"Highlight analysis failed: {e}")
            return {
                "is_investment_related": False,
                "requires_action": False,
                "reasoning": f"Analysis failed: {str(e)}",
                "suggested_action": None
            }
            
    def _parse_json_response(self, response: Any) -> Dict[str, Any]:
        if isinstance(response, dict) and "is_investment_related" in response:
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
             
        # Extract json object using regex
        match = re.search(r"\{.*\}", response_str, re.DOTALL | re.IGNORECASE)
        if match:
             try:
                 obj = json.loads(match.group(0))
                 return obj
             except json.JSONDecodeError as e:
                 self.logger.warning(f"Error decoding JSON response: {e}, raw string: {match.group(0)}")
                 # Fallback to simple matching if json is malformed
                 pass
                 
        # Additional fallback logic
        is_investment = "true" in response_str.lower() or "investment_related\": true" in response_str.lower()
        requires_action = "requires_action\": true" in response_str.lower()
        
        return {
            "is_investment_related": is_investment,
            "requires_action": requires_action,
            "reasoning": response_str[:100],
            "suggested_action": None
        }
