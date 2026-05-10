# Deployment

## Local CLI
- Create a virtual environment.
- Install dependencies with `pip install -e .[dev]`.
- Export `OPENAI_API_KEY` and `GITHUB_TOKEN`.
- Run `python -m src.main`.

## MCP GitHub (Optional)
- Ensure Node.js is installed.
- Set `MCP_GITHUB_SERVER_CMD` to the MCP server command.
- Enable `FAILBOT_USE_MCP=true`.

## Logs
- JSONL logs are written to `runs/`.
- Use `python -m src.metrics analyze` to summarize runs.
