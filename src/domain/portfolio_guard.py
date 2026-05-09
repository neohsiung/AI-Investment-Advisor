"""
Portfolio Guard — Domain Layer [Phase 15].
投資組合護欄 — 負責確定性規則的執行 (例如：部位限額)。

Directly manipulates the report text to enforce hard constraints that AI might 
miss or hallucinate (e.g., capping a single stock weight at 20%).
"""

import re
import logging

logger = logging.getLogger(__name__)

def enforce_position_limits(report_text: str, max_weight: float = 0.2) -> str:
    """
    Parses the report for markdown tables and caps any 'Quantity/Weight' (數量/比例) 
    that exceeds the max_weight.
    
    Example: 30% -> 20%*(依風控原則限制最大權重)*
    """
    try:
        # Regex to find lines in markdown tables that look like trade rows
        # Format: | Ticker | Action | Weight | ... |
        # We look for percentage values (e.g., 25%, 0.25)
        
        def cap_match(match):
            original = match.group(0)
            value_str = match.group(1).replace('%', '')
            try:
                value = float(value_str)
                # If it's a percentage (e.g., 25), convert to decimal (0.25)
                is_percentage = '%' in match.group(1)
                effective_value = value / 100.0 if is_percentage else value
                
                if effective_value > max_weight:
                    capped_val = max_weight * 100.0 if is_percentage else max_weight
                    suffix = "*(依風控原則限制最大權重)*"
                    return f"{capped_val:.1f}%{suffix}" if is_percentage else f"{capped_val:.2f}{suffix}"
                
                return original
            except ValueError:
                return original

        # Robust table parser: Process line by line to identify table rows
        lines = report_text.split('\n')
        new_lines = []
        
        for line in lines:
            if line.strip().startswith('|') and line.strip().endswith('|'):
                # It's a table row. Find percentage or weight cells.
                # Regex looks for patterns like ' 30% ' or ' 0.30 ' within cells
                def replace_cell(match):
                    return cap_match(match)
                
                # Match percentages (e.g., 25%) or decimal numbers (e.g., 0.25) inside cells
                # We target cells that look like they contain weight data
                new_line = re.sub(r'(?<=\|)\s*(\d+(?:\.\d+)?%?)\s*(?=\|)', replace_cell, line)
                new_lines.append(new_line)
            else:
                new_lines.append(line)
                
        return '\n'.join(new_lines)
        
    except Exception as e:
        logger.error(f"PortfolioGuard: Failed to enforce limits: {e}")
        return report_text
