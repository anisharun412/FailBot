"""
Retry Decorator and Backoff Utilities

Implements exponential backoff retry logic for async functions.
"""

import asyncio
import random
import logging
from functools import wraps
from typing import Callable, Type, Tuple, Optional, Any

logger = logging.getLogger(__name__)


class RetryError(Exception):
    """Raised when all retry attempts are exhausted."""
    
    def __init__(self, max_attempts: int, last_exception: Exception):
        self.max_attempts = max_attempts
        self.last_exception = last_exception
        super().__init__(
            f"Failed after {max_attempts} attempts: {str(last_exception)}"
        )


def should_retry(exception: Exception) -> bool:
    """
    Determine if an exception should trigger a retry.
    
    Retryable exceptions:
    - openai.error.APIError, RateLimitError, Timeout
    - httpx.HTTPError
    - asyncio.TimeoutError
    - ConnectionError, TimeoutError, OSError
    
    Args:
        exception: Exception to check
    
    Returns:
        True if exception is retryable
    """
    retryable_patterns = [
        "APIError",
        "RateLimitError",
        "Timeout",
        "HTTPError",
        "ConnectionError",
        "TimeoutError",
        "OSError",
    ]
    
    exception_name = type(exception).__name__
    exception_str = str(exception).lower()
    
    # Check exception type name
    for pattern in retryable_patterns:
        if pattern in exception_name or pattern.lower() in exception_str:
            return True
    
    # Check exception message for retryable indicators
    if any(phrase in exception_str for phrase in ["timeout", "connection", "rate limit", "temporarily"]):
        return True
    
    return False


def async_retry(
    max_attempts: int = 3,
    initial_delay: float = 0.5,
    max_delay: float = 10.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    retryable: Callable[[Exception], bool] = should_retry,
):
    """
    Decorator for async functions with exponential backoff retry logic.
    
    Usage:
        @async_retry(max_attempts=3, initial_delay=0.5)
        async def call_llm(...):
            return await llm.ainvoke(...)
    
    Args:
        max_attempts: Maximum number of attempts
        initial_delay: Initial delay in seconds (e.g., 0.5)
        max_delay: Maximum delay between retries (e.g., 10.0)
        backoff_factor: Exponential backoff multiplier (e.g., 2.0)
        jitter: Add randomness to delay (0.8-1.2 multiplier)
        retryable: Function to determine if exception should retry
    
    Returns:
        Decorated async function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception: Optional[Exception] = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    result = await func(*args, **kwargs)
                    if attempt > 1:
                        logger.info(
                            f"✓ {func.__name__} succeeded on attempt {attempt}"
                        )
                    return result
                
                except Exception as e:
                    last_exception = e
                    
                    # Check if we should retry
                    if not retryable(e):
                        logger.error(
                            f"✗ {func.__name__} failed with non-retryable error: {e}"
                        )
                        raise
                    
                    # Check if max attempts reached
                    if attempt >= max_attempts:
                        logger.error(
                            f"✗ {func.__name__} failed after {max_attempts} attempts"
                        )
                        raise RetryError(max_attempts, last_exception)
                    
                    # Calculate delay
                    delay = min(
                        initial_delay * (backoff_factor ** (attempt - 1)),
                        max_delay
                    )
                    
                    # Add jitter
                    if jitter:
                        delay *= random.uniform(0.8, 1.2)
                    
                    logger.warning(
                        f"⚠ {func.__name__} attempt {attempt} failed: {type(e).__name__}. "
                        f"Retrying in {delay:.2f}s... ({max_attempts - attempt} attempts left)"
                    )
                    
                    await asyncio.sleep(delay)
            
            # Should not reach here, but just in case
            raise RetryError(max_attempts, last_exception)
        
        return wrapper
    return decorator


def sync_retry(
    max_attempts: int = 3,
    initial_delay: float = 0.5,
    max_delay: float = 10.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    retryable: Callable[[Exception], bool] = should_retry,
):
    """
    Decorator for sync functions with exponential backoff retry logic.
    
    Args: Same as async_retry
    
    Returns:
        Decorated function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception: Optional[Exception] = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    result = func(*args, **kwargs)
                    if attempt > 1:
                        logger.info(
                            f"✓ {func.__name__} succeeded on attempt {attempt}"
                        )
                    return result
                
                except Exception as e:
                    last_exception = e
                    
                    if not retryable(e):
                        logger.error(
                            f"✗ {func.__name__} failed with non-retryable error: {e}"
                        )
                        raise
                    
                    if attempt >= max_attempts:
                        logger.error(
                            f"✗ {func.__name__} failed after {max_attempts} attempts"
                        )
                        raise RetryError(max_attempts, last_exception)
                    
                    delay = min(
                        initial_delay * (backoff_factor ** (attempt - 1)),
                        max_delay
                    )
                    
                    if jitter:
                        delay *= random.uniform(0.8, 1.2)
                    
                    logger.warning(
                        f"⚠ {func.__name__} attempt {attempt} failed: {type(e).__name__}. "
                        f"Retrying in {delay:.2f}s..."
                    )
                    
                    asyncio.run(asyncio.sleep(delay)) if asyncio.iscoroutinefunction(
                        func
                    ) else __import__("time").sleep(delay)
            
            raise RetryError(max_attempts, last_exception)
        
        return wrapper
    return decorator


# Test function
if __name__ == "__main__":
    import asyncio
    
    @async_retry(max_attempts=3, initial_delay=0.1, max_delay=0.5)
    async def test_flaky_operation():
        """Simulate a flaky operation that fails twice then succeeds."""
        global attempt_count
        attempt_count = getattr(test_flaky_operation, 'attempt_count', 0) + 1
        test_flaky_operation.attempt_count = attempt_count
        
        if attempt_count < 3:
            raise ConnectionError("Network error")
        return "Success!"
    
    async def main():
        try:
            result = await test_flaky_operation()
            print(f"✓ Result: {result}")
        except Exception as e:
            print(f"✗ Failed: {e}")
    
    asyncio.run(main())
