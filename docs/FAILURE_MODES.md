# Failure Modes

This page summarizes the current failure handling behavior in FailBot.

## LLM Output Invalid
- **Cause**: Non-JSON or schema mismatch.
- **Mitigation**: Structured output parsing; retry prompts; heuristic fallback.

## Tool Call Failure
- **Cause**: MCP server not running, REST auth failure, or network error.
- **Mitigation**: MCP → REST API → local markdown fallback.

## Log Too Large
- **Cause**: CI logs exceed token limit.
- **Mitigation**: Head+tail truncation with a logged reason.

## Missing Error in Truncated Log
- **Cause**: The interesting failure may fall outside the truncated section.
- **Mitigation**: The current system records the truncation reason and keeps the full log text available in state for downstream logic and future fallback handling.

## Missing Context
- **Cause**: Log lacks clear error signature.
- **Mitigation**: Heuristic parsing and default classification.

## Graph Reference
- See [failbot_graph.png](../failbot_graph.png) for the current pipeline layout.
