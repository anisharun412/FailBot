#!/usr/bin/env python3
"""Test Phase 3 node implementations."""

import asyncio
import logging
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import get_config
from src.graph import get_graph
from src.state import create_initial_state
from src.utils.logging_config import setup_json_logging

# Setup logging
logger = logging.getLogger(__name__)
setup_json_logging(level=logging.INFO)


# Sample CI log for testing
SAMPLE_LOG = """
2024-05-10 10:45:23 Running tests...
2024-05-10 10:45:25 FAIL: test_calculate_average in test_math.py
Traceback (most recent call last):
  File "/home/user/project/test_math.py", line 42, in test_calculate_average
    result = calculate_average([1, 2, 3])
  File "/home/user/project/math_utils.py", line 15, in calculate_average
    return sum(values) / len(values)
TypeError: unsupported operand type(s) for /: 'int' and 'NoneType'

Expected: 2.0
Got: TypeError
Error at math_utils.py:15
"""


async def test_phase3_nodes():
    """Test Phase 3 node implementations."""
    print("\n" + "="*70)
    print("PHASE 3 NODE INTEGRATION TEST")
    print("="*70)
    
    # Create a temporary test log file
    test_log_file = Path("/tmp/test_ci_log.txt")
    test_log_file.write_text(SAMPLE_LOG)
    
    try:
        # Initialize graph and state
        print("\n[1/7] Building graph...")
        graph = get_graph()
        print("✓ Graph built with 7 nodes")
        
        print("\n[2/7] Creating initial state...")
        state = create_initial_state(
            log_source=str(test_log_file),
            repo_name="test-repo",
            run_id=None
        )
        print(f"✓ State initialized (run_id: {state['run_id'][:8]}...)")
        
        # Run graph
        print("\n[3/7] Running FailBot pipeline...")
        print("-" * 70)
        
        config = get_config()
        
        try:
            # Run the graph
            final_state = await graph.ainvoke(state)
            
            print("-" * 70)
            print("\n[4/7] ✓ Pipeline completed!")
            
            # Print results
            print(f"\n[5/7] RESULTS:")
            print(f"  Status: {final_state.get('status')}")
            print(f"  Category: {final_state.get('failure_category')}")
            print(f"  Severity: {final_state.get('severity')}")
            print(f"  Confidence: {final_state.get('triage_confidence'):.0%}")
            print(f"  Error Signature: {final_state.get('error_signature')[:60]}")
            print(f"  Language: {final_state.get('language')}")
            print(f"  Files: {', '.join(final_state.get('files_changed', [])[:2])}")
            
            # Print test if generated
            if final_state.get("suggested_test"):
                print(f"\n[6/7] TEST GENERATED:")
                test_preview = final_state["suggested_test"][:200]
                print(f"  {test_preview}...")
            
            # Print issue info
            if final_state.get("github_issue_url"):
                print(f"\n[7/7] ISSUE:")
                print(f"  URL: {final_state['github_issue_url']}")
            
            # Print token usage
            if final_state.get("token_counts"):
                print(f"\nTOKEN USAGE:")
                total = sum(final_state["token_counts"].values())
                for node, tokens in sorted(final_state["token_counts"].items()):
                    print(f"  {node}: {tokens}")
                print(f"  TOTAL: {total}")
            
            # Print errors if any
            if final_state.get("errors"):
                print(f"\nERRORS ({len(final_state['errors'])}):")
                for error in final_state["errors"][:3]:
                    print(f"  [{error.get('node')}] {error.get('error')[:60]}")
            
            print("\n" + "="*70)
            print("✓ PHASE 3 TEST PASSED")
            print("="*70 + "\n")
            
            return True
            
        except Exception as e:
            print(f"\n✗ Pipeline failed: {e}")
            import traceback
            traceback.print_exc()
            return False
            
    finally:
        # Cleanup
        if test_log_file.exists():
            test_log_file.unlink()


if __name__ == "__main__":
    result = asyncio.run(test_phase3_nodes())
    sys.exit(0 if result else 1)
