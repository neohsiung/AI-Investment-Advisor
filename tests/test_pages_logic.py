import pytest
from unittest.mock import MagicMock, patch, mock_open
import sys
# Mock streamlit modules to allow importing the page files without error
sys.modules["streamlit"] = MagicMock()
# Helper to load modules with special names
import importlib.util
from pathlib import Path
import os
sys.path.append(os.getcwd()) # Ensure src is resolvable

def load_page_module(name):
    try:
        path = Path("src/pages") / name
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception as e:
        print(f"Failed to load module {name}: {e}")
        raise e
        return None

settings_mod = load_page_module("4_Settings.py")
data_mod = load_page_module("3_Data_Management.py")

from src.services.settings_service import SettingsService

class TestSettingsService:
    def test_get_all_settings(self):
        with patch('src.services.settings_service.get_db_connection') as mock_conn:
            mock_result = MagicMock()
            mock_result.fetchall.return_value = [
                ("AI_PROVIDER", "Google Gemini"),
                ("AI_MODEL", "gemini-1.5-pro")
            ]
            mock_conn.return_value.execute.return_value = mock_result
            
            service = SettingsService("dummy.db")
            settings = service.get_all_settings()
            
            assert settings["AI_PROVIDER"] == "Google Gemini"
            assert settings["AI_MODEL"] == "gemini-1.5-pro"

    def test_save_settings_bulk(self):
        with patch('src.services.settings_service.get_db_connection') as mock_conn:
            service = SettingsService("dummy.db")
            updates = {"AI_PROVIDER": "OpenAI", "API_KEY": "sk-123"}
            
            success, msg = service.save_settings_bulk(updates)
            
            assert success is True
            assert mock_conn.return_value.execute.call_count == 2
            
    def test_fetch_openrouter_models(self):
        with patch('requests.get') as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {
                "data": [{"id": "model A"}, {"id": "model B"}]
            }
            
            service = SettingsService("dummy.db")
            models = service.fetch_openrouter_models()
            assert "model A" in models

from src.services.transaction_service import TransactionService

class TestTransactionService:
    def test_add_manual_trade(self):
        with patch('src.services.transaction_service.TradeIngestor') as mock_ingestor_cls, \
             patch('src.services.transaction_service.update_daily_snapshot') as mock_update:
             
            service = TransactionService("dummy.db")
            success, msg = service.add_manual_trade("AAPL", "2023-01-01", "BUY", 10, 150.0, 5.0)
            
            assert success is True
            assert "AAPL" in msg
            mock_ingestor_cls.return_value.ingest_manual_trade.assert_called_once()
            mock_update.assert_called_once()

    def test_delete_transaction(self):
        with patch('src.services.transaction_service.get_db_connection') as mock_conn, \
             patch('src.services.transaction_service.update_daily_snapshot') as mock_update:
            
            service = TransactionService("dummy.db")
            success, msg = service.delete_transaction(123)
            
            assert success is True
            assert "deleted" in msg
            mock_conn.return_value.execute.assert_called_once()
            
