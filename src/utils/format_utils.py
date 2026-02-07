import json
import re

def format_agent_output(output):
    """
    Format agent output (dict or str) into clean Markdown.
    """
    if isinstance(output, dict):
        # Specific handling for Sentiment
        if "sentiment_score" in output or "score" in output:
            score = output.get("sentiment_score", output.get("score", "N/A"))
            label = output.get("sentiment_label", output.get("label", "N/A"))
            summary = output.get("summary", "")
            return f"**Score**: {score}\n**Label**: {label}\n**Summary**: {summary}"
        
        # Specific handling for Fundamental (if it returns dict)
        if "valuation" in output:
             return f"**Valuation**: {output.get('valuation')}\n**Thesis**: {output.get('thesis', '')}"
        
        # Generic Dict
        return "\n".join([f"- **{k}**: {v}" for k,v in output.items()])
    
    elif isinstance(output, str):
        # Attempt to parse if it looks like a dict string
        try:
            # Replace single quotes with double quotes for JSON (risky but common in python strs)
            if output.strip().startswith("{") and "'" in output:
                import ast
                val = ast.literal_eval(output)
                return format_agent_output(val)
        except:
            pass
        return output
    return str(output)
