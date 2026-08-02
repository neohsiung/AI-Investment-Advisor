from typing import List, Dict, Any, Tuple
from src.utils.logger import setup_logger

logger = setup_logger("EnsembleVotingEngine")

class EnsembleVotingEngine:
    """
    Multi-Agent Swarm Ensemble Voting & Confidence Aggregator inspired by Semble.
    多代理人 Swarm 集成投票與信心加權計算引擎。
    """
    def __init__(self, weights: Dict[str, float] = None):
        # Default agent role weights for final consensus score
        self.weights = weights or {
            "FundamentalSwarm": 0.40,
            "TechnicalSwarm": 0.35,
            "SentimentSwarm": 0.25,
        }

    def compute_consensus(self, agent_votes: List[Dict[str, Any]]) -> Tuple[str, float, List[Dict[str, Any]]]:
        """
        Aggregates votes and confidence scores across agents into a single unified verdict & score (0-100).
        
        Args:
            agent_votes: List of dicts with keys: agent_name, action ("BUY"/"SELL"/"HOLD"), confidence (0-100), key_factor
            
        Returns:
            Tuple of (final_action, final_confidence_score_0_to_100, breakdown_list)
        """
        if not agent_votes:
            return "HOLD", 0.0, []

        weighted_buy = 0.0
        weighted_sell = 0.0
        weighted_hold = 0.0
        total_weight = 0.0

        breakdown = []

        for vote in agent_votes:
            agent_name = vote.get("agent_name", "UnknownAgent")
            action = str(vote.get("action", "HOLD")).upper()
            raw_conf = float(vote.get("confidence", 50))
            if raw_conf <= 10:
                raw_conf = raw_conf * 10.0  # Scale 0-10 to 0-100 if needed

            weight = self.weights.get(agent_name, 0.20)
            total_weight += weight

            if action == "BUY":
                weighted_buy += raw_conf * weight
            elif action == "SELL":
                weighted_sell += raw_conf * weight
            else:
                weighted_hold += raw_conf * weight

            breakdown.append({
                "agent": agent_name,
                "action": action,
                "confidence": round(raw_conf, 1),
                "weight": weight,
                "key_factor": vote.get("key_factor", "")
            })

        if total_weight <= 0:
            total_weight = 1.0

        score_buy = weighted_buy / total_weight
        score_sell = weighted_sell / total_weight
        score_hold = weighted_hold / total_weight

        if score_buy >= score_sell and score_buy >= score_hold:
            final_action = "BUY"
            final_score = score_buy
        elif score_sell >= score_buy and score_sell >= score_hold:
            final_action = "SELL"
            final_score = score_sell
        else:
            final_action = "HOLD"
            final_score = score_hold

        logger.info(f"Ensemble Voting Result: {final_action} with score {final_score:.1f}/100")
        return final_action, round(final_score, 1), breakdown
