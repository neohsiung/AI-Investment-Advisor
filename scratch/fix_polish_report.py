import re
import os

files = [
    "tests/e2e/test_weekly_report_flow.py",
    "tests/unit/workflows/test_antigravity_workflow.py"
]

for fp in files:
    if os.path.exists(fp):
        with open(fp, "r") as f:
            content = f.read()
        
        # Replace return_value mock
        content = re.sub(
            r'([A-Za-z0-9_\]\.\[\'\"]+)\.polish_report\.return_value = (.*)', 
            r'\1.polish_report = AsyncMock(return_value=\2)', 
            content
        )
        
        # Replace side_effect mock
        content = re.sub(
            r'([A-Za-z0-9_\]\.\[\'\"]+)\.polish_report\.side_effect = lambda x: x', 
            r'async def _ret_x(x): return x\n    \1.polish_report = AsyncMock(side_effect=_ret_x)', 
            content
        )
        
        with open(fp, "w") as f:
            f.write(content)
        print(f"Updated {fp}")
