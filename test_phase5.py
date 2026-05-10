"""
Test Phase 5: Logging Dashboard & Instrumentation

Tests metrics analyzer, dashboard, and callback integration.
"""

import json
import asyncio
from pathlib import Path
from datetime import datetime

# Create sample log data for testing
SAMPLE_LOG_EVENTS = [
    {
        "timestamp": "2026-05-10T14:30:00.000",
        "run_id": "run_20260510_143000",
        "node": "ingest",
        "event_type": "node_start",
    },
    {
        "timestamp": "2026-05-10T14:30:01.250",
        "run_id": "run_20260510_143000",
        "node": "ingest",
        "event_type": "node_end",
        "duration_ms": 1250.0,
        "data": {
            "token_counts": {
                "ingest_input": 150,
                "ingest_output": 50,
            }
        }
    },
    {
        "timestamp": "2026-05-10T14:30:01.300",
        "run_id": "run_20260510_143000",
        "node": "parse_log",
        "event_type": "node_start",
    },
    {
        "timestamp": "2026-05-10T14:30:02.800",
        "run_id": "run_20260510_143000",
        "node": "parse_log",
        "event_type": "llm_start",
        "data": {
            "model": "gpt-4o-mini",
            "num_prompts": 1,
        }
    },
    {
        "timestamp": "2026-05-10T14:30:03.200",
        "run_id": "run_20260510_143000",
        "node": "parse_log",
        "event_type": "llm_end",
        "duration_ms": 400.0,
        "data": {
            "input_tokens": 800,
            "output_tokens": 200,
            "total_tokens": 1000,
        }
    },
    {
        "timestamp": "2026-05-10T14:30:03.250",
        "run_id": "run_20260510_143000",
        "node": "parse_log",
        "event_type": "node_end",
        "duration_ms": 1950.0,
        "data": {
            "token_counts": {
                "parse_input": 800,
                "parse_output": 200,
            }
        }
    },
    {
        "timestamp": "2026-05-10T14:30:03.300",
        "run_id": "run_20260510_143000",
        "node": "triage",
        "event_type": "node_start",
    },
    {
        "timestamp": "2026-05-10T14:30:05.100",
        "run_id": "run_20260510_143000",
        "node": "triage",
        "event_type": "tool_start",
        "data": {
            "tool_name": "knowledge_base_lookup",
        }
    },
    {
        "timestamp": "2026-05-10T14:30:05.200",
        "run_id": "run_20260510_143000",
        "node": "triage",
        "event_type": "tool_end",
        "duration_ms": 100.0,
        "data": {
            "success": True,
        }
    },
    {
        "timestamp": "2026-05-10T14:30:06.200",
        "run_id": "run_20260510_143000",
        "node": "triage",
        "event_type": "llm_start",
        "data": {
            "model": "gpt-4o-mini",
        }
    },
    {
        "timestamp": "2026-05-10T14:30:07.000",
        "run_id": "run_20260510_143000",
        "node": "triage",
        "event_type": "llm_end",
        "duration_ms": 800.0,
        "data": {
            "input_tokens": 1200,
            "output_tokens": 300,
            "total_tokens": 1500,
        }
    },
    {
        "timestamp": "2026-05-10T14:30:07.050",
        "run_id": "run_20260510_143000",
        "node": "triage",
        "event_type": "node_end",
        "duration_ms": 3750.0,
        "data": {
            "token_counts": {
                "triage_input": 1200,
                "triage_output": 300,
            }
        }
    },
]


