"""
UI Tests for Risk Keywords Tab.
測試風險關鍵字管理分頁。
"""
import pytest
from unittest.mock import MagicMock, patch, call
from src.pages.settings_tabs.risk_keywords_tab import render_risk_keywords_tab, CATEGORY_LABELS


class TestRiskKeywordsTab:
    """Tests for risk keywords management UI."""
    
    @pytest.fixture
    def mock_st(self):
        """Mock Streamlit module."""
        st = MagicMock()
        st.session_state = {}
        
        # Configure columns to return list of mocks based on input
        def columns_side_effect(spec, gap="small"):
            count = 0
            if isinstance(spec, int):
                count = spec
            else:
                count = len(spec)
            return [MagicMock() for _ in range(count)]
            
        st.columns.side_effect = columns_side_effect
    
        # Default selectbox to "all" to avoid early returns in render_risk_keywords_tab
        st.selectbox.return_value = "all"
    
        return st
    
    @pytest.fixture
    def mock_repo(self):
        """Mock RiskKeywordRepository."""
        repo = MagicMock()
        repo.seed_defaults.return_value = None
        repo.get_all.return_value = []
        repo.get_by_category.return_value = []
        return repo
    
    def test_render_calls_seed_defaults(self, mock_st):
        """Test that render calls seed_defaults on repository."""
        with patch('src.pages.settings_tabs.risk_keywords_tab.RiskKeywordRepository') as MockRepo:
            mock_repo = MagicMock()
            MockRepo.return_value = mock_repo
            mock_repo.get_all.return_value = []
            mock_repo.get_all.return_value = []
            
            mock_st.selectbox.return_value = "all"
            
            render_risk_keywords_tab(mock_st)
            
            mock_repo.seed_defaults.assert_called_once()
    
    def test_render_displays_no_keywords_message(self, mock_st):
        """Test display when no keywords exist."""
        with patch('src.pages.settings_tabs.risk_keywords_tab.RiskKeywordRepository') as MockRepo:
            mock_repo = MagicMock()
            MockRepo.return_value = mock_repo
            mock_repo.get_all.return_value = []
            
            render_risk_keywords_tab(mock_st)
            
            mock_st.info.assert_called_with("無關鍵字 (No keywords found)")
    
    def test_add_keyword_with_valid_input(self, mock_st):
        """Test adding a new keyword with valid input."""
        with patch('src.pages.settings_tabs.risk_keywords_tab.RiskKeywordRepository') as MockRepo:
            mock_repo = MagicMock()
            MockRepo.return_value = mock_repo
            mock_repo.get_all.return_value = []
            
            # Simulate user input
            mock_st.text_input.return_value = "bankruptcy"
            mock_st.slider.return_value = 0.8
            # Careful: There are multiple selectboxes. One for new cat, one for filter.
            # We need side_effect to distinguish them or just ensure 'all' is returned when needed.
            # But the code uses logic: new_category = st.selectbox(...) then filter_category = st.selectbox(...)
            # If we return "all" for everything, new_category becomes "all" which might be invalid if it checks keys.
            # Let's use side_effect.
            def selectbox_side_effect(label, *args, **kwargs):
                if "篩選" in label: return "all"
                return "legal"
            mock_st.selectbox.side_effect = selectbox_side_effect

            mock_st.button.return_value = True  # Simulate button click
            
            render_risk_keywords_tab(mock_st)
            
            # Verify add was called with correct parameters
            mock_repo.add.assert_called_once_with("bankruptcy", 0.8, "legal")
            mock_st.success.assert_called()
    
    def test_add_keyword_with_empty_input(self, mock_st):
        """Test adding keyword with empty input shows warning."""
        with patch('src.pages.settings_tabs.risk_keywords_tab.RiskKeywordRepository') as MockRepo:
            mock_repo = MagicMock()
            MockRepo.return_value = mock_repo
            mock_repo.get_all.return_value = []
            
            # Simulate empty input
            mock_st.text_input.return_value = "  "  # Whitespace only
            mock_st.button.return_value = True
            mock_st.selectbox.return_value = "all"
            
            render_risk_keywords_tab(mock_st)
            
            mock_repo.add.assert_not_called()
            mock_st.warning.assert_called_with("請輸入關鍵字")
    
    def test_keyword_list_display(self, mock_st):
        """Test keyword list displays correctly."""
        with patch('src.pages.settings_tabs.risk_keywords_tab.RiskKeywordRepository') as MockRepo:
            mock_kw = MagicMock()
            mock_kw.id = 1
            mock_kw.keyword = "inactive"
            mock_kw.weight = 0.5
            mock_kw.category.value = "market"
            mock_kw.is_active = False
            mock_kw.hit_count = 5
            mock_kw.last_hit_date = "2024-01-15"
            
            mock_repo = MagicMock()
            MockRepo.return_value = mock_repo
            mock_repo.get_all.return_value = [mock_kw]
            
            render_risk_keywords_tab(mock_st)
            
            # Verify markdown showing count
            calls = [c for c in mock_st.markdown.call_args_list if "共 1 個關鍵字" in str(c)]
            assert len(calls) > 0
    
    def test_filter_by_category(self, mock_st):
        """Test filtering keywords by category."""
        with patch('src.pages.settings_tabs.risk_keywords_tab.RiskKeywordRepository') as MockRepo:
            mock_kw = MagicMock()
            mock_kw.id = 1
            mock_kw.keyword = "active"
            mock_kw.weight = 0.5
            mock_kw.category.value = "market"
            mock_kw.is_active = True
            
            mock_repo = MagicMock()
            MockRepo.return_value = mock_repo
            mock_repo.get_by_category.return_value = [mock_kw]
            
            # Simulate category filter selection
            def selectbox_side_effect(*args, **kwargs):
                if "篩選類別" in args:
                    return "legal"
                return list(CATEGORY_LABELS.keys())[0]
            
            mock_st.selectbox.side_effect = selectbox_side_effect
            
            render_risk_keywords_tab(mock_st)
            
            mock_repo.get_by_category.assert_called_with("legal")
    
    def test_show_inactive_keywords(self, mock_st):
        """Test showing inactive keywords."""
        with patch('src.pages.settings_tabs.risk_keywords_tab.RiskKeywordRepository') as MockRepo:
            mock_repo = MagicMock()
            MockRepo.return_value = mock_repo
            mock_repo.get_all.return_value = []
            
            # Simulate checkbox checked
            mock_st.checkbox.return_value = True
            mock_st.selectbox.return_value = "all"
            
            render_risk_keywords_tab(mock_st)
            
            # Verify get_all called with active_only=False
            mock_repo.get_all.assert_called_with(active_only=False)
    
    def test_update_keyword_weight(self, mock_st):
        """Test updating keyword weight."""
        with patch('src.pages.settings_tabs.risk_keywords_tab.RiskKeywordRepository') as MockRepo:
            mock_kw = MagicMock()
            mock_kw.id = 1
            mock_kw.keyword = "crisis"
            mock_kw.weight = 0.5
            mock_kw.category.value = "market"
            mock_kw.is_active = True
            mock_kw.hit_count = 0
            mock_kw.last_hit_date = None
            
            mock_repo = MagicMock()
            MockRepo.return_value = mock_repo
            mock_repo.get_all.return_value = [mock_kw]
            
            # Simulate weight change
            mock_st.number_input.return_value = 0.7  # Changed from 0.5
            mock_st.selectbox.return_value = "all"
            
            render_risk_keywords_tab(mock_st)
            
            mock_repo.update_weight.assert_called_with(1, 0.7)
    
    def test_toggle_keyword_active_to_inactive(self, mock_st):
        """Test toggling keyword from active to inactive."""
        with patch('src.pages.settings_tabs.risk_keywords_tab.RiskKeywordRepository') as MockRepo:
            mock_kw = MagicMock()
            mock_kw.id = 1
            mock_kw.keyword = "volatility"
            mock_kw.weight = 0.6
            mock_kw.category.value = "market"
            mock_kw.is_active = True
            mock_kw.hit_count = 0
            mock_kw.last_hit_date = None
            
            mock_repo = MagicMock()
            MockRepo.return_value = mock_repo
            mock_repo.get_all.return_value = [mock_kw]
            
            # Simulate pause button click
            def button_side_effect(*args, **kwargs):
                key = kwargs.get('key', '')
                return key == 'rk_pause_1'
            
            mock_st.button.side_effect = button_side_effect
            
            render_risk_keywords_tab(mock_st)
            
            mock_repo.toggle_active.assert_called_with(1, False)
    
    def test_toggle_keyword_inactive_to_active(self, mock_st):
        """Test toggling keyword from inactive to active."""
        with patch('src.pages.settings_tabs.risk_keywords_tab.RiskKeywordRepository') as MockRepo:
            mock_kw = MagicMock()
            mock_kw.id = 2
            mock_kw.keyword = "disabled_keyword"
            mock_kw.weight = 0.3
            mock_kw.category.value = "custom"
            mock_kw.is_active = False  # Inactive
            mock_kw.hit_count = 0
            mock_kw.last_hit_date = None
            
            mock_repo = MagicMock()
            MockRepo.return_value = mock_repo
            mock_repo.get_all.return_value = [mock_kw]
            
            # Simulate resume button click
            def button_side_effect(*args, **kwargs):
                key = kwargs.get('key', '')
                return key == 'rk_resume_2'
            
            mock_st.button.side_effect = button_side_effect
            
            render_risk_keywords_tab(mock_st)
            
            mock_repo.toggle_active.assert_called_with(2, True)
    
    def test_delete_keyword(self, mock_st):
        """Test deleting a keyword."""
        with patch('src.pages.settings_tabs.risk_keywords_tab.RiskKeywordRepository') as MockRepo:
            mock_kw = MagicMock()
            mock_kw.id = 3
            mock_kw.keyword = "to_delete"
            mock_kw.weight = 0.5
            mock_kw.category.value = "custom"
            mock_kw.is_active = True
            mock_kw.hit_count = 0
            mock_kw.last_hit_date = None
            
            mock_repo = MagicMock()
            MockRepo.return_value = mock_repo
            mock_repo.get_all.return_value = [mock_kw]
            
            # Simulate delete button click
            def button_side_effect(*args, **kwargs):
                key = kwargs.get('key', '')
                return key == 'rk_del_3'
            
            mock_st.button.side_effect = button_side_effect
            
            render_risk_keywords_tab(mock_st)
            
            mock_repo.delete.assert_called_with(3)
    
    def test_display_top_keywords(self, mock_st):
        """Test displaying top keywords analytics."""
        with patch('src.pages.settings_tabs.risk_keywords_tab.RiskKeywordRepository') as MockRepo:
            mock_top_kw = MagicMock()
            mock_top_kw.keyword = "top1"
            mock_top_kw.hit_count = 100
            mock_top_kw.weight = 0.9
            
            mock_repo = MagicMock()
            MockRepo.return_value = mock_repo
            # Ensure get_all returns something so we don't return early
            mock_repo.get_all.return_value = [mock_top_kw]
            mock_repo.get_top_keywords.return_value = [mock_top_kw]
            
            mock_st.selectbox.return_value = "all"
            
            render_risk_keywords_tab(mock_st)
            
            mock_repo.get_top_keywords.assert_called_with(10)
    
    def test_display_stale_keywords(self, mock_st):
        """Test displaying stale keywords."""
        with patch('src.pages.settings_tabs.risk_keywords_tab.RiskKeywordRepository') as MockRepo:
            mock_stale_kw = MagicMock()
            mock_stale_kw.keyword = "stale"
            mock_stale_kw.last_hit_date = "2023-01-01"
            mock_stale_kw.weight = 0.1
            
            mock_repo = MagicMock()
            MockRepo.return_value = mock_repo
            # Ensure get_all returns something so we don't return early
            mock_repo.get_all.return_value = [mock_stale_kw]
            mock_repo.get_stale_keywords.return_value = [mock_stale_kw]
            
            mock_st.selectbox.return_value = "all"
            
            render_risk_keywords_tab(mock_st)
            
            mock_repo.get_stale_keywords.assert_called_with(days_threshold=90)
    
    def test_disable_all_stale_keywords(self, mock_st):
        """Test batch disabling all stale keywords."""
        with patch('src.pages.settings_tabs.risk_keywords_tab.RiskKeywordRepository') as MockRepo:
            mock_stale1 = MagicMock()
            mock_stale1.id = 10
            mock_stale1.keyword = "stale1"
            mock_stale1.weight = 0.1
            mock_stale1.last_hit_date = None
            
            mock_stale2 = MagicMock()
            mock_stale2.id = 11
            mock_stale2.keyword = "stale2"
            mock_stale2.weight = 0.1
            mock_stale2.last_hit_date = None
            
            mock_repo = MagicMock()
            MockRepo.return_value = mock_repo
            # Ensure get_all returns something so we don't return early
            mock_repo.get_all.return_value = [mock_stale1]
            mock_repo.get_stale_keywords.return_value = [mock_stale1, mock_stale2]
            
            # Simulate disable stale button click
            def button_side_effect(*args, **kwargs):
                key = kwargs.get('key', '')
                return key == 'rk_disable_stale'
            
            mock_st.button.side_effect = button_side_effect
            
            render_risk_keywords_tab(mock_st)
            
            # Verify both stale keywords were toggled to inactive
            calls = mock_repo.toggle_active.call_args_list
            assert any(call == ((10, False),) for call in calls)
            assert any(call == ((11, False),) for call in calls)
    
    def test_category_labels_defined(self):
        """Test that all category labels are defined."""
        assert "legal" in CATEGORY_LABELS
        assert "financial" in CATEGORY_LABELS
        assert "operational" in CATEGORY_LABELS
        assert "geopolitical" in CATEGORY_LABELS
        assert "market" in CATEGORY_LABELS
        assert "custom" in CATEGORY_LABELS
    
    def test_render_with_custom_db_path(self, mock_st):
        """Test render with custom database path."""
        with patch('src.pages.settings_tabs.risk_keywords_tab.RiskKeywordRepository') as MockRepo:
            mock_repo = MagicMock()
            MockRepo.return_value = mock_repo
            mock_repo.get_all.return_value = []
            
            mock_st.selectbox.return_value = "all"
            
            render_risk_keywords_tab(mock_st, db_path="/custom/path.db")
            
            MockRepo.assert_called_with("/custom/path.db")
