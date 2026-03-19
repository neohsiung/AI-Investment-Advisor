import typing
from typing import List, Dict, Any, Optional
from src.utils.logger import setup_logger
from src.services.market_data_service import MarketDataService

logger = setup_logger("CompetitorService")

class CompetitorService:
    """
    Service for monitoring competitor penetration and narrative shifts.
    監控競爭對手滲透率與敘事偏移的服務。
    """
    
    # Standard Peer Groups
    PEER_GROUPS = {
        "TSLA": ["BYDDF", "RIVN", "LCID", "F", "GM", "XIACY"], # EV Leaders
        "NVDA": ["AMD", "INTC", "AVGO", "ARM"],            # AI Chips
        "AAPL": ["MSFT", "GOOGL", "SAMSUNG", "META"],      # Big Tech / Hardware
        "NFLX": ["DIS", "AMZN", "WBD", "PARA"],            # Streaming
        "COST": ["WMT", "TGT", "BJ", "AMZN"],              # Retail
    }

    def __init__(self, user_id: str = "default_user", market_service: Optional[MarketDataService] = None):
        self.user_id = user_id
        self.market_service = market_service or MarketDataService(user_id=user_id)

    def get_peer_group(self, leader_ticker: str) -> List[str]:
        """Get the list of competitors for a given leader."""
        return self.PEER_GROUPS.get(leader_ticker.upper(), [])

    def analyze_penetration(self, leader_ticker: str) -> Dict[str, Any]:
        """
        Analyze penetration and narrative shift for a leader vs its peers.
        分析龍頭股相對於競爭對手的滲透率與敘事偏移。
        """
        peers = self.get_peer_group(leader_ticker)
        if not peers:
            return {"status": "skipped", "reason": f"No peer group defined for {leader_ticker}"}

        # 1. Fetch Performance Summary
        tickers = [leader_ticker] + peers
        prices = self.market_service.get_current_prices(tickers)
        
        # 2. Mock Sentiment/Narrative Analysis for now
        # In a real implementation, this would call SentimentService or an LLM-based narrative extractor
        results = {
            "leader": leader_ticker,
            "peers": peers,
            "metrics": {
                "relative_performance_5d": 0.0, # Placeholder
                "narrative_similarity": 0.65,   # Placeholder (Convergence)
                "competitor_penetration_score": 45, # 0-100 (Higher = more threat)
            },
            "risk_level": "LOW"
        }
        
        # Logic: If narrative similarity is high (>0.8) and leader underperforms, risk is HIGH
        if results["metrics"]["narrative_similarity"] > 0.8:
            results["risk_level"] = "MEDIUM"
            results["warning"] = "Narrative convergence detected: Competitors are adopting leader's core messaging."

        return results
