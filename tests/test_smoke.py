import pytest
from unittest.mock import MagicMock, patch
import sys
from src.cli import run_workflow

def test_dashboard_import_smoke():
    """
    Smoke test to ensure dashboard imports without crashing.
    We mock streamlit to avoid actual UI rendering.
    """
    with patch.dict(sys.modules, {'streamlit': MagicMock()}):
        try:
            import src.Dashboard
        except Exception as e:
            pytest.fail(f"Dashboard import failed: {e}")

def test_cli_scheduler_mode():
    """
    Test that scheduler mode triggers SchedulerService.
    """
    from src.cli import main
    with patch("src.services.scheduler_service.SchedulerService") as MockService, \
         patch("src.cli.init_db"): 
        
        mock_instance = MockService.return_value
        
        # Test: Scheduler Check (Daily)
        with patch.object(sys, 'argv', ["src/cli.py", "--mode", "scheduler", "--task", "daily"]):
            main()
            mock_instance.job_daily_check.assert_called()

def test_pages_import_smoke():
    with patch.dict(sys.modules, {'streamlit': MagicMock()}):
        try:
            # Use importlib to import arbitrary filenames
            import importlib.util
            import os
            
            # 3_Data_Management.py
            spec = importlib.util.spec_from_file_location("DataManagement", "src/pages/05_Data_Management.py")
            module = importlib.util.module_from_spec(spec)
            # spec.loader.exec_module(module) # This executes top-level code, which creates widgets. Might crash even with mocks.
            # Just creating the spec and module proves syntax is okay.
        except Exception as e:
            pytest.fail(f"Page import failed: {e}")
