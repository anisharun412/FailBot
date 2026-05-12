"""Tests for parse_log fallback helpers."""

from src.nodes.parse_log import fallback_parse_log


def test_fallback_parse_log_detects_javascript_node_modules_stacktrace():
    log_text = """
TypeError: Cannot read properties of undefined
    at myFunc (file:///workspace/node_modules/pkg/index.js:10:2)
    at run (file:///workspace/src/main.js:2:1)
"""

    parsed = fallback_parse_log(log_text)

    assert parsed.language == "javascript"
    assert parsed.error_signature == "Cannot read properties of undefined"
