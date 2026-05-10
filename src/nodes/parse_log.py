"""Parse log node: Extract error signature and context."""

import json
import logging
import re
from typing import Any, Optional

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, ValidationError

from src.config import get_config
from src.state import FailBotState
from src.utils.graph_utils import handle_node_error, log_node_end, log_node_start
from src.utils.logging_config import log_event
from src.utils.prompt_templates import render_agent_prompt
from src.utils.retry import async_retry
from src.utils.token_counter import TokenCounter


logger = logging.getLogger(__name__)


class ParsedLogOutput(BaseModel):
    """Structured output from log parser agent."""
    
    error_signature: str = Field(
        description="Brief summary of the error (e.g., 'TypeError: NoneType object is not subscriptable')"
    )
    files_changed: list[str] = Field(
        default_factory=list,
        description="List of file paths that appear in the error traceback or stack trace"
    )
    language: str = Field(
        description="Programming language of the failing code (e.g., python, javascript, go, rust, java)"
    )
    root_cause_hint: Optional[str] = Field(
        default=None,
        description="Brief hint about the root cause if identifiable from the log"
    )


def fallback_parse_log(log_text: str) -> ParsedLogOutput:
    """
    Fallback parsing using regex when LLM parsing fails.
    
    Extracts error patterns from log text without LLM.
    
    Args:
        log_text: Log content to parse
        
    Returns:
        ParsedLogOutput with best-effort extraction
    """
    # Try to detect language from common patterns
    language = "unknown"
    if any(pattern in log_text for pattern in ["Traceback", "File", "ImportError", "ModuleNotFoundError"]):
        language = "python"
    elif any(pattern in log_text for pattern in ["TypeError", "ReferenceError", "SyntaxError", "at .*node_modules"]):
        language = "javascript"
    elif any(pattern in log_text for pattern in ["goroutine", "panic:", "runtime error"]):
        language = "go"
    elif any(pattern in log_text for pattern in ["thread", "panic", "error\\[E", "rustc"]):
        language = "rust"
    elif any(pattern in log_text for pattern in ["Exception", "Exception in thread", "at java."]):
        language = "java"
    
    # Extract error signature - look for common error patterns
    error_patterns = [
        r"^(?:Error|ERROR|FATAL):\s+(.+?)$",
        r"^(?:\w+Error):\s+(.+?)$",
        r"Traceback.*?(\w+Error):\s+(.+?)$",
        r"^FAIL:.+\n(.+?)$",
    ]
    
    error_signature = "Unknown error"
    for pattern in error_patterns:
        match = re.search(pattern, log_text, re.MULTILINE | re.IGNORECASE)
        if match:
            error_signature = match.group(1) if len(match.groups()) == 1 else match.group(2)
            break
    
    # Extract file paths
    files_changed = []
    file_pattern = r"(?:File|at|in)\s+['\"]?([/\w\.\-]+\.(?:py|js|go|rs|java|cpp|c|h))['\"]?"
    for match in re.finditer(file_pattern, log_text):
        file_path = match.group(1)
        if file_path not in files_changed:
            files_changed.append(file_path)
    
    return ParsedLogOutput(
        error_signature=error_signature,
        files_changed=files_changed[:5],  # Limit to 5 files
        language=language,
        root_cause_hint=None
    )


@async_retry(max_attempts=2, initial_delay=0.5, max_delay=5.0, backoff_factor=2.0)
async def call_log_parser_agent(
    log_text: str,
    model: ChatOpenAI,
    config: Any
) -> ParsedLogOutput:
    """
    Call log parser agent via LLM.
    
    Args:
        log_text: Truncated log text to parse
        model: ChatOpenAI model instance
        config: Configuration with prompts
        
    Returns:
        ParsedLogOutput from LLM
        
    Raises:
        json.JSONDecodeError: If LLM output is not valid JSON
        ValidationError: If output doesn't match schema
    """
    system_prompt = render_agent_prompt("log_parser", "system")
    user_prompt = render_agent_prompt(
        "log_parser", "parse_log",
        log_text=log_text[:4000]  # Include first 4000 chars in prompt
    )
    
    # Call LLM with structured output
    parser = model.with_structured_output(ParsedLogOutput)
    response = await parser.ainvoke(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    )
    
    return response


async def parse_log_node(state: FailBotState) -> dict[str, Any]:
    """
    Parse log node: Extract error signature, files, and language.
    
    Calls log parser agent to extract structured information from the CI log.
    Falls back to regex parsing if LLM fails.
    
    Args:
        state: FailBotState with log_text set from ingest node
        
    Returns:
        Updated state dict with:
        - error_signature: Brief error summary
        - files_changed: List of affected files
        - language: Detected programming language
        - parsed_summary: Full ParsedLogOutput
        - token_counts: Updated with parser tokens
        - status: Updated to 'parse_complete'
        - errors: Appended with any errors
    """
    start_time = log_node_start(
        logger, state["run_id"], "parse_log", state
    )
    
    try:
        config = get_config()
        
        # Check that log text is available
        if not state.get("log_text"):
            raise ValueError("Log text not available - ingest node may have failed")
        
        log_event(
            logger, state["run_id"], "parse_log",
            "parse_start", {"log_length": len(state["log_text"])}
        )
        
        # Initialize LLM
        model = ChatOpenAI(
            model=config.get_model("parser"),
            temperature=0.0,
            max_tokens=1000
        )
        
        # Try LLM parsing
        try:
            parsed_output = await call_log_parser_agent(state["log_text"], model, config)
            fallback_used = False
        except Exception as llm_error:
            logger.warning(f"LLM parsing failed, using fallback regex: {llm_error}")
            parsed_output = fallback_parse_log(state["log_text"])
            fallback_used = True
            
            if "errors" not in state or state["errors"] is None:
                state["errors"] = []
            state["errors"].append({
                "node": "parse_log",
                "error": f"LLM parsing failed: {str(llm_error)}",
                "type": "parse_fallback",
                "fallback_used": True
            })
        
        log_event(
            logger, state["run_id"], "parse_log",
            "parse_complete",
            {
                "error_signature": parsed_output.error_signature,
                "files_count": len(parsed_output.files_changed),
                "language": parsed_output.language,
                "fallback_used": fallback_used
            }
        )
        
        # Update state
        state["error_signature"] = parsed_output.error_signature
        state["files_changed"] = parsed_output.files_changed
        state["language"] = parsed_output.language
        state["parsed_summary"] = parsed_output.model_dump()
        
        # Track tokens (estimate)
        token_counter = TokenCounter("gpt-4o-mini")
        parser_tokens = token_counter.count_tokens(state["log_text"])
        
        if "token_counts" not in state or state["token_counts"] is None:
            state["token_counts"] = {}
        state["token_counts"]["parse_log_input"] = parser_tokens
        state["token_counts"]["parse_log_output"] = 500  # Estimate for structured output
        
        state["status"] = "parse_complete"
        
        log_node_end(logger, state["run_id"], "parse_log", state, start_time)
        
        return state
        
    except Exception as e:
        error_msg = f"Parse log node failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        if "errors" not in state or state["errors"] is None:
            state["errors"] = []
        state["errors"].append({
            "node": "parse_log",
            "error": str(e),
            "type": type(e).__name__
        })
        
        state["status"] = "parse_failed"
        handle_node_error(logger, state["run_id"], "parse_log", e, state)
        
        raise
