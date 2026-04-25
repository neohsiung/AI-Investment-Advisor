import typing
import os
import json
import asyncio
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
from src.utils.logger import setup_logger
from src.services.settings_service import SettingsService
from src.infrastructure.llm.tier_config import SettingsAwareModelRouter
from src.infrastructure.llm.llm_gateway import OpenRouterGateway
from src.domain.interfaces import Message, LLMConfig
from src.repositories.settings_repository import AlchemySettingsRepository

logger = setup_logger("SupplyChainService")

class SupplyChainService:
    """
    Tracks specific hardware bottlenecks (CoWoS, HBM) and maps MAG7 CaPex
    to component suppliers to estimate shortage premiums.
    
    PAD Phase 2: Migrated to SettingsAwareModelRouter + OpenRouterGateway
    """
    def __init__(self, user_id: str = None, settings_service: Any = None):
        self.user_id = user_id
        self.settings_service = settings_service or SettingsService(user_id=self.user_id)
        
        # PAD Phase 2: Initialize router and gateway for LLM calls
        self.settings_repo = AlchemySettingsRepository()
        self.model_router = SettingsAwareModelRouter(self.settings_repo)
        self.gateway = OpenRouterGateway()
        
        self.knowledge_graph = self._load_dynamic_graph()

    def _load_dynamic_graph(self) -> Dict[str, Any]:
        """
        Loads the knowledge graph from settings, falling back to defaults if not present.
        PAD Phase 2: Uses async LLM call via gateway instead of AgentFactory
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
                    logger.info(f"Bootstrapping Supply Chain Graph from Watchlist: {active_tickers}")
                    # PAD Phase 2: Use async call via gateway
                    result = asyncio.run(self._bootstrap_graph_async(active_tickers, user_id))
                    if result and isinstance(result, dict) and result.get("status") == "success":
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
    
    async def _bootstrap_graph_async(self, active_tickers: List[str], user_id: str) -> Dict[str, Any]:
        """
        PAD Phase 2: Asynchronous helper to bootstrap the supply chain graph via LLM.
        Replaces AgentFactory.create_thematic_agent().run()
        """
        try:
            model = self.model_router.get_model(user_id, "smart")
            if not model:
                logger.warning(f"Failed to route model for tier=smart, using fallback")
                return {"status": "failed"}
            
            system_prompt = (
                "You are a Supply Chain analyst. Generate a knowledge graph mapping "
                "semiconductor hardware bottlenecks (CoWoS, HBM packaging, advanced nodes) "
                "and their beneficiary suppliers. Return valid JSON with ticker -> {bottlenecks, suppliers}."
            )
            
            context = {
                "event_text": f"Initial System Bootstrapping. User's active watchlist/portfolio: {', '.join(active_tickers)}. Create an initial Supply Chain mapping for these companies.",
                "theme_key": "supply_chain_knowledge_graph",
                "current_state": {}
            }
            
            messages = [
                Message(role="system", content=system_prompt),
                Message(role="user", content=json.dumps(context))
            ]
            
            config = LLMConfig(
                provider=os.getenv("AI_PROVIDER", "OpenRouter"),
                model=model,
                temperature=0.5,
                max_tokens=2000
            )
            
            logger.debug(f"SupplyChain: Bootstrapping graph via {model}")
            response = await self.gateway.chat(messages, config)
            
            # Parse response and save to settings
            try:
                graph_data = json.loads(response)
                if isinstance(graph_data, dict) and graph_data:
                    self.settings_service.save_setting("supply_chain_knowledge_graph", graph_data)
                    return {"status": "success"}
            except json.JSONDecodeError:
                logger.warning(f"SupplyChain: Failed to parse LLM response as JSON: {response[:100]}")
                return {"status": "parse_error"}
            
            return {"status": "success"}
        except Exception as e:
            logger.error(f"SupplyChain: Bootstrap failed: {e}")
            return {"status": "failed"}
        
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
