"""Tests for graph utility summaries."""

from src.state import FailBotState, create_initial_state

from src.utils.graph_utils import create_execution_summary


def test_create_execution_summary_falls_back_to_timestamps_when_durations_empty():
    # Use factory to create a fully typed FailBotState and then set relevant fields
    state: FailBotState = create_initial_state(log_source="test", run_id="run-123")
    state["status"] = "completed"
    state["node_durations_ms"] = {}
    state["node_timestamps"] = {"parse_log": 12.5}
    state["errors"] = []

    summary = create_execution_summary(state)

    assert summary["total_duration_ms"] == 12.5


def test_create_execution_summary_falls_back_when_duration_map_invalid():
    state: FailBotState = create_initial_state(log_source="test", run_id="run-123")
    state["status"] = "completed"
    # Intentionally set an invalid type for node_durations_ms to exercise fallback
    state["node_durations_ms"] = "invalid"  # type: ignore
    state["node_timestamps"] = {"parse_log": 12.5, "triage": 7.5}
    state["errors"] = []

    summary = create_execution_summary(state)

    assert summary["total_duration_ms"] == 20.0
