"""Report node: Generate final summary and save results."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from src.state import FailBotState
from src.utils.graph_utils import (
    format_state_snapshot,
    handle_node_error,
    log_node_end,
    log_node_start,
)
from src.utils.logging_config import log_event


logger = logging.getLogger(__name__)
console = Console()


def print_formatted_report(state: FailBotState) -> None:
    """
    Print formatted report to console using Rich.
    
    Shows timing, token usage, and fallback information.
    
    Args:
        state: FailBotState with all execution results
    """
    # Status panel
    failure_category = state.get("failure_category") or "unknown"
    error_signature = (state.get("error_signature") or "N/A")[:80]
    suggested_test = state.get("suggested_test") or ""
    test_language = state.get("test_language") or "text"

    status_color = {
        "code_bug": "red",
        "flaky": "yellow",
        "infra": "cyan",
        "unknown": "white"
    }.get(failure_category, "white")
    
    status_text = f"""
[bold][{status_color}]{failure_category.upper()}[/{status_color}][/bold]

Error Signature: {error_signature}
Severity: {state.get('severity', 'unknown')}
Confidence: {state.get('triage_confidence', 0):.0%}
Status: {state.get('status', 'unknown')}
"""
    
    console.print(Panel(status_text.strip(), title="Triage Result", expand=False))
    
    # Test/Strategy
    if suggested_test:
        if test_language == "strategy":
            try:
                test_content = suggested_test
                # Clean up Unicode characters that might cause encoding issues
                test_content = test_content.encode('ascii', errors='replace').decode('ascii')
                console.print(Panel(
                    test_content,
                    title=f"Test Strategy ({state.get('test_description')})",
                    expand=False
                ))
            except Exception as e:
                logger.warning(f"Failed to display test strategy: {e}")
                console.print(f"Test strategy generated (display issue: {str(e)[:50]})")
        else:
            try:
                test_content = suggested_test[:2000]
                # Clean up Unicode characters
                test_content = test_content.encode('ascii', errors='replace').decode('ascii')
                syntax = Syntax(
                    test_content,
                    test_language,
                    theme="monokai",
                    line_numbers=True
                )
                console.print(Panel(syntax, title=f"Generated Test ({state.get('test_language')})", expand=False))
            except Exception as e:
                logger.warning(f"Failed to display generated test: {e}")
                console.print(f"Test code generated (display issue: {str(e)[:50]})")
    
    # Issue
    if state.get("github_issue_url"):
        issue_text = f"Issue filed at: {state['github_issue_url']}"
        if state.get("issue_fallback_used"):
            issue_text += " [yellow](markdown fallback)[/yellow]"
        console.print(Panel(issue_text, title="GitHub Issue", expand=False))
    
    # Errors (if any) - separate from fallbacks
    non_fallback_errors = [
        e for e in (state.get("errors", []))
        if e.get("type") not in ["agent_fallback", "issue_fallback"]
    ]
    
    if non_fallback_errors:
        errors_text = "\n".join(
            f"* [{e.get('node', 'unknown')}] {e.get('error', 'Unknown error')}"
            for e in non_fallback_errors[:3]
        )
        console.print(Panel(errors_text, title="Errors", expand=False, style="red"))
    
    # Fallback summary
    fallback_items = []
    if state.get("agent_fallback_used"):
        fallback_items.append("log parsing used regex fallback")
    if state.get("issue_fallback_used"):
        fallback_items.append("issue filed to local markdown")
    
    if fallback_items:
        fallback_text = "Run completed with non-critical fallbacks:\n* " + "\n* ".join(fallback_items)
        console.print(Panel(fallback_text, title="Fallbacks", expand=False, style="yellow"))
    
    # Timing (if available)
    if state.get("node_durations_ms"):
        timing_table = Table(title="Execution Timing (ms)")
        timing_table.add_column("Node", style="cyan")
        timing_table.add_column("Duration", justify="right", style="green")
        
        for node, duration_ms in sorted(state["node_durations_ms"].items()):
            timing_table.add_row(node, f"{duration_ms:.1f}")
        
        total_duration = sum(state["node_durations_ms"].values())
        timing_table.add_row("[bold]Total[/bold]", f"[bold]{total_duration:.1f}[/bold]")
        console.print(timing_table)
    
    # Token usage
    if state.get("token_counts"):
        tokens_table = Table(title="Token Usage")
        tokens_table.add_column("Component", style="cyan")
        tokens_table.add_column("Tokens", justify="right", style="green")
        
        for node, tokens in sorted(state["token_counts"].items()):
            tokens_table.add_row(node, str(tokens))
        
        total_tokens = sum(state["token_counts"].values())
        tokens_table.add_row("[bold]Total[/bold]", f"[bold]{total_tokens}[/bold]")
        
        console.print(tokens_table)


def save_execution_summary(state: FailBotState, output_dir: str = "runs") -> str:
    """
    Save execution summary as JSON file.
    
    Args:
        state: FailBotState with all execution results
        output_dir: Directory to save summary
        
    Returns:
        Path to saved JSON file
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Create summary filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"summary_{timestamp}_{state.get('run_id', 'unknown')[:8]}.json"
    file_path = output_path / filename
    
    # Prepare summary data
    summary = {
        "run_id": state.get("run_id"),
        "timestamp": datetime.now().isoformat(),
        "status": state.get("status"),
        "repo_name": state.get("repo_name"),
        "log_source": state.get("log_source"),
        "failure_category": state.get("failure_category"),
        "severity": state.get("severity"),
        "triage_confidence": state.get("triage_confidence"),
        "error_signature": state.get("error_signature"),
        "language": state.get("language"),
        "files_changed": state.get("files_changed", []),
        "test_generated": bool(state.get("suggested_test")),
        "test_language": state.get("test_language"),
        "test_confidence": state.get("test_confidence"),
        "issue_filed": bool(state.get("github_issue_url")),
        "github_issue_url": state.get("github_issue_url"),
        "agent_fallback_used": state.get("agent_fallback_used", False),
        "issue_fallback_used": state.get("issue_fallback_used", False),
        "error_count": len(state.get("errors", [])),
        "token_counts": state.get("token_counts", {}),
        "total_tokens": sum(state.get("token_counts", {}).values()),
        "node_durations_ms": state.get("node_durations_ms", {}),
        "total_duration_ms": sum(state.get("node_durations_ms", {}).values()),
        "errors": state.get("errors", [])
    }
    
    # Write JSON
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    
    return str(file_path)


