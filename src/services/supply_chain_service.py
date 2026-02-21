from typing import Dict, Any
from src.utils.logger import setup_logger
from src.repositories.settings_repository import AlchemySettingsRepository as SettingsService

logger = setup_logger("SupplyChainService")

class SupplyChainService:
    """
    Tracks specific hardware bottlenecks (CoWoS, HBM) and maps MAG7 CaPex
    to component suppliers to estimate shortage premiums.
    """
    def __init__(self, settings_service: SettingsService = None):
        self.settings_service = settings_service or SettingsService()
        self.knowledge_graph = self._load_dynamic_graph()

    def _load_dynamic_graph(self) -> Dict[str, Any]:
        """
        Loads the knowledge graph from settings, falling back to defaults if not present.
        """
        saved_graph = self.settings_service.get_setting("supply_chain_knowledge_graph")
        if saved_graph and isinstance(saved_graph, dict):
            return saved_graph
            
        # [Phase 0: Cold Start via Watchlist]
        # If no graph exists, attempt to bootstrap from the user's active tickers
        try:
            from src.services.transaction_service import TransactionService
            # We assume user_id is the one attached to settings_service
            user_id = self.settings_service.user_id or "system"
            if user_id != "system":
                tx_service = TransactionService(user_id=user_id)
                active_tickers = tx_service.get_user_tickers(user_id=user_id, only_active=True)
                
                if active_tickers:
                    logger.info(f"Bootstrapping Suppy Chain Graph from Watchlist: {active_tickers}")
                    from src.agents.factory import AgentFactory
                    thematic_agent = AgentFactory.create_thematic_agent(user_id=user_id)
                    
                    context = {
                        "event_text": f"Initial System Bootstrapping. User's active watchlist/portfolio: {', '.join(active_tickers)}. Create an initial Supply Chain mapping for these companies.",
                        "theme_key": "supply_chain_knowledge_graph",
                        "current_state": {}
                    }
                    
                    # Run synchronously for initialization
                    result = thematic_agent.run(context)
                    if result.get("status") == "success":
                        new_graph = self.settings_service.get_setting("supply_chain_knowledge_graph")
                        if new_graph and isinstance(new_graph, dict):
                            return new_graph
        except Exception as e:
            logger.error(f"Failed to bootstrap knowledge graph from watchlist: {e}")

        # Fallback to Default Knowledge Graph for Milestone 2.1
        # Map MAG7 scaling/CapEx -> constraints -> beneficiaries
        default_graph = {
            "NVDA": {"bottlenecks": ["CoWoS", "HBM3e"], "suppliers": ["TSM", "MU", "000660.KS"]},
            "AMD": {"bottlenecks": ["CoWoS", "HBM3"], "suppliers": ["TSM", "MU", "000660.KS"]},
            "AAPL": {"bottlenecks": ["3nm Node"], "suppliers": ["TSM"]},
            "MSFT": {"bottlenecks": ["AI Servers", "Power"], "suppliers": ["NVDA", "SMCI", "CEG", "VST"]},
            "GOOGL": {"bottlenecks": ["TPU Structuring"], "suppliers": ["AVGO", "MRVL"]},
            "AMZN": {"bottlenecks": ["Custom Silicon", "Datacenter Power"], "suppliers": ["MRVL", "CEG"]},
            "META": {"bottlenecks": ["GPU Clusters", "Optics"], "suppliers": ["NVDA", "ANET", "COHR"]},
            "TSM": {"bottlenecks": ["Packaging Capacity (CoWoS)", "Advanced Packaging"], "suppliers": ["ASML", "AMAT"]}
        }
        
        # Seed default graph to settings
        self.settings_service.save_setting("supply_chain_knowledge_graph", default_graph)
        return default_graph
        
    def update_graph(self, new_graph: Dict[str, Any]) -> bool:
        """
        Updates the supply chain knowledge graph dynamically.
        """
        success, msg = self.settings_service.save_setting("supply_chain_knowledge_graph", new_graph)
        if success:
            self.knowledge_graph = new_graph
            return True
        logger.error(f"Failed to update knowledge graph: {msg}")
        return False

        
    def get_shortage_premium(self, ticker: str) -> Dict[str, Any]:
        """
        Evaluate if a ticker is subject to a 'shortage premium' based on supply chain bottlenecks.
        """
        premium_info = {
            "has_premium": False,
            "bottlenecks": [],
            "suppliers": [],
            "narrative": ""
        }
        
        # Check if it's the constraint creator (e.g. MAG7)
        if ticker in self.knowledge_graph:
            node = self.knowledge_graph[ticker]
            premium_info["has_premium"] = True
            premium_info["bottlenecks"] = node.get("bottlenecks", [])
            premium_info["suppliers"] = node.get("suppliers", [])
            premium_info["narrative"] = (
                f"**Supply Chain Bottleneck Alert**: High CapEx velocity from {ticker} "
                f"is creating constraints in {', '.join(premium_info['bottlenecks'])}. "
                f"Consider 'Shortage Premium' for key suppliers: {', '.join(premium_info['suppliers'])}."
            )
            return premium_info
            
        # Check if it is a supplier receiving the premium
        beneficiary_sources = []
        for mag7, data in self.knowledge_graph.items():
            if ticker in data.get("suppliers", []):
                beneficiary_sources.append(mag7)
                
        if beneficiary_sources:
             premium_info["has_premium"] = True
             premium_info["narrative"] = (
                 f"**Shortage Premium Beneficiary**: {ticker} benefits from structural Capex constraints "
                 f"driven by {', '.join(beneficiary_sources)}."
             )
             
        return premium_info
