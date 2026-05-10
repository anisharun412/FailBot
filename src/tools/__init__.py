"""FailBot tools package."""

from src.tools.code_validator import CodeValidator, validate_code
from src.tools.github_client import GitHubClient, GitHubRESTClient, MCPGitHubServer, create_github_issue
from src.tools.knowledge_base import KnownErrorsDB, get_knowledge_base, lookup_known_errors
from src.tools.langchain_tools import (
    FAILBOT_TOOLS,
    get_bound_model,
    validate_code_syntax,
    detect_code_hallucinations,
    lookup_error_patterns,
    create_github_issue,
)

__all__ = [
    # Knowledge base
    "KnownErrorsDB",
    "get_knowledge_base",
    "lookup_known_errors",
    # Code validation
    "CodeValidator",
    "validate_code",
    # GitHub
    "MCPGitHubServer",
    "GitHubRESTClient",
    "GitHubClient",
    # LangChain tools (with tool binding support)
    "FAILBOT_TOOLS",
    "get_bound_model",
    "validate_code_syntax",
    "detect_code_hallucinations",
    "lookup_error_patterns",
    "create_github_issue",
]
