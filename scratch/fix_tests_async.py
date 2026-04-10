import re
import os

files = [
    "tests/unit/workflows/test_antigravity_workflow.py",
    "tests/e2e/test_weekly_report_flow.py",
    "tests/unit/workflows/test_event_analysis_workflow.py",
    "tests/unit/workflows/test_notification_flow.py",
    "tests/unit/workflows/test_pages_logic.py",
    "tests/unit/agents/test_council_service.py",
    "tests/unit/agents/test_intent_classifier.py",
    "tests/unit/services/test_backtest_service.py",
    "tests/unit/services/test_workflow_service.py"
]

for file_path in files:
    if not os.path.exists(file_path):
        continue
    with open(file_path, "r") as f:
        content = f.read()

    # Add AsyncMock import if not exists
    if "from unittest.mock import" in content and "AsyncMock" not in content:
        content = re.sub(r'from unittest\.mock import (.*)', r'from unittest.mock import \1, AsyncMock', content)
    elif "AsyncMock" not in content:
        content = "from unittest.mock import AsyncMock\n" + content

    # Replace .run.return_value = ... with .run = AsyncMock(return_value=...)
    content = re.sub(r'([A-Za-z0-9_\]\.\[\'\"]+)\.run\.return_value = (.*)', r'\1.run = AsyncMock(return_value=\2)', content)

    with open(file_path, "w") as f:
        f.write(content)
    print(f"Updated {file_path}")
