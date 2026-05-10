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
    
    Args:
        state: FailBotState with all execution results
    """
    # Status panel
    status_color = {
        "code_bug": "red",
        "flaky": "yellow",
        "infra": "cyan",
        "unknown": "white"
    }.get(state.get("failure_category"), "white")
    
    status_text = f"""
[bold][{status_color}]{state.get('failure_category', 'unknown').upper()}[/{status_color}][/bold]

Error Signature: {state.get('error_signature', 'N/A')}
Severity: {state.get('severity', 'unknown')}
Confidence: {state.get('triage_confidence', 0):.0%}
Status: {state.get('status', 'unknown')}
"""
    
    console.print(Panel(status_text.strip(), title="Triage Result", expand=False))
    
    # Test/Strategy
    if state.get("suggested_test"):
        if state.get("test_language") == "strategy":
            console.print(Panel(
                state["suggested_test"],
                title=f"Test Strategy ({state.get('test_description')})",
                expand=False
            ))
        else:
            # Show test code with syntax highlighting
            syntax = Syntax(
                state["suggested_test"],
                state.get("test_language", "text"),
                theme="monokai",
                line_numbers=True
            )
            console.print(Panel(syntax, title=f"Generated Test ({state.get('test_language')})", expand=False))
    
    # Issue
    if state.get("github_issue_url"):
        issue_text = f"Issue filed at: {state['github_issue_url']}"
        if state.get("fallback_issue_path"):
            issue_text += " (local fallback)"
        console.print(Panel(issue_text, title="GitHub Issue", expand=False))
    
    # Errors (if any)
    if state.get("errors"):
        errors_text = "\n".join(
            f"• [{e.get('node', 'unknown')}] {e.get('error', 'Unknown error')}"
            for e in state["errors"][:5]
        )
        console.print(Panel(errors_text, title="Errors", expand=False, style="red"))
    
    # Token usage
    if state.get("token_counts"):
        tokens_table = Table(title="Token Usage")
        tokens_table.add_column("Node", style="cyan")
        tokens_table.add_column("Tokens", justify="right", style="green")
        
        for node, tokens in state["token_counts"].items():
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
        "fallback_used": bool(state.get("fallback_issue_path")),
        "error_count": len(state.get("errors", [])),
        "token_counts": state.get("token_counts", {}),
        "total_tokens": sum(state.get("token_counts", {}).values()),
        "execution_time_ms": state.get("execution_time_ms", 0),
        "skipped_nodes": state.get("skipped_nodes", []),
        "errors": state.get("errors", [])
    }
    
    # Write JSON
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    
    return str(file_path)


async def report_node(state: FailBotState) -> dict[str, Any]:
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
