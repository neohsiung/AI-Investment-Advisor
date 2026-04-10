import re
import os

fp1 = "tests/e2e/test_weekly_report_flow.py"
if os.path.exists(fp1):
    with open(fp1, "r") as f:
        content = f.read()
    content = content.replace("wf.memory_service = AsyncMock()", "wf.memory_service = MagicMock()\n    wf.memory_service.store_report = AsyncMock()")
    with open(fp1, "w") as f:
        f.write(content)
    print(f"Updated {fp1}")

fp2 = "tests/unit/workflows/test_antigravity_workflow.py"
if os.path.exists(fp2):
    with open(fp2, "r") as f:
        content = f.read()
    content = content.replace("mem_repo = AsyncMock()", "mem_repo = MagicMock()\n        mem_repo.save_report = AsyncMock()")
    content = content.replace("agent_provider = AsyncMock()", "agent_provider = MagicMock()")
    with open(fp2, "w") as f:
        f.write(content)
    print(f"Updated {fp2}")

