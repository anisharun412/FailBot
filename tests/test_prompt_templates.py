"""Unit tests for prompt template rendering."""

import pytest

from src.utils.prompt_templates import render_prompt, render_agent_prompt


def test_render_prompt_simple():
    rendered = render_prompt("Hello {name}", name="FailBot")
    assert rendered == "Hello FailBot"


def test_render_agent_prompt_system():
    prompt = render_agent_prompt("log_parser", "system")
    assert isinstance(prompt, str)
    assert len(prompt) > 20


def test_render_agent_prompt_missing_variable():
    with pytest.raises(ValueError):
        render_agent_prompt("test_suggester", "system")
