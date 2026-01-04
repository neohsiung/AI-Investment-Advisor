import json
from .base_agent import BaseAgent

class SentimentAgent(BaseAgent):
    def __init__(self, use_cache=True, ttl_hours=4, user_id="system", **kwargs):
        # Default 4 hours for Sentiment (News changes fast)
        # Ensure 'tier' is not in kwargs to avoid duplicate argument error
        kwargs.pop('tier', None)
        super().__init__(name="Sentiment", prompt_path="prompts/sentiment_agent.txt", use_cache=use_cache, ttl_hours=ttl_hours, tier="fast", user_id=user_id, **kwargs)

    def run(self, context):
        """
        Run Sentiment Analysis.
        context: {
            "ticker": "AAPL",
            "news": ["Title - Source (Link)", ...],
            "price_change_percent": optional float
        }
        """
        ticker = context.get("ticker", "UNKNOWN")
        news_list = context.get("news", [])
        
        if not news_list:
            return {
                "sentiment": "Neutral",
                "narrative": "無相關新聞",
                "score": 0.0
            }
            
        # Format news
        news_str = "\n".join([f"- {n}" for n in news_list[:5]]) # Top 5
        
        prompt_data = {
            "ticker": ticker,
            "news_list": news_str,
            "price_change_percent": context.get("price_change_percent", "N/A")
        }
        
        system_prompt = self.render_system_prompt(prompt_data)
        user_prompt = f"Analyze sentiment for {ticker}."
        
        # Use JSON mode if supported by provider, but prompt asks for raw JSON.
        response_str = self.call_llm(
             messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2
        )
        
        # Parse JSON
        try:
            cleaned = response_str.replace("```json", "").replace("```", "").strip()
            # Robust extraction
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1:
                cleaned = cleaned[start:end+1]
            return json.loads(cleaned)
        except json.JSONDecodeError:
            self.logger.warning(f"Failed to parse sentiment JSON for {ticker}: {response_str}")
            return {
                "sentiment": "Unknown",
                "narrative": response_str[:50] + "...",
                "score": 0.0
            }
