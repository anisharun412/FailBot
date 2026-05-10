# API Reference

## CLI

```bash
python -m src.main --log-source <path|url> --repo owner/repo
```

## Evaluation

```bash
python -m evals.eval --repo owner/repo
```

## Public Functions

- `src.main.run_failbot(log_source, repo_name, config_path=None, output_dir="runs")`
- `src.graph.get_graph()`
- `src.state.create_initial_state(log_source, repo_name, run_id=None)`
