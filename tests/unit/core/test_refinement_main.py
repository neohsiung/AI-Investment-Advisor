import pytest
from unittest.mock import patch, MagicMock
from src.refinement import main

class TestRefinementMain:
    @patch('src.refinement.RefinementService')
    @patch('asyncio.run')
    def test_main(self, mock_asyncio_run, MockRefinementService):
        mock_service = MockRefinementService.return_value
        main()
        MockRefinementService.assert_called_once()
        mock_asyncio_run.assert_called_once()
