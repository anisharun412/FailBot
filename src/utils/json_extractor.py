"""Utility for extracting JSON from LLM responses, including markdown code blocks."""

import json
import logging
import re
from typing import Any


logger = logging.getLogger(__name__)


def extract_json_from_response(response_text: str) -> dict[str, Any]:
    """
    Extract JSON from LLM response, handling markdown code blocks and thinking blocks.
    
    LLMs often wrap JSON in markdown code blocks like:
    ```json
    {"key": "value"}
    ```
    
    Some models (like Groq qwen) may also include thinking blocks:
    <think>reasoning text</think>
    {"key": "value"}
    
    This function handles:
    1. Thinking/reasoning blocks (<think>...</think> or <reasoning>...</reasoning>)
    2. Markdown code blocks with ```json ... ```
    3. Markdown code blocks with plain ```  ... ```
    4. Bare JSON without wrapping
    5. JSON with leading/trailing text
    
    Args:
        response_text: Raw LLM response text
        
    Returns:
        Parsed JSON dict
        
    Raises:
        ValueError: If no valid JSON found
        json.JSONDecodeError: If JSON is malformed
    """
    if not isinstance(response_text, str):
        raise ValueError(f"Invalid response text: {type(response_text)}")
    
    # Strip thinking/reasoning blocks first
    # Remove <think>...</think>, <reasoning>...</reasoning>, and similar blocks
    cleaned_text = re.sub(r"<think>.*?</think>", "", response_text, flags=re.IGNORECASE | re.DOTALL)
    cleaned_text = re.sub(r"<reasoning>.*?</reasoning>", "", cleaned_text, flags=re.IGNORECASE | re.DOTALL)
    cleaned_text = re.sub(r"<analysis>.*?</analysis>", "", cleaned_text, flags=re.IGNORECASE | re.DOTALL)
    cleaned_text = cleaned_text.strip()  # Remove leading/trailing whitespace
    
    # First try: extract from markdown code blocks
    # Match ```json ... ``` or ``` ... ```
    code_block_patterns = [
        r"```json\s*(.*?)\s*```",  # ```json { ... } ```
        r"```\s*(.*?)\s*```",       # ``` { ... } ```
    ]
    
    for pattern in code_block_patterns:
        match = re.search(pattern, cleaned_text, re.DOTALL)
        if match:
            json_text = match.group(1).strip()
            try:
                return json.loads(json_text)
            except json.JSONDecodeError as e:
                logger.debug(f"JSON in code block is malformed: {e}")
                # Continue to next pattern
    
    # Second try: extract bare JSON (look for { ... })
    json_start = cleaned_text.find('{')
    json_end = cleaned_text.rfind('}') + 1
    
    if json_start >= 0 and json_end > json_start:
        json_text = cleaned_text[json_start:json_end]
        try:
            return json.loads(json_text)
        except json.JSONDecodeError as e:
            logger.debug(f"Bare JSON is malformed: {e}")
            raise ValueError(f"No valid JSON found in response: {e}")
    
    raise ValueError(f"No JSON found in response: {response_text[:200]}")
