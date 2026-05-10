"""Suggest test node: Generate regression tests for code bugs."""

import logging
from typing import Any, Optional

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from src.config import get_config
from src.state import FailBotState
from src.tools.code_validator import CodeValidator, validate_code
from src.utils.graph_utils import handle_node_error, log_node_end, log_node_start
from src.utils.logging_config import log_event
from src.utils.prompt_templates import render_agent_prompt
from src.utils.retry import async_retry
from src.utils.token_counter import TokenCounter


logger = logging.getLogger(__name__)


class TestSuggesterOutput(BaseModel):
    """Structured output from test suggester agent."""
    
    test_code: str = Field(
        description="The generated test code"
    )
    test_description: str = Field(
        description="Brief description of what the test checks"
    )
    language: str = Field(
        description="Programming language of the test"
    )
    imports_needed: list[str] = Field(
        default_factory=list,
        description="List of imports/dependencies needed for the test"
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence that this test would catch the bug"
    )


@async_retry(max_attempts=2, initial_delay=0.5, max_delay=5.0, backoff_factor=2.0)
async def call_test_suggester_agent(
    error_signature: str,
    language: str,
    error_context: str,
    model: ChatOpenAI,
    config: Any
) -> TestSuggesterOutput:
    """
    Call test suggester agent via LLM.
    
    Args:
        error_signature: Error to generate test for
        language: Programming language for the test
        error_context: Additional context
        model: ChatOpenAI model instance
        config: Configuration with prompts
        
    Returns:
        TestSuggesterOutput from LLM
        
    Raises:
        Exception: If LLM call fails
    """
    system_prompt = render_agent_prompt(
        "test_suggester", "system",
        language=language
    )
    user_prompt = render_agent_prompt(
        "test_suggester", "suggest_test",
        error_signature=error_signature,
        language=language,
        error_context=error_context
    )
    
    # Call LLM with structured output
    parser = model.with_structured_output(TestSuggesterOutput)
    response = await parser.ainvoke(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    )
    
    return response


async def suggest_test_node(state: FailBotState) -> dict[str, Any]:
    """
    Suggest test node: Generate regression test for code bugs.
    
    Generates a targeted regression test that would catch the failure.
    Validates syntax and checks for hallucinations.
    
    Args:
        state: FailBotState with error_signature, language, files_changed
        
    Returns:
        Updated state dict with:
        - suggested_test: Generated test code
        - test_language: Language of the test
        - test_validation_errors: Any validation issues found
        - token_counts: Updated with test suggester tokens
        - status: Updated to 'suggest_test_complete'
        - errors: Appended with any errors
    """
    start_time = log_node_start(
        logger, state["run_id"], "suggest_test", state
    )
    
    try:
        config = get_config()
        
        # Check prerequisites
        if not state.get("error_signature"):
            raise ValueError("Error signature not available")
        
        if not state.get("language"):
            logger.warning("Language not detected, defaulting to 'unknown'")
            state["language"] = "unknown"
        
        log_event(
            logger, state["run_id"], "suggest_test",
            "test_generation_start",
            {"language": state["language"], "error_sig": state["error_signature"][:80]}
        )
        
        # Build context
        error_context = f"""
Error signature: {state.get('error_signature')}
Files affected: {', '.join(state.get('files_changed', [])[:3])}
Log preview: {state.get('log_text', '')[:300]}
"""
        
        # Initialize LLM
        model = ChatOpenAI(
            model=config.get_model("test_suggester"),
            temperature=0.3,
            max_tokens=1500
        )
        
        # Generate test
        try:
            test_result = await call_test_suggester_agent(
                state["error_signature"],
                state["language"],
                error_context,
                model,
                config
            )
            generation_success = True
        except Exception as llm_error:
            logger.error(f"Test generation failed: {llm_error}")
            
            if "errors" not in state or state["errors"] is None:
                state["errors"] = []
            state["errors"].append({
                "node": "suggest_test",
                "error": f"Test generation failed: {str(llm_error)}",
                "type": "generation_error"
            })
            
            # Still continue with empty test
            test_result = TestSuggesterOutput(
                test_code="# Test generation failed\n# Please review log manually",
                test_description="Test generation failed - manual review needed",
                language=state["language"],
                imports_needed=[],
                confidence=0.0
            )
            generation_success = False
        
        # Validate code and detect hallucinations
        validation_result = CodeValidator.validate_and_score(
            test_result.test_code,
            language=test_result.language
        )
        
        validation_errors = []
        if validation_result["syntax_error"]:
            validation_errors.append(f"Syntax error: {validation_result['syntax_error']}")
        validation_errors.extend(validation_result["hallucinations"])
        validation_errors.extend(validation_result["warnings"])
        
        # Adjust confidence based on validation issues
        test_confidence = test_result.confidence * (1.0 - validation_result["confidence_penalty"])
        
        log_event(
            logger, state["run_id"], "suggest_test",
            "test_generation_complete",
            {
                "language": test_result.language,
                "success": generation_success,
                "valid": validation_result["is_valid"],
                "validation_errors": len(validation_errors),
                "confidence": test_confidence
            }
        )
        
        # Update state
        state["suggested_test"] = test_result.test_code
        state["test_language"] = test_result.language
        state["test_confidence"] = test_confidence
        state["test_validation_errors"] = validation_errors
        state["test_description"] = test_result.test_description
        
        # Track tokens
        token_counter = TokenCounter("gpt-4o-mini")
        test_tokens = token_counter.count_tokens(test_result.test_code)
        
        if "token_counts" not in state or state["token_counts"] is None:
            state["token_counts"] = {}
        state["token_counts"]["suggest_test_input"] = token_counter.count_tokens(error_context)
        state["token_counts"]["suggest_test_output"] = test_tokens
        
        state["status"] = "suggest_test_complete"
        
        log_node_end(logger, state["run_id"], "suggest_test", state, start_time)
        
        return state
        
    except Exception as e:
        error_msg = f"Suggest test node failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        if "errors" not in state or state["errors"] is None:
            state["errors"] = []
        state["errors"].append({
            "node": "suggest_test",
            "error": str(e),
            "type": type(e).__name__
        })
        
        state["status"] = "suggest_test_failed"
        handle_node_error(logger, state["run_id"], "suggest_test", e, state)
        
        raise
