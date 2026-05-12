"""GitHub client: MCP server and REST API integration."""

import asyncio
import json
import logging
import os
import re
import shlex
from typing import Any, Optional

import httpx

from src.utils.retry import async_retry
from src.utils.retry import PermanentError


logger = logging.getLogger(__name__)


class MCPGitHubServer:
    """Manages MCP (Model Context Protocol) GitHub server subprocess."""

    def __init__(self, command: Optional[str] = None, timeout: int = 10):
        """
        Initialize MCP server manager.

        Args:
            command: Command to start MCP GitHub server
            timeout: Timeout for server startup in seconds
        """
        self.command = command or os.getenv(
            "MCP_GITHUB_SERVER_CMD",
            "npx -y @modelcontextprotocol/server-github"
        )
        self.timeout = timeout
        self.process: Optional[asyncio.subprocess.Process] = None
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self._stderr_task: Optional[asyncio.Task] = None
        self._next_id = 1
        self._request_lock = asyncio.Lock()

    async def start(self) -> bool:
        """
        Start the MCP GitHub server subprocess.

        Returns:
            True if server started successfully
        """
        if self.process is not None:
            logger.debug("MCP server already running")
            return True

        try:
            args = shlex.split(self.command)
            if not args:
                raise ValueError("MCP_GITHUB_SERVER_CMD is empty")

            env = os.environ.copy()
            self.process = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            self.reader = self.process.stdout
            self.writer = self.process.stdin
            self._stderr_task = asyncio.create_task(self._drain_stderr())

            await asyncio.wait_for(self._initialize(), timeout=self.timeout)
            logger.info("MCP GitHub server initialized")
            return True
        except Exception as e:
            logger.error(f"Failed to start MCP server: {e}")
            await self.stop()
            return False

    async def stop(self) -> None:
        """Stop the MCP GitHub server subprocess."""
        if self._stderr_task:
            self._stderr_task.cancel()
            self._stderr_task = None

        if self.process is not None:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=5)
                logger.debug("MCP server stopped")
            except Exception as e:
                logger.warning(f"Error stopping MCP server: {e}")
                try:
                    self.process.kill()
                except Exception:
                    pass
            finally:
                self.process = None
                self.reader = None
                self.writer = None

    async def _drain_stderr(self) -> None:
        if not self.process or not self.process.stderr:
            return

        while True:
            line = await self.process.stderr.readline()
            if not line:
                break
            logger.debug("MCP stderr: %s", line.decode(errors="ignore").rstrip())

    async def _send_message(self, payload: dict) -> None:
        if not self.writer:
            raise RuntimeError("MCP server not initialized")

        body = json.dumps(payload)
        header = f"Content-Length: {len(body.encode('utf-8'))}\r\n\r\n"
        self.writer.write(header.encode("utf-8") + body.encode("utf-8"))
        await self.writer.drain()

    async def _read_message(self) -> dict:
        if not self.reader:
            raise RuntimeError("MCP server not initialized")

        headers = {}
        while True:
            line = await self.reader.readline()
            if not line:
                raise RuntimeError("MCP server closed connection")
            if line in (b"\r\n", b"\n"):
                break
            key, _, value = line.decode("utf-8").partition(":")
            headers[key.lower()] = value.strip()

        content_length = int(headers.get("content-length", "0"))
        if content_length <= 0:
            raise RuntimeError("Invalid MCP message framing")

        body = await self.reader.readexactly(content_length)
        return json.loads(body.decode("utf-8"))

    async def _request(self, method: str, params: dict) -> dict:
        async with self._request_lock:
            request_id = self._next_id
            self._next_id += 1

            await self._send_message({
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            })

            while True:
                response = await self._read_message()
                if response.get("id") != request_id:
                    continue
                if "error" in response:
                    raise RuntimeError(response["error"])
                return response

    async def _notify(self, method: str, params: dict) -> None:
        await self._send_message({
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        })

    async def _initialize(self) -> None:
        await self._request(
            "initialize",
            {
                "protocolVersion": os.getenv("MCP_PROTOCOL_VERSION", "2024-11-05"),
                "capabilities": {},
                "clientInfo": {"name": "failbot", "version": "1.0"},
            },
        )
        await self._notify("initialized", {})

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

        tool_name = os.getenv("MCP_GITHUB_TOOL_CREATE_ISSUE", "create_issue")
        response = await self._request(
            "tools/call",
            {
                "name": tool_name,
                "arguments": {
                    "owner": owner,
                    "repo": repo,
                    "title": title,
                    "body": body,
                    "labels": labels or [],
                },
            },
        )

        return _extract_issue_url(response.get("result"))

    def __del__(self) -> None:
        if self.process is not None:
            try:
                self.process.terminate()
            except Exception:
                pass


class GitHubAuthenticationError(PermanentError):
    """GitHub authentication failed."""


class GitHubAuthorizationError(PermanentError):
    """GitHub authorization failed or rate limited."""


class GitHubNotFoundError(PermanentError):
    """GitHub repository or resource was not found."""


def _extract_issue_url(result: Optional[dict]) -> Optional[str]:
    if not result:
        return None
    if isinstance(result, dict):
        for key in ("issue_url", "html_url", "url"):
            value = result.get(key)
            if isinstance(value, str) and "github.com" in value:
                return value

        content = result.get("content")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text") or item.get("content")
                else:
                    text = item
                if isinstance(text, str):
                    match = re.search(r"https://github.com/\S+", text)
                    if match:
                        return match.group(0)
    return None


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
        
        payload: dict[str, Any] = {
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
                raise GitHubAuthenticationError("GitHub authentication failed (401)")
            elif response.status_code == 403:
                raise GitHubAuthorizationError("GitHub rate limit exceeded or access denied (403)")
            elif response.status_code == 404:
                raise GitHubNotFoundError(f"Repository not found: {owner}/{repo}")
            
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
                if await self.mcp_server.start():
                    issue_url = await self.mcp_server.create_issue(
                        owner, repo, title, body, labels
                    )
                    if issue_url:
                        logger.info(f"Issue created via MCP: {issue_url}")
                        return (issue_url, "mcp")
            except Exception as e:
                logger.warning(f"MCP issue creation failed: {e}")
                await self.mcp_server.stop()
        
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
    
    async def aclose(self) -> None:
        """Cleanup MCP server when finished."""
        if self.mcp_server:
            await self.mcp_server.stop()

    def __del__(self):
        if self.mcp_server:
            try:
                process = getattr(self.mcp_server, "process", None)
                if process is not None:
                    process.terminate()
            except Exception:
                pass


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
    use_mcp_env = os.getenv("FAILBOT_USE_MCP", "true").strip().lower()
    use_mcp = use_mcp_env in {"1", "true", "yes", "on"}
    client = GitHubClient(token=token, use_mcp=use_mcp)
    
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
        await client.aclose()
