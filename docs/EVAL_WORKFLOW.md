# Evaluation Workflow

## Inputs
- Logs: `evals/test_logs/*.txt`
- Ground truth: `evals/ground_truth.json`

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

## Iteration Loop
1. Modify prompts or heuristics.
2. Re-run evals.
3. Compare summary scores.
