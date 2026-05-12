"""
Token Counter Utility

Handles token counting and log truncation for different LLM models.
"""

from typing import Tuple, Optional
import tiktoken


class TokenCounter:
    """Count and truncate text to token limits based on model."""
    
    def __init__(self, model_name: str = "gpt-4o-mini"):
        """
        Initialize token counter for a specific model.
        
        Args:
            model_name: Name of the model (e.g., "gpt-4o-mini", "gpt-4", "claude-3")
        """
        self.model_name = model_name
        
        # Map models to encoding
        encoding_name = "o200k_base"  # For gpt-4o, gpt-4-turbo, gpt-4o-mini
        if "claude" in model_name.lower():
            encoding_name = "cl100k_base"  # Approximate for Claude
        elif "gpt-3.5" in model_name:
            encoding_name = "cl100k_base"
        
        try:
            self.encoding = tiktoken.get_encoding(encoding_name)
        except Exception:
            # Fallback to cl100k_base if specific encoding not found
            self.encoding = tiktoken.get_encoding("cl100k_base")
    
    def count_tokens(self, text: str) -> int:
        """
        Count tokens in text.
        
        Args:
            text: Text to count tokens for
        
        Returns:
            Number of tokens
        """
        if not text:
            return 0
        return len(self.encoding.encode(text))
    
    def truncate_to_limit(
        self,
        text: str,
        max_tokens: int,
        strategy: str = "head_tail"
    ) -> Tuple[str, str]:
        """
        Truncate text to fit within token limit.
        
        Args:
            text: Text to truncate
            max_tokens: Maximum tokens allowed
            strategy: "head_tail" keeps first 1/3 + last 2/3 tokens
                     "tail" keeps only last tokens
        
        Returns:
            Tuple of (truncated_text, truncation_reason)
            If no truncation needed, truncation_reason is empty string
        """
        token_count = self.count_tokens(text)
        
        if token_count <= max_tokens:
            return text, ""
        
        if strategy == "head_tail":
            # Keep first 1/3 and last 2/3 of tokens
            head_tokens = max_tokens // 3
            tail_tokens = max(0, max_tokens - head_tokens)
            
            # Encode and split
            encoded = self.encoding.encode(text)
            head = encoded[:head_tokens] if head_tokens > 0 else []
            tail = encoded[-tail_tokens:] if tail_tokens > 0 else []
            
            # Decode back
            head_text = self.encoding.decode(head)
            tail_text = self.encoding.decode(tail)
            
            if tail_tokens > 0:
                truncated = (
                    f"{head_text}\n\n...[TRUNCATED - {token_count - max_tokens} tokens removed]...\n\n"
                    f"{tail_text}"
                )
            else:
                truncated = f"{head_text}\n\n...[TRUNCATED - {token_count - max_tokens} tokens removed]..."
            reason = f"Log truncated: {token_count} tokens → {max_tokens} tokens (head+tail strategy)"
        
        else:  # strategy == "tail"
            # Keep only last N tokens
            encoded = self.encoding.encode(text)
            tail = encoded[-max_tokens:]
            truncated = self.encoding.decode(tail)
            reason = f"Log truncated: {token_count} tokens → {max_tokens} tokens (tail strategy)"
        
        return truncated, reason
    
    def estimate_tokens(self, prompt_template: str, **kwargs) -> int:
        """
        Estimate token count for a template with variables.
        
        Args:
            prompt_template: Template string with {variable} placeholders
            **kwargs: Values to fill in
        
        Returns:
            Estimated token count after formatting
        """
        try:
            formatted = prompt_template.format(**kwargs)
            return self.count_tokens(formatted)
        except KeyError:
            # If not all placeholders can be filled, estimate based on template
            return self.count_tokens(prompt_template)


# Default counter instance
_default_counter: Optional[TokenCounter] = None


def get_token_counter(model_name: str = "gpt-4o-mini") -> TokenCounter:
    """
    Get or create a token counter for the specified model.
    
    Args:
        model_name: Model name
    
    Returns:
        TokenCounter instance
    """
    global _default_counter
    
    if _default_counter is None or _default_counter.model_name != model_name:
        _default_counter = TokenCounter(model_name)
    
    return _default_counter


def count_tokens(text: str, model_name: str = "gpt-4o-mini") -> int:
    """
    Quick function to count tokens without creating a counter.
    
    Args:
        text: Text to count
        model_name: Model name
    
    Returns:
        Token count
    """
    counter = get_token_counter(model_name)
    return counter.count_tokens(text)


def truncate_log(
    text: str,
    max_tokens: int = 8000,
    model_name: str = "gpt-4o-mini"
) -> Tuple[str, str]:
    """
    Quick function to truncate text to token limit.
    
    Args:
        text: Text to truncate
        max_tokens: Maximum tokens
        model_name: Model name
    
    Returns:
        Tuple of (truncated_text, reason)
    """
    counter = get_token_counter(model_name)
    return counter.truncate_to_limit(text, max_tokens, strategy="head_tail")


if __name__ == "__main__":
    # Test token counter
    counter = TokenCounter("gpt-4o-mini")
    
    test_text = "This is a test. " * 100
    token_count = counter.count_tokens(test_text)
    print(f"Test text: {len(test_text)} chars, {token_count} tokens")
    
    truncated, reason = counter.truncate_to_limit(test_text, max_tokens=50)
    new_count = counter.count_tokens(truncated)
    print(f"Truncated: {len(truncated)} chars, {new_count} tokens")
    print(f"Reason: {reason}")
