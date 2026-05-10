"""Ingest node: Fetch and preprocess CI logs."""

import asyncio
import logging
from typing import Any

import httpx

from src.config import get_config
from src.state import FailBotState
from src.utils.graph_utils import handle_node_error, log_node_end, log_node_start
from src.utils.logging_config import log_event
from src.utils.retry import async_retry
from src.utils.token_counter import TokenCounter


logger = logging.getLogger(__name__)


@async_retry(max_attempts=3, initial_delay=0.5, max_delay=10.0, backoff_factor=2.0)
async def fetch_log_from_source(log_source: str) -> str:
    """
    Fetch log content from URL or local file.
    
    Args:
        log_source: URL or file path to CI log
        
    Returns:
        Log content as string
        
    Raises:
        ValueError: If file doesn't exist or URL fetch fails
        httpx.HTTPError: If HTTP request fails
    """
    # Try as URL first
    if log_source.startswith(("http://", "https://")):
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(log_source)
            response.raise_for_status()
            return response.text
    
    # Try as local file
    try:
        with open(log_source, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        raise ValueError(f"Log source not found (not a URL and not a file): {log_source}")
    except IOError as e:
        raise ValueError(f"Error reading log file {log_source}: {e}")


async def ingest_node(state: FailBotState) -> dict[str, Any]:
    """
    Ingest node: Fetch CI log and preprocess (truncate to token limit).
    
    Fetches log from URL or file, truncates to configured token limit using
    head+tail strategy, and stores both full and truncated versions in state.
    
    Args:
        state: FailBotState with log_source set
        
    Returns:
        Updated state dict with:
        - log_text_full: Original log content
        - log_text: Truncated log content
        - log_text_truncated_reason: Reason for truncation (or None)
        - raw_log_length: Character count of original log
        - token_counts: Dict with 'ingest_input' and 'ingest_output' tokens
        - status: Updated to 'ingest_complete'
        - errors: Appended with any errors
    """
    start_time = log_node_start(
        logger, state["run_id"], "ingest", state
    )
    
    try:
        config = get_config()
        token_counter = TokenCounter("gpt-4o-mini")
        max_tokens = config.get_token_limit("ingest")
        
        # Fetch log from source
        log_event(
            logger, state["run_id"], "ingest",
            "fetch_start", {"log_source": state["log_source"]}
        )
        
        log_text_full = await fetch_log_from_source(state["log_source"])
        
        log_event(
            logger, state["run_id"], "ingest",
            "fetch_complete", {"log_length": len(log_text_full)}
        )
        
        # Track raw log size
        raw_log_length = len(log_text_full)
        input_tokens = token_counter.count_tokens(log_text_full)
        
        # Truncate to token limit
        log_text, truncation_reason = token_counter.truncate_to_limit(
            log_text_full, max_tokens, strategy="head_tail"
        )
        
        output_tokens = token_counter.count_tokens(log_text)
        
        log_event(
            logger, state["run_id"], "ingest",
            "truncate_complete",
            {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "truncation_reason": truncation_reason,
                "truncation_pct": (1 - len(log_text) / len(log_text_full)) * 100
                if log_text_full else 0
            }
        )
        
        # Update state
        state["log_text_full"] = log_text_full
        state["log_text"] = log_text
        state["log_text_truncated_reason"] = truncation_reason
        state["raw_log_length"] = raw_log_length
        
        # Track tokens
        if "token_counts" not in state or state["token_counts"] is None:
            state["token_counts"] = {}
        state["token_counts"]["ingest_input"] = input_tokens
        state["token_counts"]["ingest_output"] = output_tokens
        
        state["status"] = "ingest_complete"
        
        log_node_end(logger, state["run_id"], "ingest", state, start_time)
        
        return state
        
    except Exception as e:
        error_msg = f"Ingest node failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        if "errors" not in state or state["errors"] is None:
            state["errors"] = []
        state["errors"].append({
            "node": "ingest",
            "error": str(e),
            "type": type(e).__name__
        })
        
        state["status"] = "ingest_failed"
        handle_node_error(logger, state["run_id"], "ingest", e, state)
        
        raise
