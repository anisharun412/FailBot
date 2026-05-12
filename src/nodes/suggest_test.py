"""Suggest test node: Generate regression tests for code bugs."""

import json
import logging
from typing import Any, Optional

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel, Field, ValidationError

from src.config import get_config
from src.state import FailBotState
from src.tools.code_validator import CodeValidator, validate_code
from src.utils.graph_utils import handle_node_error, log_node_end, log_node_start
from src.utils.json_extractor import extract_json_from_response
from src.utils.llm_factory import get_chat_model
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
    model: BaseChatModel,
    config: Any
) -> TestSuggesterOutput:
    """
    Call test suggester agent via LLM.
    
    Args:
        error_signature: Error to generate test for
        language: Programming language for the test
        error_context: Additional context
        model: Chat model instance
        config: Configuration with prompts
        
    Returns:
        TestSuggesterOutput from LLM
        
    Raises:
        Exception: If LLM call fails
    """
    system_prompt: str = render_agent_prompt(
        "test_suggester", "system",
        language=language
    )
    user_prompt: str = render_agent_prompt(
        "test_suggester", "suggest_test",
        error_signature=error_signature,
        language=language,
        error_context=error_context
    )
    
    # Call LLM and parse JSON response
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt)
    ]
    response = await model.ainvoke(messages)
    
    # Extract and parse JSON from response content
    content: str | list[str | dict[str, Any]] = response.content
    if isinstance(content, list):
        # Handle tool calls in response
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
        return TestSuggesterOutput.model_validate(parsed_dict)
    except (ValueError, json.JSONDecodeError) as e:
        logger.warning(f"JSON extraction failed: {e}")
        raise


async def suggest_test_node(state: FailBotState) -> FailBotState:
    """
    Suggest test node: Generate regression test for code bugs.
    
    Generates a targeted regression test that would catch the failure.
    Validates syntax and checks for hallucinations.
    
    Args:
        state: FailBotState with error_signature, language, files_changed
        
    Returns:
        Updated FailBotState with:
        - suggested_test: Generated test code
        - test_language: Language of the test
        - test_validation_errors: Any validation issues found
        - test_confidence: Confidence score for the test
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
        error_sig: Optional[str] = state.get("error_signature")
        if not error_sig:
            raise ValueError("Error signature not available")
        
        lang: Optional[str] = state.get("language")
        if not lang:
            logger.warning("Language not detected, defaulting to 'unknown'")
            lang = "unknown"
        
        log_event(
            logger, state["run_id"], "suggest_test",
            "test_generation_start",
            {"language": lang, "error_sig": error_sig[:80]}
        )
        
        # Build context - safely handle None values
        files_changed: Optional[list[str]] = state.get('files_changed')
        log_text: Optional[str] = state.get('log_text')
        files_str = ', '.join(files_changed[:3]) if files_changed else "unknown"
        log_preview = (log_text[:300] if log_text else "no log text")
        
        error_context = f"""
Error signature: {error_sig}
Files affected: {files_str}
Log preview: {log_preview}
"""
        
        # Initialize LLM with JSON Object Mode (per official Groq/OpenAI docs)
        model = get_chat_model(
            role="test_suggester",
            temperature=0.3,
            max_tokens=2000,
            json_object_mode=True,
        )
        
        # Generate test
        test_result: TestSuggesterOutput
        generation_success: bool
        try:
            test_result = await call_test_suggester_agent(
                error_sig,
                lang,
                error_context,
                model,
                config
            )
            generation_success = True
        except Exception as llm_error:
            logger.error(f"Test generation failed: {llm_error}")
            
            state["errors"].append({
                "node": "suggest_test",
                "error": f"Test generation failed: {str(llm_error)}",
                "type": "generation_error"
            })
            
            # Still continue with empty test
            test_result = TestSuggesterOutput(
                test_code="# Test generation failed\n# Please review log manually",
                test_description="Test generation failed - manual review needed",
                language=lang,
                imports_needed=[],
                confidence=0.0
            )
            generation_success = False
        
        # Validate code and detect hallucinations
        validation_result: dict[str, Any] = CodeValidator.validate_and_score(
            test_result.test_code,
            language=test_result.language
        )
        
        validation_errors: list[str] = []
        syntax_error: Optional[str] = validation_result.get("syntax_error")
        if syntax_error:
            validation_errors.append(f"Syntax error: {syntax_error}")
        
        hallucinations: list[str] = validation_result.get("hallucinations", [])
        validation_errors.extend(hallucinations)
        
        warnings: list[str] = validation_result.get("warnings", [])
        validation_errors.extend(warnings)
        
        # Adjust confidence based on validation issues
        confidence_penalty: float = validation_result.get("confidence_penalty", 0.0)
        test_confidence: float = test_result.confidence * (1.0 - confidence_penalty)
        
        log_event(
            logger, state["run_id"], "suggest_test",
            "test_generation_complete",
            {
                "language": test_result.language,
                "success": generation_success,
                "valid": validation_result.get("is_valid", False),
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
        test_tokens: int = token_counter.count_tokens(test_result.test_code)
        input_tokens: int = token_counter.count_tokens(error_context)
        
        state["token_counts"]["suggest_test_input"] = input_tokens
        state["token_counts"]["suggest_test_output"] = test_tokens
        
        state["status"] = "suggest_test_complete"
        
        log_node_end(logger, state["run_id"], "suggest_test", state, start_time)
        
        return state
        
    except Exception as e:
        error_msg = f"Suggest test node failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        state["errors"].append({
            "node": "suggest_test",
            "error": str(e),
            "type": type(e).__name__
        })
        
        state["status"] = "suggest_test_failed"
        handle_node_error(logger, state["run_id"], "suggest_test", e, state)
        
        raise
