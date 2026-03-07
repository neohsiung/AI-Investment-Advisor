"""
GitHub Service for interacting with GitHub API (MCP optimized)
GitHub 服務：用於與 GitHub API 互動 (MCP 優化)
"""
from __future__ import annotations
import os
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
from github import Github, Auth
from src.utils.logger import setup_logger
from src.services.settings_service import SettingsService

class GitHubService:
    """
    GitHub Service for managing issues, PRs, and repository content.
    """
    def __init__(self, user_id: str = None, settings_service: SettingsService = None):
        self.logger = setup_logger("GitHubService")
        self.settings_service = settings_service or SettingsService(user_id=user_id)
        settings = self.settings_service.get_all_settings()
        
        # Priority: DB -> Env
        self.api_key = settings.get("source_github_api_key") or os.getenv("GITHUB_TOKEN")
        self.github_client = None
        
        if self.api_key:
            try:
                auth = Auth.Token(self.api_key)
                self.github_client = Github(auth=auth)
                self.logger.info("GitHub Service initialized successfully.")
            except Exception as e:
                self.logger.error(f"Failed to initialize GitHub Service: {e}")
        else:
            self.logger.warning("GITHUB_TOKEN or source_github_api_key not found.")

    def list_issues(self, repo_full_name: str, state: str = "open") -> List[Dict[str, Any]]:
        """
        List issues for a repository.
        """
        if not self.github_client:
            return []
            
        try:
            repo = self.github_client.get_repo(repo_full_name)
            issues = repo.get_issues(state=state)
            return [
                {
                    "number": i.number,
                    "title": i.title,
                    "state": i.state,
                    "url": i.html_url,
                    "body": i.body[:200] if i.body else ""
                } for i in issues[:10]
            ]
        except Exception as e:
            self.logger.error(f"Error listing issues for {repo_full_name}: {e}")
            return []

    def get_issue_detail(self, repo_full_name: str, issue_number: int) -> Dict[str, Any]:
        """
        Get detailed information about an issue.
        """
        if not self.github_client:
            return {}
            
        try:
            repo = self.github_client.get_repo(repo_full_name)
            issue = repo.get_issue(number=issue_number)
            return {
                "number": issue.number,
                "title": issue.title,
                "body": issue.body,
                "comments": [c.body for c in issue.get_comments()],
                "state": issue.state,
                "url": issue.html_url
            }
        except Exception as e:
            self.logger.error(f"Error getting issue {issue_number} for {repo_full_name}: {e}")
            return {}

    def create_issue_comment(self, repo_full_name: str, issue_number: int, body: str) -> bool:
        """
        Add a comment to an issue.
        """
        if not self.github_client:
            return False
            
        try:
            repo = self.github_client.get_repo(repo_full_name)
            issue = repo.get_issue(number=issue_number)
            issue.create_comment(body)
            self.logger.info(f"Added comment to issue #{issue_number} in {repo_full_name}")
            return True
        except Exception as e:
            self.logger.error(f"Error commenting on issue {issue_number} in {repo_full_name}: {e}")
            return False

    def search_repos(self, query: str) -> List[Dict[str, Any]]:
        """
        Search for repositories.
        """
        if not self.github_client:
            return []
            
        try:
            repos = self.github_client.search_repositories(query=query)
            return [
                {
                    "full_name": r.full_name,
                    "description": r.description,
                    "url": r.html_url,
                    "stars": r.stargazers_count
                } for r in repos[:5]
            ]
        except Exception as e:
            self.logger.error(f"Error searching repositories for {query}: {e}")
            return []
