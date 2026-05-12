"""Suggest test generic node: Generate test strategies for non-bug failures."""

import json
import logging
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel, Field, ValidationError

from src.config import get_config
from src.state import FailBotState
from src.tools.langchain_tools import get_bound_model
from src.utils.graph_utils import handle_node_error, log_node_end, log_node_start
from src.utils.llm_factory import get_chat_model
from src.utils.logging_config import log_event
from src.utils.prompt_templates import render_agent_prompt
from src.utils.retry import async_retry
from src.utils.token_counter import TokenCounter
from src.utils.tool_runner import run_tool_calls
from src.utils.json_extractor import extract_json_from_response


logger = logging.getLogger(__name__)


class TestStrategyOutput(BaseModel):
    """Structured output for test strategy."""
    
    test_strategy: str = Field(
        description="Description of the test strategy or approach (not code, but a plan)"
    )
    strategy_type: str = Field(
        description="Type of strategy: resilience_test, flakiness_test, infrastructure_test, etc."
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence that this strategy would help validate the fix"
    )
    expected_outcomes: list[str] = Field(
        default_factory=list,
        description="What passing this test/strategy would demonstrate"
    )


@async_retry(max_attempts=2, initial_delay=0.5, max_delay=5.0, backoff_factor=2.0)
async def call_test_strategy_agent(
    error_signature: str,
    failure_category: str,
    error_context: str,
    model: BaseChatModel,
    config: Any
) -> TestStrategyOutput:
    """
    Call test strategy agent via LLM with tool binding.
    
    The model can call tools like lookup_error_patterns to find similar issues
    and build better strategies.
    
    Args:
        error_signature: Error to generate strategy for
        failure_category: flaky, infra, or unknown
        error_context: Additional context
        model: Chat model instance for tool calling
        config: Configuration with prompts
        
    Returns:
        TestStrategyOutput from LLM
        
    Raises:
        Exception: If LLM call fails
    """
    bound_model = get_bound_model(model)
    system_prompt: str = render_agent_prompt(
        "test_suggester_generic", "system",
        failure_category=failure_category
    )
    user_prompt: str = render_agent_prompt(
        "test_suggester_generic", "suggest_test_generic",
        error_signature=error_signature,
        failure_category=failure_category,
        error_context=error_context
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    # Call LLM with tool binding
    response = await bound_model.ainvoke(messages)
    
    # Execute any tool calls
    tool_messages = await run_tool_calls(response)
    
    # If tool calls were made, continue the conversation
    if tool_messages:
        messages = messages + [response] + tool_messages
        response = await model.ainvoke(messages)
    
    # Extract JSON from response content using utility function
    content: str | list[str | dict[str, Any]] = response.content
    if isinstance(content, list):
        for item in content:
            if isinstance(item, str):
                content = item
                break
        else:
            if isinstance(content, list) and content:
                content = str(content[0])
            else:
                raise ValueError("No parseable content in response")
    
    if not isinstance(content, str):
        content = str(content)
    
    # Use the standard JSON extraction utility
    try:
        parsed_dict = extract_json_from_response(content)
        return TestStrategyOutput.model_validate(parsed_dict)
    except (ValueError, json.JSONDecodeError, ValidationError) as e:
        logger.warning(f"Failed to extract and parse JSON: {e}")
        raise


async def suggest_test_generic_node(state: FailBotState) -> FailBotState:
    """
    Suggest test generic node: Generate test strategies for non-code-bug failures.
    
    For flaky and infrastructure failures, generates testing strategies rather than
    specific test code. Helps identify root causes and validate fixes.
    
    Args:
        state: FailBotState with error info and failure_category
        
    Returns:
        Updated FailBotState with:
        - suggested_test: Test strategy description (not code)
        - test_language: Set to 'strategy'
        - test_confidence: Confidence score for the strategy
        - test_description: Description of strategy type
        - status: Updated to 'suggest_test_generic_complete'
        - errors: Appended with any errors
    """
    start_time = log_node_start(
        logger, state["run_id"], "suggest_test_generic", state
    )
    
    try:
        config = get_config()
        
        # Check prerequisites
        error_sig: Optional[str] = state.get("error_signature")
        if not error_sig:
            raise ValueError("Error signature not available")
        
        failure_cat: Optional[str] = state.get("failure_category")
        if not failure_cat:
            raise ValueError("Failure category not available")
        
        log_event(
            logger, state["run_id"], "suggest_test_generic",
            "strategy_generation_start",
            {
                "category": failure_cat,
                "error_sig": error_sig[:80]
            }
        )
        
        # Build context - safely handle None values
        files_changed: Optional[list[str]] = state.get('files_changed')
        log_text: Optional[str] = state.get('log_text')
        files_str = ', '.join(files_changed[:3]) if files_changed else "unknown"
        log_preview = (log_text[:300] if log_text else "no log text")
        severity = state.get('severity') or 'unknown'
        
        error_context = f"""
Error signature: {error_sig}
Files affected: {files_str}
Log preview: {log_preview}
Severity: {severity}
"""
        
        # Initialize LLM with tool calling (no JSON mode - they cannot be combined)
        model = get_chat_model(
            role="test_suggester",
            temperature=0.3,
            max_tokens=1000,
        )
        
        # Generate strategy
        strategy_result: TestStrategyOutput
        generation_success: bool
        try:
            strategy_result = await call_test_strategy_agent(
                error_sig,
                failure_cat,
                error_context,
                model,
                config
            )
            generation_success = True
        except Exception as llm_error:
            logger.error(f"Strategy generation failed: {llm_error}")
            
            state["errors"].append({
                "node": "suggest_test_generic",
                "error": f"Strategy generation failed: {str(llm_error)}",
                "type": "generation_error"
            })
            
            # Provide default strategy based on category
            strategy: str
            strategy_type: str
            if failure_cat == "flaky":
                strategy = (
                    "Run the test multiple times (50-100 iterations) in sequence. "
                    "If it consistently fails or passes, the test may not be flaky. "
                    "If failures are sporadic, investigate timing, concurrency, or resource issues."
                )
                strategy_type = "flakiness_test"
            elif failure_cat == "infra":
                strategy = (
                    "Check infrastructure assumptions: verify network connectivity, "
                    "file system permissions, DNS resolution, environment variables, "
                    "and resource availability (disk space, memory). Test in different environments."
                )
                strategy_type = "infrastructure_test"
            else:
                strategy = (
                    "Investigate the failure conditions: review logs, "
                    "examine state changes, check for race conditions or resource exhaustion."
                )
                strategy_type = "root_cause_analysis"
            
            strategy_result = TestStrategyOutput(
                test_strategy=strategy,
                strategy_type=strategy_type,
                confidence=0.5,
                expected_outcomes=[]
            )
            generation_success = False
        
        log_event(
            logger, state["run_id"], "suggest_test_generic",
            "strategy_generation_complete",
            {
                "type": strategy_result.strategy_type,
                "success": generation_success,
                "confidence": strategy_result.confidence
            }
        )
        
        # Update state
        state["suggested_test"] = strategy_result.test_strategy
        state["test_language"] = "strategy"
        state["test_confidence"] = strategy_result.confidence
        state["test_description"] = f"Strategy ({strategy_result.strategy_type})"
        
        # Track tokens
        token_counter = TokenCounter("gpt-4o-mini")
        strategy_tokens: int = token_counter.count_tokens(strategy_result.test_strategy)
        input_tokens: int = token_counter.count_tokens(error_context)
        
        state["token_counts"]["suggest_test_generic_input"] = input_tokens
        state["token_counts"]["suggest_test_generic_output"] = strategy_tokens
        
        state["status"] = "suggest_test_generic_complete"
        
        log_node_end(logger, state["run_id"], "suggest_test_generic", state, start_time)
        
        return state
        
    except Exception as e:
        error_msg = f"Suggest test generic node failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        state["errors"].append({
            "node": "suggest_test_generic",
            "error": str(e),
            "type": type(e).__name__
        })
        
        state["status"] = "suggest_test_generic_failed"
        handle_node_error(logger, state["run_id"], "suggest_test_generic", e, state)
        
        raise
    """
    Suggest test generic node: Generate test strategies for non-code-bug failures.
    
    For flaky and infrastructure failures, generates testing strategies rather than
    specific test code. Helps identify root causes and validate fixes.
    
    Args:
        state: FailBotState with error info and failure_category
        
    Returns:
        Updated state dict with:
        - suggested_test: Test strategy description (not code)
        - test_language: Set to 'strategy'
        - status: Updated to 'suggest_test_generic_complete'
        - errors: Appended with any errors
    """
    start_time = log_node_start(
        logger, state["run_id"], "suggest_test_generic", state
    )
    
    try:
        config = get_config()
        
        # Check prerequisites
        if not state.get("error_signature"):
            raise ValueError("Error signature not available")
        
        if not state.get("failure_category"):
            raise ValueError("Failure category not available")
        
        log_event(
            logger, state["run_id"], "suggest_test_generic",
            "strategy_generation_start",
            {
                "category": state["failure_category"],
                "error_sig": state["error_signature"][:80]
            }
        )
        
        # Build context
        error_context = f"""
Error signature: {state.get('error_signature')}
Files affected: {', '.join(state.get('files_changed', [])[:3])}
Log preview: {state.get('log_text', '')[:300]}
Severity: {state.get('severity', 'unknown')}
"""
        
        # Initialize LLM (tool calling with knowledge base - no JSON mode)
        model = get_chat_model(
            role="test_suggester",
            temperature=0.3,
            max_tokens=1000,
        )
        
        # Generate strategy
        try:
            strategy_result = await call_test_strategy_agent(
                state["error_signature"],
                state["failure_category"],
                error_context,
                model,
                config
            )
            generation_success = True
        except Exception as llm_error:
            logger.error(f"Strategy generation failed: {llm_error}")
            
            if "errors" not in state or state["errors"] is None:
                state["errors"] = []
            state["errors"].append({
                "node": "suggest_test_generic",
                "error": f"Strategy generation failed: {str(llm_error)}",
                "type": "generation_error"
            })
            
            # Provide default strategy based on category
            if state["failure_category"] == "flaky":
                strategy = (
                    "Run the test multiple times (50-100 iterations) in sequence. "
                    "If it consistently fails or passes, the test may not be flaky. "
                    "If failures are sporadic, investigate timing, concurrency, or resource issues."
                )
                strategy_type = "flakiness_test"
            elif state["failure_category"] == "infra":
                strategy = (
                    "Check infrastructure assumptions: verify network connectivity, "
                    "file system permissions, DNS resolution, environment variables, "
                    "and resource availability (disk space, memory). Test in different environments."
                )
                strategy_type = "infrastructure_test"
            else:
                strategy = (
                    "Investigate the failure conditions: review logs, "
                    "examine state changes, check for race conditions or resource exhaustion."
                )
                strategy_type = "root_cause_analysis"
            
            strategy_result = TestStrategyOutput(
                test_strategy=strategy,
                strategy_type=strategy_type,
                confidence=0.5,
                expected_outcomes=[]
            )
            generation_success = False
        
        log_event(
            logger, state["run_id"], "suggest_test_generic",
            "strategy_generation_complete",
            {
                "type": strategy_result.strategy_type,
                "success": generation_success,
                "confidence": strategy_result.confidence
            }
        )
        
        # Update state
        state["suggested_test"] = strategy_result.test_strategy
        state["test_language"] = "strategy"
        state["test_confidence"] = strategy_result.confidence
        state["test_description"] = f"Strategy ({strategy_result.strategy_type})"
        
        # Track tokens
        token_counter = TokenCounter("gpt-4o-mini")
        strategy_tokens = token_counter.count_tokens(strategy_result.test_strategy)
        
        if "token_counts" not in state or state["token_counts"] is None:
            state["token_counts"] = {}
        state["token_counts"]["suggest_test_generic_input"] = token_counter.count_tokens(error_context)
        state["token_counts"]["suggest_test_generic_output"] = strategy_tokens
        
        state["status"] = "suggest_test_generic_complete"
        
        log_node_end(logger, state["run_id"], "suggest_test_generic", state, start_time)
        
        return state
        
    except Exception as e:
        error_msg = f"Suggest test generic node failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        if "errors" not in state or state["errors"] is None:
            state["errors"] = []
        state["errors"].append({
            "node": "suggest_test_generic",
            "error": str(e),
            "type": type(e).__name__
        })
        
        state["status"] = "suggest_test_generic_failed"
        handle_node_error(logger, state["run_id"], "suggest_test_generic", e, state)
        
        raise
