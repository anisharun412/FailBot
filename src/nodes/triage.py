"""Triage node: Classify failure category and severity."""

import logging
from typing import Any, Literal, Optional

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from src.config import get_config
from src.state import FailBotState
from src.tools.knowledge_base import lookup_known_errors
from src.utils.graph_utils import handle_node_error, log_node_end, log_node_start
from src.utils.logging_config import log_event
from src.utils.prompt_templates import render_agent_prompt
from src.utils.retry import async_retry
from src.utils.token_counter import TokenCounter


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
    model: ChatOpenAI,
    config: Any
) -> TriageOutput:
    """
    Call triage agent via LLM.
    
    Args:
        error_signature: Error message to triage
        error_context: Additional context (files, language, etc.)
        model: ChatOpenAI model instance
        config: Configuration with prompts
        
    Returns:
        TriageOutput from LLM
        
    Raises:
        Exception: If LLM call fails
    """
    system_prompt = render_agent_prompt("triage", "system")
    user_prompt = render_agent_prompt(
        "triage", "classify",
        error_signature=error_signature,
        error_context=error_context
    )
    
    # Call LLM with structured output
    parser = model.with_structured_output(TriageOutput)
    response = await parser.ainvoke(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    )
    
    return response


async def triage_node(state: FailBotState) -> dict[str, Any]:
    """
    Triage node: Classify failure into category and severity.
    
    Uses LLM to classify the failure, with heuristic fallback.
    Determines whether to suggest targeted test or generic test.
    
    Args:
        state: FailBotState with error_signature and parsed info
        
    Returns:
        Updated state dict with:
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
        if not state.get("error_signature"):
            raise ValueError("Error signature not available - parse_log node may have failed")
        
        log_event(
            logger, state["run_id"], "triage",
            "triage_start", {"error_signature": state["error_signature"][:100]}
        )
        
        # Build context for triage
        error_context = f"""
Language: {state.get('language', 'unknown')}
Files: {', '.join(state.get('files_changed', [])[:3])}
Log preview: {state.get('log_text', '')[:500]}
"""
        
        # Try to find similar known errors
        known_errors_matches = []
        try:
            known_errors_matches = await lookup_known_errors(
                state["error_signature"],
                top_k=3
            )
            if known_errors_matches:
                log_event(
                    logger, state["run_id"], "triage",
                    "kb_match",
                    {
                        "matches": len(known_errors_matches),
                        "top_match": known_errors_matches[0].get("category"),
                        "score": known_errors_matches[0].get("match_score")
                    }
                )
                # Append KB info to context for LLM
                error_context += f"\n\nKnown similar errors:\n"
                for match in known_errors_matches:
                    error_context += f"- {match.get('category')}: {match.get('description')[:60]}\n"
        except Exception as kb_error:
            logger.debug(f"Knowledge base lookup failed: {kb_error}")
        
        # Initialize LLM
        model = ChatOpenAI(
            model=config.get_model("triage"),
            temperature=0.0,
            max_tokens=500
        )
        
        # Try LLM triage
        try:
            triage_result = await call_triage_agent(
                state["error_signature"],
                error_context,
                model,
                config
            )
            heuristic_used = False
        except Exception as llm_error:
            logger.warning(f"LLM triage failed, using heuristics: {llm_error}")
            
            # Fallback to heuristics
            category, conf = apply_heuristics(
                state["error_signature"],
                state.get("language", "unknown"),
                state.get("files_changed", [])
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
            
            if "errors" not in state or state["errors"] is None:
                state["errors"] = []
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
        
        if "token_counts" not in state or state["token_counts"] is None:
            state["token_counts"] = {}
        state["token_counts"]["triage_input"] = triage_tokens
        state["token_counts"]["triage_output"] = 200  # Estimate
        
        state["status"] = "triage_complete"
        
        log_node_end(logger, state["run_id"], "triage", state, start_time)
        
        return state
        
    except Exception as e:
        error_msg = f"Triage node failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        if "errors" not in state or state["errors"] is None:
            state["errors"] = []
        state["errors"].append({
            "node": "triage",
            "error": str(e),
            "type": type(e).__name__
        })
        
        state["status"] = "triage_failed"
        handle_node_error(logger, state["run_id"], "triage", e, state)
        
        raise
