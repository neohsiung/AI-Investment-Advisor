import pytest
from unittest.mock import MagicMock, patch
import sys
import os

# Ensure src is in path
sys.path.append(os.getcwd())

from src.services.github_service import GitHubService

class TestGitHubService:
    @patch('src.services.github_service.Github')
    @patch('src.services.github_service.SettingsService')
    def test_list_issues(self, mock_settings_class, mock_github_class):
        # Setup mock Settings
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {"source_github_api_key": "test_key"}
        mock_settings_class.return_value = mock_settings
        
        # Setup mock Repo/Issue
        mock_repo = MagicMock()
        mock_issue = MagicMock()
        mock_issue.number = 1
        mock_issue.title = "Test Issue"
        mock_issue.state = "open"
        mock_issue.user.login = "testuser"
        mock_issue.body = "Sample body"
        mock_repo.get_issues.return_value = [mock_issue]
        
        mock_gh = MagicMock()
        mock_github_class.return_value = mock_gh
        mock_gh.get_repo.return_value = mock_repo
        
        service = GitHubService(user_id="test_user")
        result = service.list_issues("owner/repo", state="open")
        
        assert len(result) == 1
        assert result[0]['number'] == 1
        assert result[0]['title'] == "Test Issue"

    @patch('src.services.github_service.Github')
    @patch('src.services.github_service.SettingsService')
    def test_get_issue_detail(self, mock_settings_class, mock_github_class):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {"source_github_api_key": "test_key"}
        mock_settings_class.return_value = mock_settings

        # Setup mock
        mock_repo = MagicMock()
        mock_issue = MagicMock()
        mock_issue.number = 1
        mock_issue.title = "Test Issue"
        mock_issue.body = "Issue Body"
        mock_comment = MagicMock()
        mock_comment.body = "Comment 1"
        mock_issue.get_comments.return_value = [mock_comment]
        mock_issue.state = "open"
        mock_issue.html_url = "http://github.com/issue/1"
        mock_repo.get_issue.return_value = mock_issue
        
        mock_gh = MagicMock()
        mock_github_class.return_value = mock_gh
        mock_gh.get_repo.return_value = mock_repo
        
        service = GitHubService(user_id="test_user")
        result = service.get_issue_detail("owner/repo", 1)
        
        assert result['number'] == 1
        assert result['title'] == "Test Issue"
        assert result['body'] == "Issue Body"
        assert "Comment 1" in result['comments']

    @patch('src.services.github_service.Github')
    @patch('src.services.github_service.SettingsService')
    def test_search_repos(self, mock_settings_class, mock_github_class):
        mock_settings = MagicMock()
        mock_settings.get_all_settings.return_value = {"source_github_api_key": "test_key"}
        mock_settings_class.return_value = mock_settings

        # Setup mock
        mock_repo = MagicMock()
        mock_repo.full_name = "owner/repo"
        mock_repo.description = "Test Repo"
        mock_repo.stargazers_count = 100
        mock_repo.html_url = "http://github.com/repo"
        
        mock_gh = MagicMock()
        mock_github_class.return_value = mock_gh
        mock_gh.search_repositories.return_value = [mock_repo]
        
        service = GitHubService(user_id="test_user")
        result = service.search_repos("test query")
        
        assert len(result) == 1
        assert result[0]['full_name'] == "owner/repo"
        assert result[0]['stars'] == 100
