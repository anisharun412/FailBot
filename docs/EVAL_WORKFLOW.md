# Evaluation Workflow

This workflow evaluates the current FailBot pipeline against labeled CI logs and produces scored reports for regression tracking.

## Inputs
- Logs: `evals/test_logs/*.txt`
- Ground truth: `evals/ground_truth.json`

The evaluator compares the parsed outputs from the current graph against the expected failure category, severity, and test-relevance signals.

## Run

```bash
python -m evals.eval --repo owner/repo
```

## Outputs
- `evals/results/eval_results.csv`
- `evals/results/eval_summary.json`
- `evals/results/eval_report.html`

## Metrics
- Category accuracy
- Severity accuracy (exact or +/-1 step)
- Test keyword recall

## Current System Coverage
- Ingest truncation behavior is included in the evaluated pipeline.
- The evaluation harness records structured run output, timing, and token counts.
- Batch reports are written under `evals/results/`.

## Iteration Loop
1. Modify prompts or heuristics.
2. Re-run evals.
3. Compare summary scores.
