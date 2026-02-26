import pytest
from unittest.mock import Mock, patch, MagicMock
from src.services.theme_service import ThemeService

class TestThemeService:
    """Test suite for ThemeService"""
    
    @pytest.fixture
    def service(self):
        """Create a ThemeService instance"""
        return ThemeService()
    
    def test_get_fallback_theme_data_light(self, service):
        """Test fallback theme data for light mode"""
        data = service.get_fallback_theme_data('light')
        assert 'colors' in data
        assert data['colors']['primary'] == '#0D9488'
        assert data['colors']['bg'] == '#F8FAFC'
        assert data['colors']['card_bg'] == '#FFFFFF'
        assert data['colors']['text_main'] == '#1E293B'
    
    def test_get_fallback_theme_data_dark(self, service):
        """Test fallback theme data for dark mode"""
        data = service.get_fallback_theme_data('dark')
        assert 'colors' in data
        assert data['colors']['primary'] == '#14B8A6'
        assert data['colors']['bg'] == '#0B1120'
        assert data['colors']['card_bg'] == '#1E293B'
        assert data['colors']['text_main'] == '#F1F5F9'
    
    @patch('os.path.exists', return_value=True)
    @patch('builtins.open', create=True)
    def test_load_theme_data_success(self, mock_open, mock_exists, service):
        """Test loading theme data from JSON file"""
        mock_file = MagicMock()
        mock_file.__enter__.return_value.read.return_value = '{"colors": {"primary": "#0D9488"}}'
        mock_open.return_value = mock_file
        
        with patch('json.load', return_value={"colors": {"primary": "#0D9488"}}):
            data = service.load_theme_data('light')
            assert data is not None
            assert 'colors' in data
    
    @patch('os.path.exists', return_value=False)
    def test_load_theme_data_file_not_found(self, mock_exists, service):
        """Test loading theme data when file doesn't exist"""
        data = service.load_theme_data('nonexistent')
        assert data is None
