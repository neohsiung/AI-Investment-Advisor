import pytest
from unittest.mock import MagicMock, patch, mock_open
import sys
# Mock streamlit modules to allow importing the page files without error
sys.modules["streamlit"] = MagicMock()
# Helper to load modules with special names
import importlib.util
from pathlib import Path

def load_page_module(name):
    try:
        path = Path("src/pages") / name
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception as e:
        print(f"Failed to load module {name}: {e}")
        return None

settings_mod = load_page_module("4_Settings.py")
data_mod = load_page_module("3_Data_Management.py")

class TestSettingsLogic:
    def test_load_settings_from_db(self):
        # Patch the function reference that the module holds
        with patch.object(settings_mod, 'get_db_connection') as mock_conn:
            mock_cursor = mock_conn.return_value.cursor.return_value
            mock_cursor.execute.return_value.fetchall.return_value = [
                ("AI_PROVIDER", "Google Gemini"),
                ("AI_MODEL", "gemini-1.5-pro")
            ]
            
            settings = settings_mod.load_settings_from_db("dummy.db")
            
            assert settings["AI_PROVIDER"] == "Google Gemini"
            assert settings["AI_MODEL"] == "gemini-1.5-pro"
            
    def test_save_settings_to_db(self):
        with patch.object(settings_mod, 'get_db_connection') as mock_conn:
            mock_cursor = mock_conn.return_value.cursor.return_value
            
            success, msg = settings_mod.save_settings_to_db("dummy.db", "OpenAI", "gpt-4", "sk-...", "https://api.openai.com")
            
            if not success:
               print(f"Test Failed Msg: {msg}") 

            assert success is True
            assert "saved" in msg
            
            # Verify SQL execution
            assert mock_cursor.execute.call_count == 4

    def test_fetch_openrouter_models(self):
        # requests is imported as a module, so patching requests.get works globally or we can patch settings_mod.requests.get
        with patch.object(settings_mod.requests, 'get') as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {
                "data": [{"id": "model A"}, {"id": "model B"}]
            }
            
            models = settings_mod.fetch_openrouter_models()
            assert "model A" in models
            assert "model B" in models

class TestDataManagementLogic:
    def test_process_manual_trade(self):
        # TradeIngestor is imported INSIDE the function, so we must patch 'src.ingestor.TradeIngestor'
        # update_daily_snapshot is imported at TOP LEVEL, so we must patch data_mod.update_daily_snapshot
        with patch('src.ingestor.TradeIngestor') as mock_ingestor_cls, \
             patch.object(data_mod, 'update_daily_snapshot') as mock_update:
            
            success, msg = data_mod.process_manual_trade(
                "dummy.db", "AAPL", "2023-01-01", "BUY", 10, 150.0, 5.0
            )
            
            assert success is True
            assert "AAPL" in msg
            mock_ingestor_cls.return_value.ingest_manual_trade.assert_called_once()
            mock_update.assert_called_once()

    def test_delete_transaction(self):
        # get_db_connection is imported at TOP LEVEL
        # update_daily_snapshot is imported at TOP LEVEL
        with patch.object(data_mod, 'get_db_connection') as mock_conn, \
             patch.object(data_mod, 'update_daily_snapshot') as mock_update:
            
            mock_conn.return_value.execute.return_value = MagicMock()
            
            success, msg = data_mod.delete_transaction("dummy.db", 123)
            
            assert success is True
            assert "deleted" in msg

class TestSettingsRender:
    def test_render_ai_settings_tab(self):
        mock_st = MagicMock()
        mock_st.session_state = {}
        # Mock columns to return list of mocks 
        mock_st.columns.side_effect = lambda n: [MagicMock() for _ in range(n if isinstance(n, int) else len(n))]
        
        settings = {"AI_PROVIDER": "OpenRouter", "AI_MODEL": "gpt-4"}
        
        # Call the render function
        settings_mod.render_ai_settings_tab(mock_st, "dummy.db", settings)
        
        # Verify UI interactions
        mock_st.subheader.assert_called_with("AI 模型參數 (AI Model Parameters)")
        mock_st.selectbox.assert_any_call("AI 提供者 (Provider)", ["Google Gemini", "OpenRouter", "OpenAI"], index=1)

    def test_render_scheduler_tab(self):
        mock_st = MagicMock()
        mock_st.columns.side_effect = lambda n: [MagicMock() for _ in range(n)]
        
        # Mock SystemEngineerAgent inside the function
        with patch('src.agents.engineer.SystemEngineerAgent') as mock_agent_cls, \
             patch.object(settings_mod, 'get_db_connection') as mock_conn:
             
            mock_agent_cls.return_value.get_schedule_config.return_value = {"schedule_daily": "10:00"}
            mock_conn.return_value.cursor.return_value.fetchall.return_value = []
            
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
            # Mock table existence check
            mock_cursor = mock_conn.return_value.cursor.return_value
            mock_cursor.fetchone.return_value = True # Table exists
            
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
        # Handle st.columns(int) and st.columns(list)
        mock_st.columns.side_effect = lambda n: [MagicMock() for _ in range(n if isinstance(n, int) else len(n))]
        
        # Configure input return values to be valid numbers for logic checks
        # We need specific mocks for the columns to set their return values
        col_mock = MagicMock()
        col_mock.number_input.return_value = 10.0 # Quantity and Price > 0
        col_mock.text_input.return_value = "AAPL" # Ticker not empty
        
        # Return our configured col_mocks
        mock_st.columns.return_value = [col_mock, col_mock, col_mock]
        # Override side_effect for this test if we want specific returns or just rely on return_value if side_effect is cleared
        mock_st.columns.side_effect = None
        mock_st.columns.return_value = [col_mock, col_mock, col_mock]

        # Since the code calls st.columns(2) then st.columns(3), we need side_effect to return list of correct size
        def column_side_effect(n):
            count = n if isinstance(n, int) else len(n)
            return [col_mock for _ in range(count)]
        mock_st.columns.side_effect = column_side_effect
        
        mock_st.form_submit_button.return_value = True 
        
        # Mock process_manual_trade
        with patch.object(data_mod, 'process_manual_trade') as mock_process:
            mock_process.return_value = (True, "Success")
            
            data_mod.render_manual_entry_tab(mock_st, "dummy.db")
            
            mock_st.success.assert_called_with("Success")
    
    def test_render_transactions_tab(self):
        mock_st = MagicMock()
        mock_st.columns.side_effect = lambda n: [MagicMock() for _ in range(n if isinstance(n, int) else len(n))]
        
        with patch.object(data_mod, 'get_db_connection') as mock_conn:
            mock_df = MagicMock()
            mock_df.empty = False
            mock_df.iterrows.return_value = [
                (0, {'id': 1, 'date': '2023-01-01', 'ticker': 'AAPL', 'action': 'BUY', 'quantity': 10, 'price': 150, 'amount': 1500})
            ]
            # Mock pd.read_sql
            with patch('pandas.read_sql', return_value=mock_df):
                data_mod.render_transactions_tab(mock_st, "dummy.db")
                
                # Should create columns for header and row
                assert mock_st.columns.call_count >= 2

from unittest.mock import ANY
