import json
import re
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

def repair_json(text: str) -> str:
    """
    Attempts to repair common JSON errors from LLM outputs.
    1. Removes Markdown code blocks (```json ... ```)
    2. Handles leading/trailing whitespace
    """
    if not text:
        return ""
        
    # Remove Markdown fences
    text = re.sub(r'^```(?:json)?', '', text.strip(), flags=re.MULTILINE)
    text = re.sub(r'```$', '', text.strip(), flags=re.MULTILINE)
    
    return text.strip()

def json_loads_safe(text: str, default: Any = None) -> Any:
    """
    Safely load JSON with repair logic.
    """
    if not text:
        return default if default is not None else {}
        
    repaired = repair_json(text)
    
    # 1. Clean trailing commas and other common garbage
    repaired = re.sub(r',\s*([\]}])', r'\1', repaired)
    
    # 2. First attempt: Direct load
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        # 3. Second attempt: Robust extraction of JSON block
        try:
            # Isolate {} and [] blocks separately to avoid matching from [ to }
            dict_match = re.search(r'(\{.*\})', repaired, re.DOTALL)
            list_match = re.search(r'(\[.*\])', repaired, re.DOTALL)
            
            json_block = None
            if dict_match and list_match:
                # If both exist, pick the one that starts first
                if dict_match.start() < list_match.start():
                    json_block = dict_match.group(1).strip()
                else:
                    json_block = list_match.group(1).strip()
            elif dict_match:
                json_block = dict_match.group(1).strip()
            elif list_match:
                json_block = list_match.group(1).strip()
                
            if json_block:
                return json.loads(json_block)
        except Exception as e:
            logger.warning(f"json_loads_safe extraction failed: {e}")
            
        logger.error(f"JSON Parse Error: Expecting value: line 1 column 1 (char 0) - Content: {text[:200]}...")
        return default if default is not None else {}
