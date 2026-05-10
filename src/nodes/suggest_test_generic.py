"""Suggest test generic node: Generate test strategies for non-bug failures."""

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from src.config import get_config
from src.state import FailBotState
from src.tools.langchain_tools import get_bound_model
from src.utils.graph_utils import handle_node_error, log_node_end, log_node_start
from src.utils.logging_config import log_event
from src.utils.prompt_templates import render_agent_prompt
from src.utils.retry import async_retry
from src.utils.token_counter import TokenCounter
from src.utils.tool_runner import run_tool_calls


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
    model: ChatOpenAI,
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
        model: ChatOpenAI model instance
        config: Configuration with prompts
        
    Returns:
        TestStrategyOutput from LLM
        
    Raises:
        Exception: If LLM call fails
    """
    bound_model = get_bound_model(model)
    system_prompt = render_agent_prompt(
        "test_suggester_generic", "system",
        failure_category=failure_category
    )
    user_prompt = render_agent_prompt(
        "test_suggester_generic", "suggest_test_generic",
        error_signature=error_signature,
        failure_category=failure_category,
        error_context=error_context
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    first_response = await bound_model.ainvoke(messages)
    tool_messages = await run_tool_calls(first_response)

    if tool_messages:
        tool_aware_messages = messages + [first_response] + tool_messages
        parser = bound_model.with_structured_output(TestStrategyOutput)
        return await parser.ainvoke(tool_aware_messages)

    try:
        return TestStrategyOutput.model_validate_json(first_response.content)
    except Exception:
        parser = bound_model.with_structured_output(TestStrategyOutput)
        return await parser.ainvoke(messages)


async def suggest_test_generic_node(state: FailBotState) -> dict[str, Any]:
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
        
        # Initialize LLM
        model = ChatOpenAI(
            model=config.get_model("test_suggester"),
            temperature=0.3,
            max_tokens=1000
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
