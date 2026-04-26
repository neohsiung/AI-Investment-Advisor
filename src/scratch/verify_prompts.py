import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.utils.prompt_utils import load_agent_prompt

def test_prompt_compliance():
    print("Testing prompt compliance (Rule #14)...")
    
    # Test loading an existing prompt
    try:
        content = load_agent_prompt("report_translator")
        print(f"SUCCESS: Loaded 'report_translator' prompt ({len(content)} chars).")
    except Exception as e:
        print(f"FAILURE: Could not load existing prompt: {e}")
        
    # Test loading a non-existent prompt
    try:
        load_agent_prompt("non_existent_ghost_agent")
        print("FAILURE: Loaded a non-existent prompt without error!")
    except FileNotFoundError as e:
        print(f"SUCCESS: Correctly raised FileNotFoundError for missing prompt: {e}")
    except Exception as e:
        print(f"FAILURE: Raised unexpected exception type: {type(e).__name__}: {e}")

if __name__ == "__main__":
    test_prompt_compliance()
