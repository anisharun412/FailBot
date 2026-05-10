#!/usr/bin/env python
"""
FailBot Metrics CLI

Command-line tool for analyzing execution metrics from runs.
"""

import argparse
import sys
from pathlib import Path

from src.utils.metrics import MetricsAnalyzer, analyze_latest_run


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze FailBot execution metrics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze latest run
  python -m src.metrics analyze
  
  # Analyze specific run
  python -m src.metrics analyze --log runs/failbot_20260510_143022.jsonl
  
  # Compare multiple runs
  python -m src.metrics compare --logs runs/failbot_*.jsonl
  
  # Export metrics to JSON
  python -m src.metrics analyze --log runs/failbot_*.jsonl --output metrics.json
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Analyze command
    analyze_cmd = subparsers.add_parser("analyze", help="Analyze a single run")
    analyze_cmd.add_argument(
        "--log",
        help="Path to JSONL log file (uses latest if omitted)"
    )
    analyze_cmd.add_argument(
        "--output",
        help="Save metrics to JSON file"
    )
    
    # Compare command
    compare_cmd = subparsers.add_parser("compare", help="Compare multiple runs")
    compare_cmd.add_argument(
        "--logs",
        nargs="+",
        required=True,
        help="Paths to JSONL log files"
    )
    
    # List command
    list_cmd = subparsers.add_parser("list", help="List available runs")
    list_cmd.add_argument(
        "--runs-dir",
        default="runs",
        help="Directory containing run logs"
    )
    list_cmd.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of recent runs to show"
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    if args.command == "analyze":
        analyze_run(args)
    elif args.command == "compare":
        compare_runs(args)
    elif args.command == "list":
        list_runs(args)


def analyze_run(args) -> None:
    """Analyze a single run."""
    if args.log:
        log_file = Path(args.log)
        if not log_file.exists():
            print(f"Error: Log file not found: {args.log}")
            sys.exit(1)
    else:
        analyzer = analyze_latest_run()
        if not analyzer:
            sys.exit(1)
        
        if args.output:
            import json
            with open(args.output, 'w') as f:
                json.dump(analyzer.metrics, f, indent=2, default=str)
            print(f"✓ Metrics saved to {args.output}")
        else:
            analyzer.print_summary()
        return
    
    analyzer = MetricsAnalyzer(log_file)
    analyzer.analyze()
    
    if args.output:
        import json
        with open(args.output, 'w') as f:
            json.dump(analyzer.metrics, f, indent=2, default=str)
        print(f"✓ Metrics saved to {args.output}")
    else:
        analyzer.print_summary()


def compare_runs(args) -> None:
    """Compare metrics from multiple runs."""
    log_files = []
    for log_pattern in args.logs:
        log_files.extend(Path().glob(log_pattern))
    
    if not log_files:
        print("Error: No log files found")
        sys.exit(1)
    
    print(f"\n{'='*70}")
    print(f"COMPARING {len(log_files)} RUNS")
    print(f"{'='*70}\n")
    
    all_metrics = []
    for log_file in sorted(log_files):
        analyzer = MetricsAnalyzer(log_file)
        analyzer.analyze()
        all_metrics.append({
            "log_file": log_file.name,
            "metrics": analyzer.metrics
        })
    
    # Compare total tokens
    print("Total Token Usage:")
    print("-" * 70)
    for item in all_metrics:
        tokens = item["metrics"]["llm_calls"]["total_tokens"]
        print(f"  {item['log_file']:50s} | {tokens:6d} tokens")
    
    # Compare execution times
    print("\nExecution Times:")
    print("-" * 70)
    for item in all_metrics:
        timing = item["metrics"]["node_timing"]
        total_time = sum(t["total_ms"] for t in timing.values())
        print(f"  {item['log_file']:50s} | {total_time:8.0f} ms")
    
    # Compare error rates
    print("\nError Counts:")
    print("-" * 70)
    for item in all_metrics:
        errors = item["metrics"]["errors"]["total"]
        print(f"  {item['log_file']:50s} | {errors:3d} errors")
    
    print(f"\n{'='*70}")


def list_runs(args) -> None:
    """List available runs."""
    runs_dir = Path(args.runs_dir)
    
    if not runs_dir.exists():
        print(f"Error: Runs directory not found: {args.runs_dir}")
        sys.exit(1)
    
    log_files = sorted(runs_dir.glob("failbot_*.jsonl"), reverse=True)
    
    if not log_files:
        print(f"No log files found in {args.runs_dir}")
        return
    
    print(f"\n{'='*70}")
    print(f"RECENT RUNS ({len(log_files)} total)")
    print(f"{'='*70}\n")
    
    print(f"{'Filename':<50s} {'Size':>10s}  {'Date Modified':>20s}")
    print("-" * 70)
    
    for i, log_file in enumerate(log_files[:args.limit]):
        size = log_file.stat().st_size
        mtime = log_file.stat().st_mtime
        from datetime import datetime
        date_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        
        size_str = f"{size / 1024:.1f} KB"
        print(f"{log_file.name:<50s} {size_str:>10s}  {date_str:>20s}")
    
    if len(log_files) > args.limit:
        print(f"\n... and {len(log_files) - args.limit} more runs")
    
    print(f"\n{'='*70}")


if __name__ == "__main__":
    main()
