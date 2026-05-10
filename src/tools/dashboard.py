#!/usr/bin/env python
"""
FailBot Execution Dashboard

Real-time visualization of FailBot pipeline execution.
Tails JSONL logs and displays metrics with Rich formatting.
"""

import json
import time
import asyncio
from pathlib import Path
from typing import Dict, List, Optional
from collections import defaultdict
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.live import Live
from rich.layout import Layout


class DashboardMetrics:
    """Track and display execution metrics in real-time."""
    
    def __init__(self):
        """Initialize metrics tracker."""
        self.events: List[Dict] = []
        self.node_status: Dict[str, str] = {}
        self.node_times: Dict[str, float] = {}
        self.token_counts: Dict[str, int] = defaultdict(int)
        self.error_count = 0
        self.llm_call_count = 0
        self.tool_call_count = 0
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
    
    def add_event(self, event: Dict) -> None:
        """
        Add a new event to metrics.
        
        Args:
            event: Event dictionary from JSONL log
        """
        self.events.append(event)
        event_type = event.get("event_type", "")
        node = event.get("node", "unknown")
        
        # Track start time
        if not self.start_time and event_type == "node_start":
            self.start_time = time.time()
        
        # Update node status
        if event_type == "node_start":
            self.node_status[node] = "🔄 running"
        elif event_type == "node_end":
            self.node_status[node] = "✅ done"
            self.end_time = time.time()
        elif event_type == "error":
            self.node_status[node] = "❌ error"
            self.error_count += 1
        
        # Track timings
        if event_type == "node_end" and "duration_ms" in event:
            self.node_times[node] = event["duration_ms"]
        
        # Track tokens
        if event_type == "node_end":
            data = event.get("data", {})
            if "token_counts" in data:
                token_data = data["token_counts"]
                for key, value in token_data.items():
                    self.token_counts[key] += value
        
        # Track LLM calls
        if event_type == "llm_start":
            self.llm_call_count += 1
        
        # Track tool calls
        if event_type == "tool_start":
            self.tool_call_count += 1
    
    def get_node_table(self) -> Table:
        """Get Rich Table of node statuses."""
        table = Table(title="Node Execution", show_header=True, header_style="bold cyan")
        table.add_column("Node", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Time (ms)", justify="right")
        
        for node in [
            "ingest",
            "parse_log",
            "triage",
            "suggest_test",
            "suggest_test_generic",
            "file_issue",
            "report",
        ]:
            status = self.node_status.get(node, "⏳ pending")
            time_ms = self.node_times.get(node, 0)
            time_str = f"{time_ms:.0f}" if time_ms > 0 else "-"
            table.add_row(node, status, time_str)
        
        return table
    
    def get_metrics_panel(self) -> Panel:
        """Get Rich Panel with metrics."""
        total_time_ms = 0
        if self.start_time and self.end_time:
            total_time_ms = (self.end_time - self.start_time) * 1000
        
        total_tokens = sum(self.token_counts.values())
        
        metrics_text = (
            f"[cyan]Total Events:[/cyan] {len(self.events)}\n"
            f"[cyan]LLM Calls:[/cyan] {self.llm_call_count}\n"
            f"[cyan]Tool Calls:[/cyan] {self.tool_call_count}\n"
            f"[cyan]Errors:[/cyan] {self.error_count}\n"
            f"\n"
            f"[cyan]Total Tokens:[/cyan] {total_tokens}\n"
            f"[cyan]Execution Time:[/cyan] {total_time_ms:.0f} ms"
        )
        
        return Panel(metrics_text, title="Metrics", border_style="blue")
    
    def get_timeline_table(self) -> Table:
        """Get Rich Table of recent events."""
        table = Table(title="Event Timeline (Last 10)", show_header=True, header_style="bold cyan")
        table.add_column("Timestamp", style="cyan")
        table.add_column("Node", style="magenta")
        table.add_column("Event Type", style="yellow")
        table.add_column("Details", style="white")
        
        for event in self.events[-10:]:
            timestamp = event.get("timestamp", "")[-8:]  # Last 8 chars (HH:MM:SS)
            node = event.get("node", "?")
            event_type = event.get("event_type", "?")
            
            details = ""
            data = event.get("data", {})
            
            if event_type == "node_end" and "duration_ms" in event:
                details = f"{event['duration_ms']:.0f}ms"
            elif event_type == "llm_end":
                details = f"tokens: {data.get('total_tokens', 0)}"
            elif event_type == "error":
                details = data.get("error_type", "?")
            
            table.add_row(timestamp, node, event_type, details)
        
        return table


async def tail_log_file(log_file: Path, on_event_callback) -> None:
    """
    Tail a JSONL log file and process new events.
    
    Args:
        log_file: Path to JSONL log file
        on_event_callback: Callback function for each new event
    """
    if not log_file.exists():
        print(f"Log file not found: {log_file}")
        return
    
    file_position = 0
    
    while True:
        try:
            # Check if file is still being written to
            if not log_file.exists():
                await asyncio.sleep(0.5)
                continue
            
            with open(log_file, 'r') as f:
                f.seek(file_position)
                
                for line in f:
                    try:
                        event = json.loads(line.strip())
                        on_event_callback(event)
                    except json.JSONDecodeError:
                        continue
                
                file_position = f.tell()
            
            # Check every 500ms for new events
            await asyncio.sleep(0.5)
        
        except Exception as e:
            print(f"Error tailing log: {e}")
            await asyncio.sleep(1.0)


async def dashboard_main(log_file: Optional[str] = None) -> None:
    """
    Main dashboard loop.
    
    Args:
        log_file: Path to JSONL log file (or auto-detect latest)
    """
    console = Console()
    
    # Find log file
    if log_file is None:
        runs_path = Path("runs")
        if not runs_path.exists():
            console.print("[red]Error: runs/ directory not found[/red]")
            return
        
        log_files = sorted(runs_path.glob("failbot_*.jsonl"), reverse=True)
        if not log_files:
            console.print("[red]Error: No log files found in runs/[/red]")
            return
        
        log_file = str(log_files[0])
    
    log_path = Path(log_file)
    console.print(f"[cyan]Monitoring: {log_path.name}[/cyan]")
    
    metrics = DashboardMetrics()
    
    def on_event(event: Dict) -> None:
        """Callback when new event is received."""
        metrics.add_event(event)
    
    # Create layout
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=3),
    )
    
    layout["header"].update(
        Panel(
            "[bold cyan]FailBot Execution Dashboard[/bold cyan]",
            border_style="cyan"
        )
    )
    
    layout["footer"].update(
        Panel(
            "[dim]Press Ctrl+C to exit • Updates every 500ms[/dim]",
            border_style="dim"
        )
    )
    
    # Start tailing log file
    tail_task = asyncio.create_task(tail_log_file(log_path, on_event))
    
    try:
        # Update dashboard every 500ms
        with Live(layout, refresh_per_second=2, screen=True) as live:
            while not tail_task.done():
                try:
                    # Update body layout
                    body_layout = Layout()
                    body_layout.split_row(
                        Layout(metrics.get_node_table()),
                        Layout(
                            Layout(metrics.get_metrics_panel(), size=8),
                            Layout(metrics.get_timeline_table()),
                        )
                    )
                    
                    layout["body"].update(body_layout)
                    
                    await asyncio.sleep(0.5)
                except Exception as e:
                    console.print(f"[red]Dashboard error: {e}[/red]")
                    break
    
    except KeyboardInterrupt:
        console.print("\n[yellow]Dashboard stopped[/yellow]")
    finally:
        tail_task.cancel()


def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="FailBot Execution Dashboard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Monitor latest run
  python -m src.tools.dashboard
  
  # Monitor specific run
  python -m src.tools.dashboard --log runs/failbot_20260510_143022.jsonl
        """
    )
    
    parser.add_argument(
        "--log",
        help="Path to specific JSONL log file (auto-detects latest if omitted)"
    )
    
    args = parser.parse_args()
    
    # Run async dashboard
    asyncio.run(dashboard_main(args.log))


if __name__ == "__main__":
    main()
