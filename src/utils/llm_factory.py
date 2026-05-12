"""LLM factory for FailBot.

Selects a chat model based on available API keys.
"""

from __future__ import annotations

import os
from typing import Optional

from langchain_core.language_models.chat_models import BaseChatModel

from src.config import get_config


def _select_provider() -> Optional[str]:
    if os.getenv("GROQ_API_KEY"):
        return "groq"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    return None


def get_chat_model(
    role: str,
    temperature: float,
    max_tokens: Optional[int] = None,
    json_object_mode: bool = False,
) -> BaseChatModel:
    """
    Create a chat model based on available API keys.

    Priority:
    1) GROQ_API_KEY -> ChatGroq with optional JSON Object Mode
    2) OPENAI_API_KEY -> ChatOpenAI with optional JSON mode

    Args:
        role: Configuration role for the model
        temperature: Sampling temperature (0-2)
        max_tokens: Maximum tokens in response
        json_object_mode: Enable JSON Object Mode for guaranteed valid JSON output
                         (per official Groq/OpenAI documentation)

    Note: JSON mode and tool calling cannot be combined per official Groq/OpenAI docs.
    Use json_object_mode=True for structured JSON responses, or use tool calling
    with prompt-based JSON instructions instead.
    """
    config = get_config()
    model_name = config.get_model(role)

    provider = _select_provider()
    if provider == "groq":
        from langchain_groq import ChatGroq

        kwargs = {
            "model": model_name,
            "temperature": temperature,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        
        # JSON Object Mode for Groq (official docs: all models support this)
        if json_object_mode:
            kwargs["model_kwargs"] = {
                "response_format": {"type": "json_object"}
            }

        return ChatGroq(**kwargs)

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        kwargs = {
            "model": model_name,
            "temperature": temperature,
        }
        if max_tokens is not None:
            kwargs["max_completion_tokens"] = max_tokens
        
        # JSON mode for OpenAI
        if json_object_mode:
            kwargs["model_kwargs"] = {
                "response_format": {"type": "json_object"}
            }

        return ChatOpenAI(**kwargs)

    raise RuntimeError(
        "No API key found. Set GROQ_API_KEY or OPENAI_API_KEY to enable LLM calls."
    )
