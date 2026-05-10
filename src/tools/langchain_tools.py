"""
LangChain Tool Definitions for FailBot

Defines tools using @tool decorator for proper LangGraph integration.
Tools are automatically bound to language models for agent usage.
"""

from langchain_core.tools import tool
import logging
import os
from typing import Optional

from src.tools.code_validator import CodeValidator
from src.tools.knowledge_base import get_knowledge_base
from src.tools.github_client import GitHubRESTClient

logger = logging.getLogger(__name__)


@tool
def validate_code_syntax(code: str, language: str = "python") -> dict:
    """
    Validate generated code for syntax errors.
    
    Use this tool to check if generated test code or other code has valid syntax.
    
    Args:
        code: The code to validate
        language: Programming language ('python', 'javascript', etc.)
        
    Returns:
        Dictionary with:
        - is_valid: True if syntax is correct
        - error: Error message if invalid, None otherwise
        - language: The language checked
    """
    validator = CodeValidator()
    
    if language.lower() == "python":
        is_valid, error = validator.validate_python_syntax(code)
    elif language.lower() in ["javascript", "js"]:
        is_valid, error = validator.validate_javascript_syntax(code)
    else:
        # Default to Python
        is_valid, error = validator.validate_python_syntax(code)
    
    return {
        "is_valid": is_valid,
        "error": error,
        "language": language
    }


@tool
def detect_code_hallucinations(code: str, language: str = "python") -> dict:
    """
    Detect common hallucinations in generated code.
    
    Use this tool to identify hallucinated functions, missing imports, or invalid test patterns.
    
    Args:
        code: The code to analyze
        language: Programming language ('python', 'javascript', etc.)
        
    Returns:
        Dictionary with:
        - has_hallucinations: True if issues found
        - issues: List of detected hallucination issues
        - confidence_penalty: Penalty to apply (0.0-1.0)
    """
    validator = CodeValidator()
    hallucinations = validator.detect_hallucinations(code, language)
    
    return {
        "has_hallucinations": len(hallucinations) > 0,
        "issues": hallucinations,
        "confidence_penalty": 0.1 * len(hallucinations)  # 10% penalty per issue
    }


@tool
def lookup_error_patterns(error_signature: str, top_k: int = 3) -> dict:
    """
    Look up known error patterns in the knowledge base.
    
    Use this tool to find similar errors and their solutions in the knowledge base.
    
    Args:
        error_signature: The error to search for
        top_k: Number of matches to return (default 3)
        
    Returns:
        Dictionary with:
        - matches_found: Number of matches
        - matches: List of matching error patterns with details
        - best_match: The highest scoring match if any
    """
    kb = get_knowledge_base()
    matches = kb.lookup(error_signature, top_k=top_k, threshold=0.80)
    
    best_match = None
    if matches:
        best_match = matches[0]
    
    return {
        "matches_found": len(matches),
        "matches": matches,
        "best_match": best_match
    }


@tool
def create_github_issue(
    title: str,
    body: str,
    owner: str = "unknown",
    repo: str = "unknown",
    labels: Optional[list[str]] = None
) -> dict:
    """
    Create a GitHub issue for the failure.
    
    Use this tool to file a GitHub issue with the triage results and test suggestions.
    Falls back to local markdown file if GitHub API is unavailable.
    
    Args:
        title: Issue title
        body: Issue body (markdown format)
        owner: GitHub repository owner
        repo: GitHub repository name
        labels: Optional list of labels to add (default: ['failbot'])
        
    Returns:
        Dictionary with:
        - success: True if issue created successfully
        - issue_url: URL of created issue or path to local markdown file
        - method: 'github_api', 'local_markdown', or 'failed'
        - error: Error message if failed
    """
    if labels is None:
        labels = ["failbot"]
    
    github_token = os.getenv("GITHUB_TOKEN")
    
    try:
        # Try GitHub API first
        client = GitHubRESTClient(token=github_token)
        issue_url = client.create_issue(
            owner=owner,
            repo=repo,
            title=title,
            body=body,
            labels=labels
        )
        
        return {
            "success": True,
            "issue_url": issue_url,
            "method": "github_api",
            "error": None
        }
    
    except Exception as api_error:
        logger.warning(f"GitHub API failed: {api_error}, attempting fallback...")
        
        # Fallback to local markdown
        try:
            from pathlib import Path
            from datetime import datetime
            
            output_path = Path("runs")
            output_path.mkdir(parents=True, exist_ok=True)
            
            safe_title = "".join(c if c.isalnum() or c in "-_ " else "" for c in title)[:50]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"issue_{timestamp}_{safe_title}.md"
            
            file_path = output_path / filename
            
            issue_content = f"""# {title}

{body}

---
*Created by FailBot (GitHub API fallback)*
*Timestamp: {datetime.now().isoformat()}*
"""
            
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(issue_content)
            
            return {
                "success": True,
                "issue_url": str(file_path),
                "method": "local_markdown",
                "error": None
            }
        
        except Exception as fallback_error:
            return {
                "success": False,
                "issue_url": None,
                "method": "failed",
                "error": f"Both GitHub API and local fallback failed: {str(fallback_error)}"
            }


# Export tools as a list for easy binding
FAILBOT_TOOLS = [
    validate_code_syntax,
    detect_code_hallucinations,
    lookup_error_patterns,
    create_github_issue,
]


def get_bound_model(model):
    """
    Bind all FailBot tools to a language model.
    
    Args:
        model: LangChain ChatModel instance
        
    Returns:
        Model with tools bound
    """
    return model.bind_tools(FAILBOT_TOOLS)