async def report_node(state: FailBotState) -> FailBotState:
    """
    Report node: Generate final summary and save results.
    
    Prints formatted report to console and saves execution summary as JSON.
    
    Args:
        state: FailBotState with all execution results
        
    Returns:
        Updated state dict with:
        - status: Updated to 'report_complete' or 'report_failed'
        - execution_summary_path: Path to saved JSON summary
    """
    start_time = log_node_start(
        logger, state["run_id"], "report", state
    )
    
    try:
        log_event(
            logger, state["run_id"], "report",
            "report_generation_start",
            {"status": state.get("status")}
        )
        
        # Print formatted report
        print_formatted_report(state)
        
        # Save summary JSON
        summary_path = save_execution_summary(
            state,
            output_dir=state.get("output_dir", "runs")
        )
        
        log_event(
            logger, state["run_id"], "report",
            "report_saved",
            {"path": summary_path}
        )
        
        # Update state
        state["execution_summary_path"] = summary_path
        state["status"] = "report_complete"
        
        log_node_end(logger, state["run_id"], "report", state, start_time)
        
        return state
        
    except Exception as e:
        error_msg = f"Report node failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        if "errors" not in state or state["errors"] is None:
            state["errors"] = []
        state["errors"].append({
            "node": "report",
            "error": str(e),
            "type": type(e).__name__
        })
        
        state["status"] = "report_failed"
        handle_node_error(logger, state["run_id"], "report", e, state)
        
        raise