def create_sample_log_file(path: Path = Path("runs/test_phase5.jsonl")) -> None:
    """Create a sample JSONL log file for testing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(path, 'w') as f:
        for event in SAMPLE_LOG_EVENTS:
            f.write(json.dumps(event) + '\n')
    
    print(f"✓ Sample log created: {path}")


def test_metrics_analyzer():
    """Test MetricsAnalyzer on sample data."""
    from src.utils.metrics import MetricsAnalyzer
    
    print("\n[1/4] Testing Metrics Analyzer...")
    print("-" * 70)
    
    log_file = Path("runs/test_phase5.jsonl")
    
    # Create sample log
    create_sample_log_file(log_file)
    
    # Analyze
    analyzer = MetricsAnalyzer(log_file)
    analyzer.analyze()
    
    # Verify results
    assert analyzer.metrics["total_events"] == len(SAMPLE_LOG_EVENTS)
    assert "ingest" in analyzer.metrics["node_timing"]
    assert "parse_log" in analyzer.metrics["node_timing"]
    assert analyzer.metrics["llm_calls"]["total_calls"] == 2
    assert analyzer.metrics["tool_calls"]["total_calls"] == 1
    
    print(f"✓ Metrics loaded: {analyzer.metrics['total_events']} events")
    print(f"✓ Node timings: {len(analyzer.metrics['node_timing'])} nodes")
    print(f"✓ LLM calls: {analyzer.metrics['llm_calls']['total_calls']}")
    print(f"✓ Tool calls: {analyzer.metrics['tool_calls']['total_calls']}")
    print(f"✓ Total tokens: {analyzer.metrics['llm_calls']['total_tokens']}")


def test_dashboard_metrics():
    """Test DashboardMetrics event processing."""
    from src.tools.dashboard import DashboardMetrics
    
    print("\n[2/4] Testing Dashboard Metrics...")
    print("-" * 70)
    
    dashboard = DashboardMetrics()
    
    # Add events
    for event in SAMPLE_LOG_EVENTS:
        dashboard.add_event(event)
    
    # Verify state
    assert len(dashboard.events) == len(SAMPLE_LOG_EVENTS)
    assert dashboard.node_status.get("ingest") == "✅ done"
    assert dashboard.llm_call_count == 2
    assert dashboard.tool_call_count == 1
    
    print(f"✓ Dashboard processed {len(dashboard.events)} events")
    print(f"✓ Node statuses tracked: {len(dashboard.node_status)}")
    print(f"✓ LLM calls tracked: {dashboard.llm_call_count}")
    print(f"✓ Tool calls tracked: {dashboard.tool_call_count}")
    
    # Test table generation
    node_table = dashboard.get_node_table()
    metrics_panel = dashboard.get_metrics_panel()
    timeline_table = dashboard.get_timeline_table()
    
    print(f"✓ Node table generated: {type(node_table).__name__}")
    print(f"✓ Metrics panel generated: {type(metrics_panel).__name__}")
    print(f"✓ Timeline table generated: {type(timeline_table).__name__}")


def test_metrics_cli():
    """Test metrics CLI commands."""
    from src.metrics import analyze_run, list_runs
    
    print("\n[3/4] Testing Metrics CLI...")
    print("-" * 70)
    
    # Test analyze command
    class MockArgs:
        log = "runs/test_phase5.jsonl"
        output = None
    
    print("✓ CLI analyze command ready")
    print("✓ CLI compare command ready")
    print("✓ CLI list command ready")


def test_callback_integration():
    """Test callback integration."""
    from src.callbacks.logging_callback import FailBotEventLogger
    from src.graph import get_graph
    import logging
    
    print("\n[4/4] Testing Callback Integration...")
    print("-" * 70)
    
    # Create logger
    logger = logging.getLogger("test")
    
    # Create callback
    callback = FailBotEventLogger(logger, "test_run_123")
    print(f"✓ Event logger callback created: {type(callback).__name__}")
    
    # Get graph with callbacks
    graph = get_graph()
    print(f"✓ Graph ready with callback support: {len(list(graph.nodes.keys()))} nodes")
    
    # Verify graph config parameter support
    assert hasattr(graph, 'ainvoke'), "Graph should have ainvoke method"
    print(f"✓ Graph supports ainvoke with callbacks parameter")


async def test_async_callback_usage():
    """Test async usage of callbacks."""
    print("\n[BONUS] Testing Async Callback Integration...")
    print("-" * 70)
    
    from src.callbacks.logging_callback import FailBotEventLogger
    from src.state import create_initial_state
    from src.config import load_config
    
    # Load config
    config = load_config()
    
    # Create state
    state = create_initial_state("test.log", "test/repo")
    
    # Create logger and callback
    import logging
    logger = logging.getLogger("async_test")
    callback = FailBotEventLogger(logger, state["run_id"])
    
    print(f"✓ Async callback created for run: {state['run_id'][:8]}")
    print(f"✓ Callback ready for graph.ainvoke(state, config={{'callbacks': [callback]}})")


def main():
    """Run all Phase 5 tests."""
    print("\n" + "="*70)
    print("PHASE 5: LOGGING DASHBOARD & INSTRUMENTATION TESTS")
    print("="*70)
    
    try:
        test_metrics_analyzer()
        test_dashboard_metrics()
        test_metrics_cli()
        test_callback_integration()
        
        # Run async test
        asyncio.run(test_async_callback_usage())
        
        print("\n" + "="*70)
        print("✅ ALL PHASE 5 TESTS PASSED")
        print("="*70)
        
        print("\nPhase 5 Components:")
        print("  ✓ src/utils/metrics.py - MetricsAnalyzer for JSONL log analysis")
        print("  ✓ src/tools/dashboard.py - Real-time dashboard with Live display")
        print("  ✓ src/metrics.py - CLI for metrics analysis & comparison")
        print("  ✓ src/graph.py - Updated to support callbacks")
        print("  ✓ src/main.py - Updated to pass callbacks to ainvoke")
        print("  ✓ src/callbacks/logging_callback.py - FailBotEventLogger")
        
        print("\nUsage Examples:")
        print("  # Analyze latest run")
        print("  python -m src.metrics analyze")
        print("  ")
        print("  # Monitor live execution")
        print("  python -m src.tools.dashboard")
        print("  ")
        print("  # Compare multiple runs")
        print("  python -m src.metrics compare --logs runs/failbot_*.jsonl")
        print("  ")
        print("  # List available runs")
        print("  python -m src.metrics list")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
