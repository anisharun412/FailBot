"""
FailBot CLI Entry Point

Main interface for running the FailBot pipeline.
"""

import asyncio
import argparse
import logging
import sys
from pathlib import Path
from typing import Optional, cast, Dict

from src.state import create_initial_state, FailBotState
from src.config import load_config
from src.graph import get_graph
from src.utils.logging_config import setup_json_logging
from src.utils.graph_utils import create_execution_summary, format_state_snapshot
from src.callbacks.logging_callback import FailBotEventLogger
from evals.scoring import score_run_with_ground_truth, update_summary_file


def _build_log_source_help() -> str:
    sample_dir = Path("tests/test_log_files")
    if sample_dir.exists():
        samples = sorted(sample_dir.glob("*.log"))
        if samples:
            lines = "\n".join(f"  - {s.as_posix()}" for s in samples[:4])
            return f"Examples:\n{lines}"
    return "Example:\n  - tests/test_log_files/log.txt"


async def run_failbot(
    log_source: str,
    repo_name: Optional[str] = None,
    config_path: Optional[str] = None,
    output_dir: str = "runs"
) -> FailBotState:
    """
    Run the FailBot pipeline.
    
    Args:
        log_source: Path to log file or URL
        repo_name: GitHub repository (owner/repo). Defaults to "unknown" if omitted.
        config_path: Path to config/prompts.yaml
        output_dir: Output directory for logs
    
    Returns:
        Final state dictionary
    """
    # Load config
    config = load_config(config_path)
    
    # Setup logging
    logger = setup_json_logging(output_dir)
    
    # Create initial state
    state = create_initial_state(log_source, repo_name)
    run_id = state["run_id"]
    
    logger.info(f"Starting FailBot run: {run_id}")
    
    try:
        # Get graph
        graph = get_graph()
        
        # Create event logger callback
        event_logger = FailBotEventLogger(logger, run_id)
        
        # Run graph with callbacks
        logger.info(f"Invoking graph with log source: {log_source}")
        final_state_raw = await graph.ainvoke(state, config={"callbacks": [event_logger]})
        final_state: FailBotState = cast(FailBotState, final_state_raw)
        
        # Create summary
        summary = create_execution_summary(final_state)

        # Attach eval scores when ground-truth exists for this log source
        matched_key, expected, eval_scores = score_run_with_ground_truth(
            cast(Dict[str, object], final_state),
            log_source=log_source,
            ground_truth_path=None,
        )
        if eval_scores is not None:
            summary["eval_scores"] = eval_scores

            summary_path = final_state.get("execution_summary_path")
            if summary_path:
                update_summary_file(summary_path, eval_scores)

            logger.info(
                "Eval scores attached for %s using ground-truth key %s",
                log_source,
                matched_key,
            )
        
        logger.info(f"FailBot run completed: {run_id}")
        
        return final_state
    
    except Exception as e:
        logger.error(f"FailBot run failed: {str(e)}", exc_info=True)
        state["status"] = "failed"
        state["errors"].append({
            "node": "main",
            "error": f"Pipeline error: {str(e)}",
            "type": type(e).__name__
        })
        return state


def print_summary(state: FailBotState) -> None:
    """
    Print a formatted summary of execution.
    
    Args:
        state: Final state
    """
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    
    console = Console()
    
    # Title
    console.print(
        Panel(
            f"FailBot Execution Report - Run: {state['run_id'][:8]}",
            style="bold blue"
        )
    )
    
    # Status and timing
    status_color = "green" if state.get("status") == "completed" else "red"
    console.print(f"Status: [{status_color}]{state.get('status', 'unknown')}[/{status_color}]")
    
    # Triage results
    if state.get("failure_category"):
        console.print(f"Category: {state['failure_category']} ({state.get('severity', 'unknown')} severity)")
        console.print(f"Confidence: {state.get('triage_confidence', 0):.1%}")
    
    # Test generation
    if state.get("suggested_test"):
        console.print(f"Test Language: {state.get('test_language', 'unknown')}")
        console.print(f"Test Generated: YES")
    
    # Issue filing
    if state.get("github_issue_url"):
        console.print(f"GitHub Issue: {state['github_issue_url']}")
    elif state.get("fallback_issue_path"):
        console.print(f"Fallback Issue: {state['fallback_issue_path']}")

    fallback_items = []
    if state.get("agent_fallback_used"):
        fallback_items.append("log parsing used regex fallback")
    if state.get("issue_fallback_used"):
        fallback_items.append("issue filed to local markdown")

    if fallback_items:
        console.print("Fallbacks:")
        for item in fallback_items:
            console.print(f"  - {item}")
    
    # Errors
    if state.get("errors"):
        console.print(f"\n[red]Errors ({len(state['errors'])}):[/red]")
        for error in state["errors"]:
            console.print(f"  - {error}")
    
    success_statuses = {"completed", "report_complete", "file_issue_complete"}
    if state.get("status") in success_statuses:
        if fallback_items:
            console.print("\nRun completed with non-critical fallbacks.")
        else:
            console.print("\nRun completed successfully!")
    else:
        console.print("\nRun completed with errors.")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="FailBot - Multi-Agent CI Failure Triage & Test Generation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run on local log file
  python -m src.main --log-source /path/to/build.log --repo owner/repo
  
  # Run on GitHub Actions log
  python -m src.main --log-source https://github.com/.../logs/1234 --repo owner/repo
  
  # Use custom config
  python -m src.main --log-source test.log --repo owner/repo --config my_config.yaml
        """
    )
    
    parser.add_argument(
        "--log-source",
        required=True,
        help="Path to log file or URL to fetch"
    )
    
    parser.add_argument(
        "--repo",
        required=False,
        default="unknown",
        help="GitHub repository (owner/repo). Defaults to 'unknown' if omitted."
    )
    
    parser.add_argument(
        "--config",
        default=None,
        help="Path to config/prompts.yaml"
    )
    
    parser.add_argument(
        "--output-dir",
        default="runs",
        help="Output directory for logs (default: runs)"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Set log level
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    # Validate log source before running pipeline
    if not args.log_source.startswith(("http://", "https://")):
        log_path = Path(args.log_source)
        if not log_path.is_file():
            print(f"✗ Log source not found: {args.log_source}", file=sys.stderr)
            print("Provide a valid file path or URL.", file=sys.stderr)
            print(_build_log_source_help(), file=sys.stderr)
            sys.exit(2)
    
    # Run pipeline
    try:
        state = asyncio.run(
            run_failbot(
                log_source=args.log_source,
                repo_name=args.repo,
                config_path=args.config,
                output_dir=args.output_dir
            )
        )
        
        # Print summary
        print_summary(state)
        
        # Exit with status code
        sys.exit(0 if state.get("status") == "completed" else 1)
    
    except KeyboardInterrupt:
        print("\n✗ Interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
