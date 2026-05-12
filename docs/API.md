# API Reference

This project exposes a CLI, a LangGraph builder, and a typed shared state object for the current multi-agent workflow.

## CLI

```bash
python -m src.main --log-source <path|url> --repo owner/repo
```

## Current Workflow

The live graph currently runs through:

1. Ingest
2. Parse Log
3. Triage
4. Suggest Test or Suggest Test Generic when appropriate
5. File Issue
6. Report

Large logs are truncated with the head+tail strategy in ingest, and the truncation reason is stored in state.

## Evaluation

```bash
python -m evals.eval --repo owner/repo
```

## Dashboard

```bash
streamlit run dashboard/app.py
python -m src.tools.dashboard
```

The dashboard layer has two entry points: the Streamlit UI in the [dashboard/](../dashboard/) folder and the Rich terminal dashboard in [src/tools/dashboard.py](../src/tools/dashboard.py). The Streamlit UI visualizes run summaries, eval results, issue drafts, and pipeline status from the repo data files. The terminal dashboard tails JSONL run logs and shows live execution progress.

## Public Functions

- `src.main.run_failbot(log_source, repo_name, config_path=None, output_dir="runs")`
- `src.graph.get_graph()`
- `src.state.create_initial_state(log_source, repo_name, run_id=None)`

## Shared State

The main state definition lives in [src/state.py](../src/state.py). Key fields include:

- Input metadata such as `log_source`, `repo_name`, and `run_id`
- Log data such as `log_text_full`, `log_text`, and `log_truncated_reason`
- Runtime tracking such as `token_counts`, `node_durations_ms`, and `status`
- Node outputs such as `parsed_summary`, `failure_category`, `severity`, and `github_issue_url`

## Model Selection

The LLM factory in [src/utils/llm_factory.py](../src/utils/llm_factory.py) selects providers in this order:

1. Groq when `GROQ_API_KEY` is present
2. OpenAI when `OPENAI_API_KEY` is present
3. Runtime error if neither key is configured
