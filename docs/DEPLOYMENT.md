# Deployment

This repository is designed to run locally first and can optionally use MCP GitHub integration for issue filing.

## Local CLI
- Create a virtual environment.
- Install dependencies with `pip install -e .[dev]`.
- Export `OPENAI_API_KEY` and `GITHUB_TOKEN`.
- Run `python -m src.main`.

## Runtime Notes
- The ingest step fetches or reads a log, then truncates it with the head+tail strategy when the log is too large.
- The report step writes summary output and structured execution data to the configured output directory.

## MCP GitHub (Optional)
- Ensure Node.js is installed.
- Set `MCP_GITHUB_SERVER_CMD` to the MCP server command.
- Enable `FAILBOT_USE_MCP=true`.

## Logs
- JSONL logs are written to `runs/`.
- Use `python -m src.metrics analyze` to summarize runs.

## Streamlit Dashboard
- Launch the dashboard with `streamlit run dashboard/app.py`.
- The dashboard depends on the repo's local `runs/` and `evals/results/` data.

## Graph Reference
- The current pipeline graph is documented in [failbot_graph.png](../failbot_graph.png) and summarized in [docs/ARCHITECTURE.md](ARCHITECTURE.md).
