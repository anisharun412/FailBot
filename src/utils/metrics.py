"""
Metrics Analysis for FailBot Execution

Aggregates and analyzes execution metrics from JSONL logs.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import defaultdict
from datetime import datetime


class MetricsAnalyzer:
    """Analyze FailBot execution metrics from JSONL logs."""
    
    def __init__(self, log_file: Path):
        """
        Initialize metrics analyzer.
        
        Args:
            log_file: Path to JSONL log file
        """
        self.log_file = Path(log_file)
        self.events: List[Dict[str, Any]] = []
        self.metrics: Dict[str, Any] = {}
    
    def load_events(self) -> None:
        """Load all events from JSONL log file."""
        if not self.log_file.exists():
            raise FileNotFoundError(f"Log file not found: {self.log_file}")
        
        self.events = []
        with open(self.log_file, 'r') as f:
            for line in f:
                try:
                    event = json.loads(line.strip())
                    self.events.append(event)
                except json.JSONDecodeError:
                    continue
    
    def analyze(self) -> Dict[str, Any]:
        """
        Analyze all metrics from loaded events.
        
        Returns:
            Dictionary with aggregated metrics
        """
        self.load_events()
        
        metrics = {
            "total_events": len(self.events),
            "node_timing": self._analyze_node_timing(),
            "token_usage": self._analyze_token_usage(),
            "errors": self._analyze_errors(),
            "llm_calls": self._analyze_llm_calls(),
            "tool_calls": self._analyze_tool_calls(),
            "timeline": self._build_timeline(),
        }
        
        self.metrics = metrics
        return metrics
    
    def _analyze_node_timing(self) -> Dict[str, Any]:
        """Analyze timing for each node."""
        node_times = defaultdict(list)
        
        for event in self.events:
            node = event.get("node", "unknown")
            event_type = event.get("event_type", "")
            duration = event.get("duration_ms", 0)
            
            if event_type in ["node_end", "node_error"] and duration:
                node_times[node].append(duration)
        
        timing = {}
        for node, times in node_times.items():
            if times:
                timing[node] = {
                    "count": len(times),
                    "min_ms": min(times),
                    "max_ms": max(times),
                    "avg_ms": sum(times) / len(times),
                    "total_ms": sum(times),
                }
        
        return timing
    
    def _analyze_token_usage(self) -> Dict[str, Any]:
        """Analyze token usage across all nodes."""
        node_tokens = defaultdict(lambda: {"input": 0, "output": 0, "total": 0})
        
        for event in self.events:
            if event.get("event_type") == "node_end":
                node = event.get("node", "unknown")
                data = event.get("data", {})
                
                # Extract token counts from state
                if "token_counts" in data:
                    token_data = data["token_counts"]
                    for key, value in token_data.items():
                        if "_input" in key or "_output" in key:
                            if "_input" in key:
                                node_tokens[node]["input"] += value
                            else:
                                node_tokens[node]["output"] += value
                            node_tokens[node]["total"] += value
        
        # Also check for LLM call tokens
        for event in self.events:
            if event.get("event_type") == "llm_end":
                node = event.get("node", "unknown")
                data = event.get("data", {})
                
                input_tokens = data.get("input_tokens", 0)
                output_tokens = data.get("output_tokens", 0)
                
                node_tokens[node]["input"] += input_tokens
                node_tokens[node]["output"] += output_tokens
                node_tokens[node]["total"] += input_tokens + output_tokens
        
        return dict(node_tokens)
    
    def _analyze_errors(self) -> Dict[str, Any]:
        """Analyze errors and failures."""
        errors = {
            "total": 0,
            "by_node": defaultdict(int),
            "by_type": defaultdict(int),
            "messages": [],
        }
        
        for event in self.events:
            if event.get("event_type") in ["error", "node_error", "llm_error"]:
                errors["total"] += 1
                
                node = event.get("node", "unknown")
                errors["by_node"][node] += 1
                
                error_data = event.get("data", {})
                error_type = error_data.get("error_type", "unknown")
                errors["by_type"][error_type] += 1
                
                error_msg = error_data.get("error_message", "")
                if error_msg:
                    errors["messages"].append({
                        "node": node,
                        "type": error_type,
                        "message": error_msg[:200],
                        "timestamp": event.get("timestamp", ""),
                    })
        
        return {
            "total": errors["total"],
            "by_node": dict(errors["by_node"]),
            "by_type": dict(errors["by_type"]),
            "messages": errors["messages"][:10],  # Keep last 10
        }
    
    def _analyze_llm_calls(self) -> Dict[str, Any]:
        """Analyze LLM usage patterns."""
        llm_stats = {
            "total_calls": 0,
            "by_node": defaultdict(int),
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "avg_response_time_ms": 0,
            "models_used": set(),
        }
        
        response_times = []
        
        for event in self.events:
            if event.get("event_type") == "llm_start":
                llm_stats["total_calls"] += 1
                node = event.get("node", "unknown")
                llm_stats["by_node"][node] += 1
                
                model = event.get("data", {}).get("model", "")
                if model:
                    llm_stats["models_used"].add(model)
            
            elif event.get("event_type") == "llm_end":
                data = event.get("data", {})
                llm_stats["total_input_tokens"] += data.get("input_tokens", 0)
                llm_stats["total_output_tokens"] += data.get("output_tokens", 0)
                
                duration = event.get("duration_ms", 0)
                if duration:
                    response_times.append(duration)
        
        if response_times:
            llm_stats["avg_response_time_ms"] = sum(response_times) / len(response_times)
        
        return {
            "total_calls": llm_stats["total_calls"],
            "by_node": dict(llm_stats["by_node"]),
            "total_input_tokens": llm_stats["total_input_tokens"],
            "total_output_tokens": llm_stats["total_output_tokens"],
            "total_tokens": llm_stats["total_input_tokens"] + llm_stats["total_output_tokens"],
            "avg_response_time_ms": round(llm_stats["avg_response_time_ms"], 2),
            "models_used": list(llm_stats["models_used"]),
        }
    
    def _analyze_tool_calls(self) -> Dict[str, Any]:
        """Analyze tool usage patterns."""
        tool_stats = {
            "total_calls": 0,
            "by_tool": defaultdict(int),
            "by_node": defaultdict(int),
            "success_count": 0,
            "failure_count": 0,
            "avg_response_time_ms": 0,
        }
        
        response_times = []
        
        for event in self.events:
            if event.get("event_type") == "tool_start":
                tool_stats["total_calls"] += 1
                
                node = event.get("node", "unknown")
                tool_stats["by_node"][node] += 1
                
                tool_name = event.get("data", {}).get("tool_name", "unknown")
                tool_stats["by_tool"][tool_name] += 1
            
            elif event.get("event_type") == "tool_end":
                data = event.get("data", {})
                if data.get("success"):
                    tool_stats["success_count"] += 1
                else:
                    tool_stats["failure_count"] += 1
                
                duration = event.get("duration_ms", 0)
                if duration:
                    response_times.append(duration)
        
        if response_times:
            tool_stats["avg_response_time_ms"] = round(sum(response_times) / len(response_times), 2)
        
        return {
            "total_calls": tool_stats["total_calls"],
            "by_tool": dict(tool_stats["by_tool"]),
            "by_node": dict(tool_stats["by_node"]),
            "success_count": tool_stats["success_count"],
            "failure_count": tool_stats["failure_count"],
            "success_rate": round(tool_stats["success_count"] / max(tool_stats["total_calls"], 1), 2),
            "avg_response_time_ms": tool_stats["avg_response_time_ms"],
        }
    
    def _build_timeline(self) -> List[Dict[str, Any]]:
        """Build execution timeline."""
        timeline = []
        
        for event in self.events:
            if event.get("event_type") in ["node_start", "node_end", "error"]:
                timeline.append({
                    "timestamp": event.get("timestamp", ""),
                    "node": event.get("node", "unknown"),
                    "event_type": event.get("event_type", ""),
                    "duration_ms": event.get("duration_ms", 0),
                    "status": "success" if event.get("event_type") == "node_end" else "error",
                })
        
        return timeline
    
    def print_summary(self) -> None:
        """Print a human-readable summary of metrics."""
        if not self.metrics:
            self.analyze()
        
        print("\n" + "="*70)
        print("FAILBOT EXECUTION METRICS")
        print("="*70)
        
        print(f"\nTotal Events: {self.metrics['total_events']}")
        
        # Node timing
        print("\nNode Timing (ms):")
        print("-" * 70)
        for node, timing in sorted(self.metrics["node_timing"].items()):
            print(f"  {node:20s} | avg: {timing['avg_ms']:8.1f} | "
                  f"min: {timing['min_ms']:8.1f} | max: {timing['max_ms']:8.1f} | "
                  f"count: {timing['count']}")
        
        # Token usage
        print("\nToken Usage:")
        print("-" * 70)
        total_tokens = 0
        for node, tokens in sorted(self.metrics["token_usage"].items()):
            total_tokens += tokens["total"]
            print(f"  {node:20s} | in: {tokens['input']:6d} | "
                  f"out: {tokens['output']:6d} | total: {tokens['total']:6d}")
        print(f"  {'TOTAL':20s} | tokens: {total_tokens}")
        
        # LLM calls
        llm = self.metrics["llm_calls"]
        print("\nLLM Calls:")
        print("-" * 70)
        print(f"  Total Calls: {llm['total_calls']}")
        print(f"  Models Used: {', '.join(llm['models_used'])}")
        print(f"  Input Tokens: {llm['total_input_tokens']}")
        print(f"  Output Tokens: {llm['total_output_tokens']}")
        print(f"  Total Tokens: {llm['total_tokens']}")
        print(f"  Avg Response Time: {llm['avg_response_time_ms']:.1f} ms")
        
        # Tool calls
        tools = self.metrics["tool_calls"]
        print("\nTool Calls:")
        print("-" * 70)
        print(f"  Total Calls: {tools['total_calls']}")
        print(f"  Success Rate: {tools['success_rate']:.0%}")
        print(f"  Avg Response Time: {tools['avg_response_time_ms']:.1f} ms")
        
        # Errors
        errors = self.metrics["errors"]
        print("\nErrors:")
        print("-" * 70)
        print(f"  Total: {errors['total']}")
        if errors["total"] > 0:
            print(f"  By Node: {errors['by_node']}")
            print(f"  By Type: {errors['by_type']}")
        
        print("\n" + "="*70)


def analyze_latest_run(runs_dir: str = "runs") -> Optional[MetricsAnalyzer]:
    """
    Analyze the most recent run's metrics.
    
    Args:
        runs_dir: Directory containing run logs
    
    Returns:
        MetricsAnalyzer with loaded metrics, or None if no logs found
    """
    runs_path = Path(runs_dir)
    
    if not runs_path.exists():
        print(f"Runs directory not found: {runs_dir}")
        return None
    
    # Find latest JSONL log
    log_files = sorted(runs_path.glob("failbot_*.jsonl"), reverse=True)
    
    if not log_files:
        print(f"No log files found in {runs_dir}")
        return None
    
    latest_log = log_files[0]
    print(f"Analyzing: {latest_log.name}")
    
    analyzer = MetricsAnalyzer(latest_log)
    analyzer.analyze()
    return analyzer
