"""Triage node: Classify failure category and severity."""

import logging
from typing import Any, Literal, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel, Field

from src.config import get_config
from src.state import FailBotState
from src.tools.langchain_tools import get_bound_model
from src.utils.graph_utils import handle_node_error, log_node_end, log_node_start
from src.utils.json_extractor import extract_json_from_response
from src.utils.llm_factory import get_chat_model
from src.utils.logging_config import log_event
from src.utils.prompt_templates import render_agent_prompt
from src.utils.retry import async_retry
from src.utils.token_counter import TokenCounter
from src.utils.tool_runner import run_tool_calls


logger = logging.getLogger(__name__)


class TriageOutput(BaseModel):
    """Structured output from triage agent."""
    
    failure_category: Literal["code_bug", "flaky", "infra", "unknown"] = Field(
        description="Category of failure: code_bug (real bug in code), flaky (intermittent test), "
                    "infra (infrastructure/environment issue), unknown (unable to classify)"
    )
    severity: Literal["critical", "high", "medium", "low"] = Field(
        description="Severity level of the failure"
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence score for this classification (0.0 to 1.0)"
    )
    reasoning: str = Field(
        description="Brief explanation of the classification decision"
    )
    is_flaky_indicator: bool = Field(
        default=False,
        description="True if error suggests flakiness (timeouts, connection errors, etc.)"
    )
    is_infra_indicator: bool = Field(
        default=False,
        description="True if error suggests infrastructure issue (DNS, permission, etc.)"
    )


def apply_heuristics(
    error_signature: str,
    language: str,
    files_changed: list[str]
) -> tuple[Optional[Literal["code_bug", "flaky", "infra"]], float]:
    """
    Apply heuristic rules to classify failures without LLM.
    
    Useful for quick classification or as a fallback.
    
    Args:
        error_signature: Error message from parser
        language: Programming language
        files_changed: List of affected files
        
    Returns:
        Tuple of (category or None, confidence 0.0-1.0)
    """
    error_lower = error_signature.lower()
    
    # Flaky indicators
    flaky_keywords = [
        "timeout", "timed out", "deadline exceeded",
        "connection reset", "connection refused", "connection timeout",
        "resource temporarily unavailable", "address already in use",
        "temporary failure", "transient"
    ]
    if any(kw in error_lower for kw in flaky_keywords):
        return ("flaky", 0.85)
    
    # Infrastructure indicators
    infra_keywords = [
        "permission denied", "access denied", "no such file or directory",
        "not found", "dns", "domain name", "ssl", "certificate",
        "file not found", "directory not found", "cannot create", "cannot write"
    ]
    if any(kw in error_lower for kw in infra_keywords):
        return ("infra", 0.80)
    
    # Code bug indicators (e.g., type errors, attribute errors)
    code_keywords = [
        "typeerror", "attributeerror", "nameerror", "valueerror",
        "indexerror", "keyerror", "zerodivisionerror", "assertionerror",
        "notimplementederror", "runtimeerror"
    ]
    if any(kw in error_lower for kw in code_keywords):
        return ("code_bug", 0.90)
    
    return (None, 0.5)


@async_retry(max_attempts=2, initial_delay=0.5, max_delay=5.0, backoff_factor=2.0)
async def call_triage_agent(
    error_signature: str,
    error_context: str,
    model: BaseChatModel,
    config: Any
) -> TriageOutput:
    """
    Call triage agent via LLM.
    
    Args:
        error_signature: Error message to triage
        error_context: Additional context (files, language, etc.)
        model: Chat model instance
        config: Configuration with prompts
        
    Returns:
        TriageOutput from LLM
        
    Raises:
        Exception: If LLM call fails
    """
    import json
    
    system_prompt = render_agent_prompt("triage", "system")
    user_prompt = render_agent_prompt(
        "triage", "classify",
        error_signature=error_signature,
        error_context=error_context
    )
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    response = await model.ainvoke(messages)
    
    # Extract content - handle both string and list responses
    content: str | list[str | dict[str, Any]] = response.content
    if isinstance(content, list):
        # Handle tool calls or multiple content items
        for item in content:
            if isinstance(item, str):
                content = item
                break
        else:
            if isinstance(content, list) and content:
                content = str(content[0])
            else:
                raise ValueError("No parseable content in LLM response")
    
    if not isinstance(content, str):
        content = str(content)
    
    # Extract JSON from response (handles markdown code blocks and bare JSON)
    try:
        parsed_dict = extract_json_from_response(content)
        return TriageOutput.model_validate(parsed_dict)
    except (ValueError, json.JSONDecodeError) as e:
        logger.warning(f"JSON extraction failed: {e}")
        raise