class TestSettingsRender:
    def test_render_api_settings(self):
        mock_st = MagicMock()
        mock_st.session_state = {}
        mock_st.columns.side_effect = lambda n: [MagicMock() for _ in range(n if isinstance(n, int) else len(n))]
        
        mock_service = MagicMock()
        mock_service.save_settings_bulk.return_value = (True, "Success") # Fix ValueError unpacking
        settings = {"AI_PROVIDER": "OpenRouter", "AI_MODEL": "gpt-4"}
        
        # Call the render function
        # Note: function name changed to render_api_settings
        settings_mod.render_api_settings(mock_st, mock_service, settings)
        
        # Verify UI interactions
        mock_st.subheader.assert_called_with("AI 模型參數 (AI Model Parameters)")
        mock_st.selectbox.assert_any_call("AI 提供者 (Provider)", ["Google Gemini", "OpenRouter", "OpenAI"], index=1)

    def test_render_scheduler_tab(self):
        mock_st = MagicMock()
        mock_st.columns.side_effect = lambda n: [MagicMock() for _ in range(n)]
        
        # Mock SystemEngineerAgent inside the function
        with patch('src.agents.engineer.SystemEngineerAgent') as mock_agent_cls, \
             patch.object(settings_mod, 'get_db_connection') as mock_conn, \
             patch('pandas.read_sql') as mock_read_sql:
             
            mock_agent_cls.return_value.get_schedule_config.return_value = {"schedule_daily": "10:00"}
            
            settings_mod.render_scheduler_tab(mock_st, "dummy.db")
            
            mock_st.time_input.assert_any_call("每日檢查時間 (Daily Check Time)", value=ANY)


    def test_render_report_dry_run_tab(self):
        mock_st = MagicMock()
        # Mock columns to return a fixed list of 2 mocks
        col1, col2 = MagicMock(), MagicMock()
        mock_st.columns.return_value = [col1, col2]
        
        mock_st.session_state = {'dry_run_pid': None}
        
        with patch.object(settings_mod, 'os') as mock_os, \
             patch.object(settings_mod, 'subprocess') as mock_subprocess, \
             patch('builtins.open', mock_open()):
             
            mock_os.path.exists.return_value = True
            
            # Button logic:
            # The code calls st.button inside the 'with col_btn:' block.
            # If st is mocked, st.button is still st.button.
            # We enforce return_value=True.
            mock_st.button.return_value = True
            
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_subprocess.Popen.return_value = mock_process
            
            settings_mod.render_report_dry_run_tab(mock_st)
            
            # Assert Popen called
            mock_subprocess.Popen.assert_called()
            assert mock_st.session_state['dry_run_pid'] == 12345

    def test_render_agent_playground_tab(self):
        mock_st = MagicMock()
        mock_st.selectbox.return_value = "Momentum"
        mock_st.text_area.return_value = '{"ticker": "AAPL"}'
        mock_st.button.return_value = True # Execute button
        
        # Test successful execution
        with patch('src.agents.momentum.MomentumAgent') as mock_agent_cls:
            mock_agent_instance = mock_agent_cls.return_value
            mock_agent_instance.run.return_value = "Agent Output"
            
            settings_mod.render_agent_playground_tab(mock_st)
            
            mock_agent_cls.assert_called()
            mock_agent_instance.run.assert_called()
            mock_st.success.assert_called()
            
    def test_render_optimization_history_tab(self):
        mock_st = MagicMock()
        
        with patch.object(settings_mod, 'get_db_connection') as mock_conn:
            # Code: conn.execute(...) checks existence. Mock works by default.
            
            # Mock data retrieval
            mock_df = MagicMock()
            mock_df.empty = False
            mock_df.iterrows.return_value = [
                (0, {'timestamp': '2023-01-01', 'target_agent': 'Momentum', 'reason': 'Test', 'diff_content': 'diff'})
            ]
            
            with patch('pandas.read_sql', return_value=mock_df):
                settings_mod.render_optimization_history_tab(mock_st, "dummy.db")
                
                mock_st.expander.assert_called()
                mock_st.code.assert_called()

class TestDataManagementRender:
    def test_render_manual_entry_tab(self):
        mock_st = MagicMock()
        
        mock_st.columns.side_effect = None # Clear previous side effects if any

        # Create explicit column mocks
        col1 = MagicMock()
        col2 = MagicMock()
        col3 = MagicMock()
        
        # When st.columns(3) is called
        mock_st.columns.return_value = [col1, col2, col3]
        
        # Configure st.inputs directly as they are likely called via 'with col:' context
        mock_st.text_input.return_value = "AAPL"
        mock_st.date_input.return_value = MagicMock()
        mock_st.selectbox.return_value = "BUY"
        # number_input is called for Quantity, Price, Fees
        mock_st.number_input.side_effect = [10.0, 150.0, 5.0]
        
        mock_st.form_submit_button.return_value = True
        
        mock_st.form_submit_button.return_value = True 
        
        mock_service = MagicMock()
        mock_service.add_manual_trade.return_value = (True, "Success")
        
        # Call with service
        data_mod.render_manual_entry_tab(mock_st, mock_service)
        
        mock_st.success.assert_called_with("Success")
    
    def test_render_transactions_tab(self):
        mock_st = MagicMock()
        mock_st.columns.side_effect = lambda n: [MagicMock() for _ in range(n if isinstance(n, int) else len(n))]
        
        mock_service = MagicMock()
        mock_service.delete_transaction.return_value = (True, "Deleted") # Fix ValueError unpacking
        
        mock_df = MagicMock()
        mock_df.empty = False
        # Mocking for options iteration
        mock_df.head.return_value.iterrows.return_value = [
            (0, {'id': 1, 'trade_date': '2023-01-01', 'ticker': 'AAPL', 'action': 'BUY', 'quantity': 10, 'price': 150})
        ]
        mock_service.get_transactions.return_value = mock_df
        
        data_mod.render_transactions_tab(mock_st, mock_service)
        
        assert mock_st.dataframe.called

from unittest.mock import ANY
