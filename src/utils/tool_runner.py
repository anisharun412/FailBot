"""Tool execution helpers for LangGraph tool binding."""

from __future__ import annotations

import json
from typing import List

from langchain_core.messages import AIMessage, ToolMessage

from src.tools.langchain_tools import FAILBOT_TOOLS

try:
    from langgraph.prebuilt import ToolNode
except Exception:  # pragma: no cover - fallback for older langgraph
    ToolNode = None


_TOOL_REGISTRY = {tool.name: tool for tool in FAILBOT_TOOLS}
_TOOL_NODE = ToolNode(FAILBOT_TOOLS) if ToolNode else None


def _normalize_tool_output(output: object) -> str:
    if isinstance(output, str):
        return output
    return json.dumps(output, ensure_ascii=True)


async def run_tool_calls(message: AIMessage) -> List[ToolMessage]:
    """
    Execute tool calls from an AIMessage and return ToolMessages.

    Uses LangGraph ToolNode when available; falls back to direct tool invocation.
    """
    if not getattr(message, "tool_calls", None):
        return []

    if _TOOL_NODE is not None:
        result = await _TOOL_NODE.ainvoke({"messages": [message]})
        return result.get("messages", [])

    tool_messages: List[ToolMessage] = []
    for tool_call in message.tool_calls:
        tool_name = tool_call.get("name")
        tool = _TOOL_REGISTRY.get(tool_name)
        if tool is None:
            continue

        tool_args = tool_call.get("args", {})
        try:
            output = await tool.ainvoke(tool_args)
        except Exception as exc:  # pragma: no cover - safety fallback
            output = {"success": False, "error": str(exc)}

        tool_messages.append(
            ToolMessage(
                content=_normalize_tool_output(output),
                name=tool_name or "unknown",
                tool_call_id=tool_call.get("id"),
            )
        )

    return tool_messages


def parse_tool_message(tool_message: ToolMessage) -> dict:
    """Parse a ToolMessage payload into a dict when possible."""
    content = tool_message.content
    if isinstance(content, dict):
        return content
    if not content:
        return {}
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"raw": content}
