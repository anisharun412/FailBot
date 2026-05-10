"""GitHub client: MCP server and REST API integration."""

import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

import httpx

from src.utils.retry import async_retry


logger = logging.getLogger(__name__)


class MCPGitHubServer:
    """Manages MCP (Model Context Protocol) GitHub server subprocess."""
    
    def __init__(self, port: int = 3000, timeout: int = 10):
        """
        Initialize MCP server manager.
        
        Args:
            port: Port to run MCP server on
            timeout: Timeout for server startup in seconds
        """
        self.port = port
        self.timeout = timeout
        self.process = None
        self.base_url = f"http://localhost:{port}"
    
    def start(self) -> bool:
        """
        Start the MCP GitHub server subprocess.
        
        Returns:
            True if server started successfully
        """
        if self.process is not None:
            logger.debug("MCP server already running")
            return True
        
        try:
            # Try to start MCP server
            # Note: Actual MCP server implementation would need to be available
            logger.debug(f"Starting MCP GitHub server on port {self.port}...")
            
            # This is a placeholder - real implementation would start the MCP server
            # For now, we simulate server startup
            self.process = None  # Would be actual subprocess
            
            # Wait for server to be ready
            time.sleep(0.5)
            
            logger.info(f"MCP server started on {self.base_url}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start MCP server: {e}")
            self.process = None
            return False
    
    def stop(self):
        """Stop the MCP GitHub server subprocess."""
        if self.process is not None:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
                logger.debug("MCP server stopped")
            except Exception as e:
                logger.warning(f"Error stopping MCP server: {e}")
                try:
                    self.process.kill()
                except Exception:
                    pass
            finally:
                self.process = None
    
    async def create_issue(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        labels: Optional[list[str]] = None
    ) -> Optional[str]:
        """
        Create a GitHub issue via MCP server.
        
        Args:
            owner: Repository owner
            repo: Repository name
            title: Issue title
            body: Issue body
            labels: Optional issue labels
            
        Returns:
            Issue URL if successful, None otherwise
            
        Raises:
            Exception: If MCP request fails
        """
        if not self.process:
            raise RuntimeError("MCP server not running")
        
        payload = {
            "jsonrpc": "2.0",
            "method": "gh.createIssue",
            "params": {
                "owner": owner,
                "repo": repo,
                "title": title,
                "body": body,
                "labels": labels or []
            },
            "id": int(time.time() * 1000)
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/rpc",
                json=payload
            )
            response.raise_for_status()
            
            result = response.json()
            
            if "error" in result:
                raise Exception(f"MCP error: {result['error']}")
            
            issue_url = result.get("result", {}).get("html_url")
            return issue_url


