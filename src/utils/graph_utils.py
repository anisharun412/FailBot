"""
LangGraph Utilities

Helper functions for graph construction and execution.
"""

import time
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from src.state import FailBotState


def log_node_start(
    logger: logging.Logger,
    run_id: str,
    node_name: str,
    state: FailBotState
) -> float:
    """
    Log the start of a node execution.
    
    Args:
        logger: Logger instance
        run_id: Run ID
        node_name: Name of the node
        state: Current state
    
    Returns:
        Start time (for latency calculation)
    """
    start_time = time.time()
    
    record = logging.LogRecord(
        name="failbot",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg=f"Starting node: {node_name}",
        args=(),
        exc_info=None
    )
    
    record.run_id = run_id
    record.node = node_name
    record.event_type = "node_start"
    record.data = {
        "log_source": (state.get("log_source") or "")[:50],  # Truncate for readability
        "status": state.get("status", "unknown"),
        "errors_count": len(state.get("errors") or []),
    }
    
    logger.handle(record)
    return start_time


def log_node_end(
    logger: logging.Logger,
    run_id: str,
    node_name: str,
    state: FailBotState,
    start_time: float
) -> None:
    """
    Log the end of a node execution.
    
    Args:
        logger: Logger instance
        run_id: Run ID
        node_name: Name of the node
        state: Updated state
        start_time: Start time from log_node_start
    """
    duration_ms = (time.time() - start_time) * 1000
    
    # Get node outputs (change based on node)
    data: Dict[str, Any] = {
        "duration_ms": duration_ms,
        "status": state.get("status", "unknown"),
    }
    
    if node_name == "ingest":
        data["log_text_length"] = len(state.get("log_text") or "")
        data["truncated"] = state.get("log_truncated_reason") is not None
    
    elif node_name == "parse_log":
        data["has_error_signature"] = state.get("error_signature") is not None
        data["files_changed_count"] = len(state.get("files_changed") or [])
    
    elif node_name == "triage":
        data["category"] = state.get("failure_category", "unknown")
        data["severity"] = state.get("severity", "unknown")
        data["confidence"] = state.get("triage_confidence", 0.0)
    
    elif node_name == "suggest_test":
        data["test_language"] = state.get("test_language", "unknown")
        data["has_test"] = state.get("suggested_test") is not None
        data["validation_errors"] = len(state.get("test_validation_errors") or [])
    
    elif node_name == "file_issue":
        data["has_issue_url"] = state.get("github_issue_url") is not None
        data["has_fallback"] = state.get("fallback_issue_path") is not None
    
    # Log event
    record = logging.LogRecord(
        name="failbot",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg=f"Completed node: {node_name}",
        args=(),
        exc_info=None
    )
    
    record.run_id = run_id
    record.node = node_name
    record.event_type = "node_end"
    record.duration_ms = duration_ms
    record.data = data
    
    logger.handle(record)


def handle_node_error(
    logger: logging.Logger,
    run_id: str,
    node_name: str,
    error: Exception,
    state: FailBotState
) -> None:
    """
    Log a node error and append to state errors.
    
    Args:
        logger: Logger instance
        run_id: Run ID
        node_name: Name of the node
        error: Exception that occurred
        state: Current state (will be modified)
    """
    error_msg = f"{node_name}: {type(error).__name__}: {str(error)}"
    if not isinstance(state.get("errors"), list):
        state["errors"] = []
    state["errors"].append({
        "node": node_name,
        "error": str(error),
        "type": type(error).__name__,
    })
    
    record = logging.LogRecord(
        name="failbot",
        level=logging.ERROR,
        pathname="",
        lineno=0,
        msg=error_msg,
        args=(),
        exc_info=None
    )
    
    record.run_id = run_id
    record.node = node_name
    record.event_type = "error"
    record.data = {
        "error_type": type(error).__name__,
        "error_message": str(error),
        "errors_count": len(state["errors"]),
    }
    
    logger.handle(record)


def route_after_triage(state: FailBotState) -> str:
    """
    Determine next node based on triage result.
    
    Args:
        state: Current state with triage results
    
    Returns:
        Next node name
    """
    category = state.get("failure_category", "unknown")
    
    if category == "code_bug":
        return "suggest_test"
    elif category in ["flaky", "infra"]:
        return "suggest_test_generic"
    else:  # "unknown"
        return "file_issue"


def format_state_snapshot(state: FailBotState) -> Dict[str, Any]:
    """
    Create a readable snapshot of state for logging.
    
    Args:
        state: State to snapshot
    
    Returns:
        Snapshot dictionary
    """
    return {
        "run_id": (state.get("run_id") or "")[:8],
        "status": state.get("status", "unknown"),
        "failure_category": state.get("failure_category", None),
        "severity": state.get("severity", None),
        "errors_count": len(state.get("errors") or []),
        "has_test": state.get("suggested_test") is not None,
        "has_issue_url": state.get("github_issue_url") is not None,
    }


def create_execution_summary(state: FailBotState) -> Dict[str, Any]:
    """
    Create a summary of the complete execution.
    
    Args:
        state: Final state
    
    Returns:
        Summary dictionary
    """
    node_durations = state.get("node_durations_ms")
    if not isinstance(node_durations, dict) or not node_durations:
        node_timestamps = state.get("node_timestamps")
        if isinstance(node_timestamps, dict):
            node_durations = node_timestamps
        else:
            node_durations = {}
    total_duration_ms = sum(
        float(value)
        for value in node_durations.values()
        if isinstance(value, (int, float))
    )

    started_at = state.get("started_at")
    if isinstance(started_at, datetime):
        started_at_value = started_at.isoformat()
    elif isinstance(started_at, str):
        started_at_value = started_at
    else:
        started_at_value = None
    
    error_list = state.get("errors") or []
    skipped_nodes = state.get("skipped_nodes") or []

    summary = {
        "run_id": state.get("run_id") or "",
        "status": state.get("status", "unknown"),
        "total_duration_ms": total_duration_ms,
        "started_at": started_at_value,
        
        # Triage results
        "failure_category": state.get("failure_category"),
        "severity": state.get("severity"),
        "triage_confidence": state.get("triage_confidence"),
        
        # Test results
        "test_language": state.get("test_language"),
        "has_test": state.get("suggested_test") is not None,
        
        # Issue filing
        "github_issue_url": state.get("github_issue_url"),
        "fallback_issue_path": state.get("fallback_issue_path"),
        
        # Errors
        "error_count": len(error_list),
        "errors": error_list,
        
        # Skipped nodes
        "skipped_nodes": skipped_nodes,
    }
    
    return summary


if __name__ == "__main__":
    # Test utilities
    import logging
    from src.state import create_initial_state
    
    logger = logging.getLogger("test")
    handler = logging.StreamHandler()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    
    state = create_initial_state("test.log", "owner/repo")
    
    # Test routing
    state["failure_category"] = "code_bug"
    next_node = route_after_triage(state)
    print(f"✓ Route after triage (code_bug): {next_node}")
    
    state["failure_category"] = "flaky"
    next_node = route_after_triage(state)
    print(f"✓ Route after triage (flaky): {next_node}")
    
    # Test snapshot
    snapshot = format_state_snapshot(state)
    print(f"✓ State snapshot: {snapshot}")
