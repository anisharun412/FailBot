"""Utilities for extracting data from LLM responses."""

from typing import Optional, Union, Any
from langchain_core.messages import AIMessage, BaseMessage


def extract_token_usage(response: Union[BaseMessage, Any]) -> Optional[int]:
    """
    Extract actual token usage from LLM response.
    
    Supports:
    - LangChain AIMessage with usage_metadata
    - Direct usage attribute (from OpenAI/Groq API responses)
    
    Args:
        response: LLM response object
        
    Returns:
        Total tokens used, or None if not available
    """
    # Try usage_metadata (LangChain standard)
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        usage = response.usage_metadata
        if isinstance(usage, dict):
            return usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        elif hasattr(usage, "total_tokens"):
            return usage.total_tokens
    
    # Try direct usage attribute
    if hasattr(response, "usage") and response.usage:
        usage = response.usage
        if hasattr(usage, "total_tokens"):
            return usage.total_tokens
        elif isinstance(usage, dict):
            return usage.get("total_tokens")
    
    # Try response_metadata (another common pattern)
    if hasattr(response, "response_metadata") and response.response_metadata:
        metadata = response.response_metadata
        if isinstance(metadata, dict) and "usage" in metadata:
            usage = metadata["usage"]
            if isinstance(usage, dict):
                return usage.get("total_tokens")
    
    return None


def format_error_slug(error_signature: str, max_len: int = 30) -> str:
    """
    Convert error signature to clean filename slug.
    
    Example:
        "requests.exceptions.ConnectionError: Failed to connect"
        -> "requests_exceptions_connectionerror"
    
    Args:
        error_signature: Error signature text
        max_len: Maximum length of slug
        
    Returns:
        Clean slug suitable for filenames
    """
    # Take first meaningful part (before colon or newline)
    base = error_signature.split(":")[0].split("\n")[0]
    
    # Replace non-alphanumeric with underscore, lowercase
    slug = "".join(c.lower() if c.isalnum() else "_" for c in base)
    
    # Remove consecutive underscores
    while "__" in slug:
        slug = slug.replace("__", "_")
    
    # Trim leading/trailing underscores
    slug = slug.strip("_")
    
    # Truncate if needed
    return slug[:max_len]
