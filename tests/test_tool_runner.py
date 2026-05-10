"""Unit tests for tool runner helpers."""

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from src.utils.tool_runner import run_tool_calls, parse_tool_message


@pytest.mark.asyncio
async def test_run_tool_calls_validate_code():
    message = AIMessage(
        content="Run tool",
        tool_calls=[
            {
                "id": "call_1",
                "name": "validate_code_syntax",
                "args": {"code": "print('ok')", "language": "python"},
            }
        ],
    )

    tool_messages = await run_tool_calls(message)
    assert tool_messages, "Expected at least one tool message"

    tool_message = next(
        (msg for msg in tool_messages if isinstance(msg, ToolMessage)),
        tool_messages[0],
    )
    parsed = parse_tool_message(tool_message)
    assert parsed.get("is_valid") is True


def test_parse_tool_message_raw():
    message = ToolMessage(content="plain text", name="dummy", tool_call_id="x")
    parsed = parse_tool_message(message)
    assert parsed.get("raw") == "plain text"
