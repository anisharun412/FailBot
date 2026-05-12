"""Parse log node: Extract error signature and context."""

import json
import logging
import re
import time
from typing import Any, Optional

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel, Field, ValidationError

from src.config import get_config
from src.state import FailBotState
from src.utils.graph_utils import handle_node_error, log_node_end, log_node_start
from src.utils.json_extractor import extract_json_from_response
from src.utils.llm_factory import get_chat_model
from src.utils.logging_config import log_event
from src.utils.prompt_templates import render_agent_prompt
from src.utils.response_utils import extract_token_usage
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
    language: Optional[str] = Field(
        default=None,
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
        r"^E\s+(.+?)$",
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
    files_changed: list[str] = []
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
    model: BaseChatModel,
    config: Any
) -> tuple[ParsedLogOutput, Optional[int]]:
    """
    Call log parser agent via LLM.
    
    Args:
        log_text: Truncated log text to parse
        model: Chat model instance
        config: Configuration with prompts
        
    Returns:
        Tuple of (ParsedLogOutput, total_tokens_used)
        
    Raises:
        json.JSONDecodeError: If LLM output is not valid JSON
        ValidationError: If output doesn't match schema
    """
    system_prompt: str = render_agent_prompt("log_parser", "system")
    user_prompt: str = render_agent_prompt(
        "log_parser", "parse_log",
        log_text=log_text[:4000]  # Include first 4000 chars in prompt
    )
    
    # Call LLM and parse response as JSON
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt)
    ]
    response = await model.ainvoke(messages)
    
    # Extract actual token usage from response
    total_tokens = extract_token_usage(response)
    
    # Extract and parse JSON from response content
    content: str | list[str | dict[str, Any]] = response.content
    if isinstance(content, list):
        # Handle tool calls in response
        for item in content:
            if isinstance(item, str):
                content = item
                break
        else:
            # No string content found, use first dict or raise error
            if isinstance(content, list) and content:
                content = str(content[0])
            else:
                raise ValueError("No parseable content in LLM response")
    
    if not isinstance(content, str):
        content = str(content)
    
    # Extract JSON from response (handles markdown code blocks and bare JSON)
    try:
        parsed_dict = extract_json_from_response(content)
        return ParsedLogOutput.model_validate(parsed_dict), total_tokens
    except (ValueError, json.JSONDecodeError) as e:
        logger.warning(f"JSON extraction failed: {e}")
        raise


async def parse_log_node(state: FailBotState) -> FailBotState:
    """
    Parse log node: Extract error signature, files, and language.
    
    Calls log parser agent to extract structured information from the CI log.
    Falls back to regex parsing if LLM fails.
    
    Args:
        state: FailBotState with log_text set from ingest node
        
    Returns:
        Updated FailBotState with:
        - error_signature: Brief error summary
        - files_changed: List of affected files
        - language: Detected programming language
        - parsed_summary: Full ParsedLogOutput
        - token_counts: Updated with real parser tokens
        - node_durations_ms: Updated with execution time
        - agent_fallback_used: Set if regex fallback used
        - status: Updated to 'parse_complete'
        - errors: Appended with any errors
    """
    start_time = log_node_start(
        logger, state["run_id"], "parse_log", state
    )
    node_start_time = time.perf_counter()
    
    try:
        config = get_config()
        
        # Check that log text is available
        log_text: Optional[str] = state.get("log_text")
        if not log_text:
            raise ValueError("Log text not available - ingest node may have failed")
        
        log_event(
            logger, state["run_id"], "parse_log",
            "parse_start", {"log_length": len(log_text)}
        )
        
        # Initialize LLM with JSON Object Mode (per official Groq/OpenAI docs)
        model = get_chat_model(
            role="parser",
            temperature=0.0,
            max_tokens=1500,
            json_object_mode=True,
        )

        # Try LLM parsing
        parsed_output: ParsedLogOutput
        agent_fallback_used: bool = False
        total_tokens: Optional[int] = None
        
        try:
            parsed_output, total_tokens = await call_log_parser_agent(log_text, model, config)
            agent_fallback_used = False
        except Exception as llm_error:
            logger.warning(
                f"LLM parsing failed, using fallback regex: {llm_error}"
            )
            parsed_output = fallback_parse_log(log_text)
            agent_fallback_used = True

            state["errors"].append({
                "node": "parse_log",
                "error": f"LLM parsing failed: {str(llm_error)}",
                "type": "agent_fallback",
                "agent_fallback_used": True
            })
        
        if not parsed_output.error_signature or not parsed_output.error_signature.strip():
            logger.warning("LLM returned empty error_signature; using fallback extractor")
            fallback_output = fallback_parse_log(log_text)
            parsed_output = ParsedLogOutput(
                error_signature=fallback_output.error_signature or "Unknown error",
                files_changed=parsed_output.files_changed or fallback_output.files_changed,
                language=parsed_output.language or fallback_output.language,
                root_cause_hint=parsed_output.root_cause_hint,
            )
            agent_fallback_used = True

            state["errors"].append({
                "node": "parse_log",
                "error": "LLM returned empty error_signature; used fallback extractor",
                "type": "agent_fallback",
                "agent_fallback_used": True
            })

        log_event(
            logger, state["run_id"], "parse_log",
            "parse_complete",
            {
                "error_signature": parsed_output.error_signature[:80],
                "files_count": len(parsed_output.files_changed),
                "language": parsed_output.language,
                "agent_fallback_used": agent_fallback_used,
                "tokens": total_tokens
            }
        )
        
        # Update state
        state["error_signature"] = parsed_output.error_signature
        state["files_changed"] = parsed_output.files_changed
        state["language"] = parsed_output.language or "unknown"
        state["parsed_summary"] = parsed_output.model_dump_json()
        state["agent_fallback_used"] = agent_fallback_used
        
        # Track actual tokens or estimate as fallback
        if total_tokens:
            state["token_counts"]["parse_log"] = total_tokens
        else:
            # Fallback to estimation
            token_counter = TokenCounter("gpt-4o-mini")
            estimated_tokens = token_counter.count_tokens(log_text)
            state["token_counts"]["parse_log"] = estimated_tokens
        
        # Track execution time
        node_duration_ms = (time.perf_counter() - node_start_time) * 1000
        state["node_durations_ms"]["parse_log"] = node_duration_ms
        
        state["status"] = "parse_complete"
        
        log_node_end(logger, state["run_id"], "parse_log", state, start_time)
        
        return state
        
    except Exception as e:
        error_msg = f"Parse log node failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        state["errors"].append({
            "node": "parse_log",
            "error": str(e),
            "type": type(e).__name__
        })
        
        # Track execution time even on error
        node_duration_ms = (time.perf_counter() - node_start_time) * 1000
        state["node_durations_ms"]["parse_log"] = node_duration_ms
        
        state["status"] = "parse_failed"
        handle_node_error(logger, state["run_id"], "parse_log", e, state)
        
        raise
