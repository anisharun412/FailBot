"""FailBot evaluation harness (Phase 6)."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import time
from pathlib import Path
from typing import Dict, Any, List

from evals.metrics import compute_row_metrics, summarize
from src.main import run_failbot


async def _evaluate_log(
    log_path: Path,
    repo: str,
    expected: Dict[str, Any],
    config_path: str | None,
    output_dir: str,
) -> Dict[str, Any]:
    start = time.time()
    state = await run_failbot(
        log_source=str(log_path),
        repo_name=repo,
        config_path=config_path,
        output_dir=output_dir,
    )
    duration_ms = int((time.time() - start) * 1000)

    metrics = compute_row_metrics(state, expected)

    return {
        "log_file": log_path.name,
        "duration_ms": duration_ms,
        "status": state.get("status"),
        "failure_category": state.get("failure_category"),
        "severity": state.get("severity"),
        "triage_confidence": state.get("triage_confidence"),
        "test_language": state.get("test_language"),
        "github_issue_url": state.get("github_issue_url") or state.get("fallback_issue_path"),
        "error_count": len(state.get("errors", [])),
        **metrics,
    }


async def run_evals(args: argparse.Namespace) -> int:
    logs_dir = Path(args.logs_dir)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not logs_dir.exists():
        raise FileNotFoundError(f"Logs directory not found: {logs_dir}")

    with open(args.ground_truth, "r", encoding="utf-8") as handle:
        ground_truth = json.load(handle)

    log_files = sorted(logs_dir.glob("*.txt"))
    if args.limit:
        log_files = log_files[: args.limit]

    rows: List[Dict[str, Any]] = []
    for log_path in log_files:
        expected = ground_truth.get(log_path.name)
        if not expected:
            continue

        row = await _evaluate_log(
            log_path=log_path,
            repo=args.repo,
            expected=expected,
            config_path=args.config,
            output_dir=args.output,
        )
        rows.append(row)

    summary = summarize(rows)

    csv_path = output_dir / "eval_results.csv"
    json_path = output_dir / "eval_summary.json"
    html_path = output_dir / "eval_report.html"

    if rows:
        with open(csv_path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump({"summary": summary, "rows": rows}, handle, indent=2)

    with open(html_path, "w", encoding="utf-8") as handle:
        handle.write("<html><head><title>FailBot Eval Report</title></head><body>")
        handle.write("<h1>FailBot Evaluation Report</h1>")
        handle.write("<h2>Summary</h2>")
        handle.write("<ul>")
        for key, value in summary.items():
            handle.write(f"<li>{key}: {value:.2f}</li>")
        handle.write("</ul>")

        handle.write("<h2>Runs</h2>")
        handle.write("<table border='1' cellpadding='6' cellspacing='0'>")
        if rows:
            handle.write("<tr>")
            for key in rows[0].keys():
                handle.write(f"<th>{key}</th>")
            handle.write("</tr>")
            for row in rows:
                handle.write("<tr>")
                for key in rows[0].keys():
                    handle.write(f"<td>{row.get(key, '')}</td>")
                handle.write("</tr>")
        handle.write("</table>")
        handle.write("</body></html>")

    print(f"Eval results saved to: {csv_path}")
    print(f"Eval summary saved to: {json_path}")
    print(f"Eval report saved to: {html_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="FailBot evaluation harness")
    parser.add_argument("--logs-dir", default="evals/test_logs", help="Directory with log files")
    parser.add_argument("--ground-truth", default="evals/ground_truth.json", help="Ground truth JSON")
    parser.add_argument("--output", default="evals/results", help="Output directory")
    parser.add_argument("--repo", required=True, help="GitHub repo (owner/repo)")
    parser.add_argument("--config", default=None, help="Path to config/prompts.yaml")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of logs")

    args = parser.parse_args()
    return asyncio.run(run_evals(args))


if __name__ == "__main__":
    raise SystemExit(main())