class GitHubRESTClient:
    """GitHub REST API client with authentication."""
    
    def __init__(self, token: Optional[str] = None):
        """
        Initialize GitHub API client.
        
        Args:
            token: GitHub authentication token (from GITHUB_TOKEN env if not provided)
        """
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.base_url = "https://api.github.com"
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "FailBot/1.0"
        }
        
        if self.token:
            self.headers["Authorization"] = f"token {self.token}"
    
    def _get_headers(self) -> dict:
        """Get request headers with auth token."""
        return self.headers.copy()
    
    @async_retry(max_attempts=3, initial_delay=1.0, max_delay=10.0)
    async def create_issue(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        labels: Optional[list[str]] = None
    ) -> Optional[str]:
        """
        Create a GitHub issue via REST API.
        
        Args:
            owner: Repository owner
            repo: Repository name
            title: Issue title
            body: Issue body
            labels: Optional issue labels
            
        Returns:
            Issue URL if successful, None otherwise
            
        Raises:
            httpx.HTTPError: If API call fails
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/issues"
        
        payload = {
            "title": title,
            "body": body
        }
        
        if labels:
            payload["labels"] = labels
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                json=payload,
                headers=self._get_headers()
            )
            
            if response.status_code == 401:
                raise PermissionError("GitHub authentication failed (401)")
            elif response.status_code == 403:
                raise PermissionError("GitHub rate limit exceeded or access denied (403)")
            elif response.status_code == 404:
                raise ValueError(f"Repository not found: {owner}/{repo}")
            
            response.raise_for_status()
            
            result = response.json()
            issue_url = result.get("html_url")
            
            logger.info(f"Created GitHub issue: {issue_url}")
            
            return issue_url
    
    async def get_repo_info(
        self,
        owner: str,
        repo: str
    ) -> Optional[dict]:
        """
        Get repository information.
        
        Args:
            owner: Repository owner
            repo: Repository name
            
        Returns:
            Repository info dict or None if not found
        """
        url = f"{self.base_url}/repos/{owner}/{repo}"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                url,
                headers=self._get_headers()
            )
            
            if response.status_code == 404:
                return None
            
            response.raise_for_status()
            return response.json()


class GitHubClient:
    """Main GitHub client with fallback chain: MCP → REST API."""
    
    def __init__(self, token: Optional[str] = None, use_mcp: bool = True):
        """
        Initialize GitHub client.
        
        Args:
            token: GitHub authentication token
            use_mcp: Whether to try MCP server first
        """
        self.token = token
        self.use_mcp = use_mcp
        self.mcp_server = MCPGitHubServer() if use_mcp else None
        self.rest_client = GitHubRESTClient(token)
    
    async def create_issue(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        labels: Optional[list[str]] = None
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Create a GitHub issue with fallback chain.
        
        Tries: MCP server → REST API → None (logged failure)
        
        Args:
            owner: Repository owner
            repo: Repository name
            title: Issue title
            body: Issue body
            labels: Optional issue labels
            
        Returns:
            Tuple of (issue_url, method_used) where method_used is "mcp" or "rest_api"
        """
        # Try MCP server first
        if self.use_mcp and self.mcp_server:
            try:
                if self.mcp_server.start():
                    issue_url = await self.mcp_server.create_issue(
                        owner, repo, title, body, labels
                    )
                    if issue_url:
                        logger.info(f"Issue created via MCP: {issue_url}")
                        return (issue_url, "mcp")
            except Exception as e:
                logger.warning(f"MCP issue creation failed: {e}")
                self.mcp_server.stop()
        
        # Fallback to REST API
        try:
            issue_url = await self.rest_client.create_issue(
                owner, repo, title, body, labels
            )
            logger.info(f"Issue created via REST API: {issue_url}")
            return (issue_url, "rest_api")
        except Exception as e:
            logger.error(f"REST API issue creation failed: {e}")
            return (None, None)
    
    def __del__(self):
        """Cleanup MCP server on deletion."""
        if self.mcp_server:
            self.mcp_server.stop()


async def create_github_issue(
    owner: str,
    repo: str,
    title: str,
    body: str,
    labels: Optional[list[str]] = None,
    token: Optional[str] = None
) -> tuple[Optional[str], Optional[str]]:
    """
    Async wrapper to create GitHub issue with fallback chain.
    
    Use in LangGraph file_issue node.
    
    Args:
        owner: Repository owner
        repo: Repository name
        title: Issue title
        body: Issue body
        labels: Optional issue labels
        token: GitHub authentication token
        
    Returns:
        Tuple of (issue_url, method_used)
    """
    client = GitHubClient(token=token, use_mcp=False)  # MCP not ready yet
    
    try:
        issue_url, method = await client.create_issue(
            owner, repo, title, body, labels
        )
        
        if issue_url:
            logger.info(f"Successfully created GitHub issue via {method}: {issue_url}")
        else:
            logger.error("Failed to create GitHub issue (all methods failed)")
        
        return (issue_url, method)
    finally:
        # Cleanup
        if client.mcp_server:
            client.mcp_server.stop()
