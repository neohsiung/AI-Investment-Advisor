import os
import logging
from typing import Dict, Any, Optional
from jinja2 import Template

logger = logging.getLogger(__name__)

def load_agent_prompt(agent_name: str, context: Optional[Dict[str, Any]] = None) -> str:
    """
    Load agent prompt from prompts/ directory and optionally render with context.
    從 prompts/ 目錄載入 Agent 提示詞，並可選擇性使用 context 進行渲染。
    
    [STRICT] Must exist in prompts/ directory. No fallbacks allowed.
    """
    # Standardize agent name to lowercase for filename
    base_name = agent_name.lower().replace(" ", "_")
    if not base_name.endswith("_agent"):
        filename = f"{base_name}_agent.txt"
    else:
        filename = f"{base_name}.txt"
        
    prompt_path = os.path.join("prompts", filename)
    
    if not os.path.exists(prompt_path):
        # [STRICT] Rule #14: No fallbacks.
        raise FileNotFoundError(
            f"CRITICAL: Prompt file for agent '{agent_name}' not found at {prompt_path}. "
            "All agent prompts must reside in the prompts/ directory."
        )
        
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            prompt_content = f.read()
            
        if context:
            template = Template(prompt_content)
            return template.render(**context)
        return prompt_content
    except Exception as e:
        logger.error(f"Failed to load/render prompt for {agent_name}: {e}")
        raise
