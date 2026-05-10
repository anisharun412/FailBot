# Failure Modes

## LLM Output Invalid
- **Cause**: Non-JSON or schema mismatch.
- **Mitigation**: Structured output parsing; retry prompts; heuristic fallback.

## Tool Call Failure
- **Cause**: MCP server not running, REST auth failure, or network error.
- **Mitigation**: MCP → REST API → local markdown fallback.

## Log Too Large
- **Cause**: CI logs exceed token limit.
- **Mitigation**: Head+tail truncation with a logged reason.

## Missing Context
- **Cause**: Log lacks clear error signature.
- **Mitigation**: Heuristic parsing and default classification.