async def triage_node(state: FailBotState) -> FailBotState:
    """
    Triage node: Classify failure into category and severity.
    
    Uses LLM to classify the failure, with heuristic fallback.
    Determines whether to suggest targeted test or generic test.
    
    Args:
        state: FailBotState with error_signature and parsed info
        
    Returns:
        Updated FailBotState with:
        - failure_category: One of code_bug, flaky, infra, unknown
        - severity: One of critical, high, medium, low
        - triage_confidence: Confidence score for classification
        - status: Updated to 'triage_complete'
        - errors: Appended with any errors
    """
    start_time = log_node_start(
        logger, state["run_id"], "triage", state
    )
    
    try:
        config = get_config()
        
        # Check that error_signature is available
        error_sig: Optional[str] = state.get("error_signature")
        if not error_sig:
            raise ValueError("Error signature not available - parse_log node may have failed")
        
        log_event(
            logger, state["run_id"], "triage",
            "triage_start", {"error_signature": error_sig[:100]}
        )
        
        # Build context for triage - safely handle None values
        lang: str = state.get('language') or 'unknown'
        files_changed: list[str] = state.get('files_changed') or []
        log_text: str = state.get('log_text') or ''
        
        files_str = ', '.join(files_changed[:3]) if files_changed else "unknown"
        log_preview = log_text[:500] if log_text else "no log text"
        
        error_context = f"""
Language: {lang}
Files: {files_str}
Log preview: {log_preview}
"""
        
        # Initialize LLM with JSON Object Mode (per official Groq/OpenAI docs)
        model = get_chat_model(
            role="triage",
            temperature=0.0,
            max_tokens=1000,
            json_object_mode=True,
        )
        
        # Try LLM triage
        try:
            triage_result = await call_triage_agent(
                error_sig,
                error_context,
                model,
                config
            )
            heuristic_used = False
        except Exception as llm_error:
            logger.warning(f"LLM triage failed, using heuristics: {llm_error}")
            
            # Fallback to heuristics
            category, conf = apply_heuristics(
                error_sig,
                lang,
                files_changed
            )
            
            triage_result = TriageOutput(
                failure_category=category or "unknown",
                severity="medium",
                confidence=conf,
                reasoning="Using heuristic fallback (LLM failed)",
                is_flaky_indicator=category == "flaky",
                is_infra_indicator=category == "infra"
            )
            heuristic_used = True
            
            state["errors"].append({
                "node": "triage",
                "error": f"LLM triage failed: {str(llm_error)}",
                "type": "triage_fallback",
                "heuristic_used": True
            })
        
        log_event(
            logger, state["run_id"], "triage",
            "triage_complete",
            {
                "category": triage_result.failure_category,
                "severity": triage_result.severity,
                "confidence": triage_result.confidence,
                "heuristic_used": heuristic_used
            }
        )
        
        # Update state
        state["failure_category"] = triage_result.failure_category
        state["severity"] = triage_result.severity
        state["triage_confidence"] = triage_result.confidence
        state["triage_reasoning"] = triage_result.reasoning
        
        # Track tokens (estimate)
        token_counter = TokenCounter("gpt-4o-mini")
        triage_tokens = token_counter.count_tokens(error_context)
        
        state["token_counts"]["triage_input"] = triage_tokens
        state["token_counts"]["triage_output"] = 200  # Estimate
        
        state["status"] = "triage_complete"
        
        log_node_end(logger, state["run_id"], "triage", state, start_time)
        
        return state
        
    except Exception as e:
        error_msg = f"Triage node failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        state["errors"].append({
            "node": "triage",
            "error": str(e),
            "type": type(e).__name__
        })
        
        state["status"] = "triage_failed"
        handle_node_error(logger, state["run_id"], "triage", e, state)
        
        raise
