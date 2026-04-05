"""
Implementation of the Knowledge Vault skill for long-term agent memory.
"""

import json
import logging
from typing import Optional
from src.infrastructure.memory.memory_manager import HybridMemory

logger = logging.getLogger(__name__)

def knowledge_vault(user_id: str, action: str, content: str = "", query_term: str = "", category: str = "", limit: int = 5, **kwargs) -> str:
    """
    Interface for the Knowledge Vault (Memory).
    """
    logger.info(f"KnowledgeVault called: user={user_id}, action={action}")
    
    try:
        memory = HybridMemory()
        
        if action == "save":
            if not content:
                return json.dumps({"status": "error", "message": "Content is required for save action."})
            
            metadata = {"source": "knowledge_vault", "category": category}
            mem_id = memory.add_memory(user_id=user_id, content=content, category=category, metadata=metadata)
            return json.dumps({"status": "success", "message": f"Knowledge saved with ID: {mem_id}"})
            
        elif action == "query":
            if not query_term:
                return json.dumps({"status": "error", "message": "Query term is required for query action."})
            
            # Execute search
            results = memory.search(query_text=query_term, user_id=user_id, limit=limit)
            return json.dumps({"status": "success", "data": results})
            
        elif action == "prune":
            # Placeholder for pruning old/irrelevant memory
            return json.dumps({"status": "error", "message": "Prune action not fully implemented yet."})
            
        else:
            return json.dumps({"status": "error", "message": f"Unknown action: {action}"})
            
    except Exception as e:
        logger.error(f"KnowledgeVault error: {e}", exc_info=True)
        return json.dumps({"status": "error", "message": str(e)})

