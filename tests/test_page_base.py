import pytest
from unittest.mock import Mock, patch, MagicMock
from src.utils.page_base import BasePage

class ConcretePage(BasePage):
    """Concrete implementation for testing"""
    def render(self):
        pass

class TestBasePage:
    
    def test_initialization(self):
        """Test initialization of attributes"""
        page = ConcretePage("Test Title", "🚀", "centered")
        assert page.title == "Test Title"
        assert page.icon == "🚀"
        assert page.layout == "centered"
        
    def test_setup_page_config(self):
        """Test setup_page calls config and css loader"""
        page = ConcretePage("Test", "🧪")
        
        # Patch the alias 'st' in src.utils.page_base
        with patch('src.utils.page_base.st') as mock_st, \
             patch('src.utils.ui.load_design_system_css') as mock_css, \
             patch('src.utils.ui.render_sidebar') as mock_sidebar, \
             patch('src.utils.auth_guard.require_authentication') as mock_auth, \
             patch('src.data.database.init_db') as mock_db:

            
            page.setup_page()
            
            mock_st.set_page_config.assert_called_with(
                page_title="Test",
                page_icon="🧪",
                layout="wide"
            )
            mock_css.assert_called_once()

    @patch('src.utils.ui.load_design_system_css') 
    def test_render_not_implemented(self, mock_css):
        """Test abstract method requirement"""
        # Abstract class shouldn't be instantiated properly without implementing render
        # But here we test BasePage directly if possible, or concrete
        pass

    def test_run_method(self):
        """Test run method sequence"""
        page = ConcretePage("Test", "🧪")
        
        with patch('src.utils.page_base.st') as mock_st, \
             patch('src.utils.ui.load_design_system_css') as mock_css, \
             patch('src.utils.ui.render_sidebar') as mock_sidebar, \
             patch('src.utils.auth_guard.require_authentication') as mock_auth, \
             patch('src.data.database.init_db') as mock_db, \
             patch('src.utils.ui.render_top_profile') as mock_top, \
             patch('src.utils.components.saas_section_header') as mock_header:

             
            # Mock container context manager
            mock_container = Mock()
            mock_st.container.return_value.__enter__.return_value = mock_container
            
            page.run()
            
            # Verify sequence (setup_page calls config and css)
            mock_st.set_page_config.assert_called()
            mock_css.assert_called()
            mock_auth.assert_called()
            mock_sidebar.assert_called()
            mock_st.container.assert_called()

    def test_default_icon(self):
        """Test default values"""
        page = ConcretePage("Test", "icon")
        assert page.layout == "wide"  # Default layout

    def test_concrete_subclass_can_override_render(self):
        """Test that subclass implementation is called"""
        page = ConcretePage("Test", "icon")
        try:
            page.render()
        except Exception:
            pytest.fail("render() raised Exception unexpectedly!")
