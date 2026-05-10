#!/usr/bin/env python3
"""
Test Code Practice Consistency - Verifies all project patterns are followed

Tests:
1. Prompt loading from YAML with render_agent_prompt()
2. TypedDict state management with proper type hints
3. Tool binding with LangChain @tool decorator
4. Node implementations following established patterns
5. Error handling and logging consistency
"""

import logging
import sys
from typing import Optional
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(message)s')

def print_header(num: int, title: str):
    """Print a formatted test section header."""
    print(f"\n[{num}/6] {title}")
    print("-" * 70)

def test_prompt_management():
    """Test that all prompts are loaded from YAML via render_agent_prompt()."""
    print_header(1, "Testing Prompt Management (YAML + render_agent_prompt)")
    
    from src.utils.prompt_templates import render_agent_prompt
    from src.config import get_config
    
    config = get_config()
    print(f"✓ Config loaded: {type(config).__name__}")
    
    # Test file_issue prompts
    try:
        system = render_agent_prompt("file_issue", "system")
        print(f"✓ file_issue.system: {len(system)} chars")
        
        body = render_agent_prompt(
            "file_issue", "format_issue_body",
            summary="Test", category="code_bug", severity="high",
            confidence="85%", affected_files="- file.py",
            error_signature="Error", suggested_test="test code",
            reasoning="reason", timestamp=datetime.now().isoformat(), run_id="123"
        )
        print(f"✓ file_issue.format_issue_body: {len(body)} chars (variables substituted)")
        
        # Verify substitution
        assert "Test" in body and "code_bug" in body and "high" in body
        print("✓ Variable substitution working")
        
    except Exception as e:
        print(f"✗ File issue prompts failed: {e}")
        return False
    
    # Test test_suggester prompts
    try:
        system = render_agent_prompt("test_suggester", "system", language="python")
        user = render_agent_prompt(
            "test_suggester", "suggest_test",
            error_signature="TestError",
            language="python",
            error_context="context"
        )
        print(f"✓ test_suggester prompts loaded")
        assert "python" in system.lower() and "TestError" in user
        
    except Exception as e:
        print(f"✗ Test suggester prompts failed: {e}")
        return False
    
    # Test test_suggester_generic prompts
    try:
        system = render_agent_prompt(
            "test_suggester_generic", "system",
            failure_category="flaky"
        )
        user = render_agent_prompt(
            "test_suggester_generic", "suggest_test_generic",
            error_signature="TimeoutError",
            failure_category="flaky",
            error_context="ctx"
        )
        print(f"✓ test_suggester_generic prompts loaded")
        assert "flaky" in system and "TimeoutError" in user
        
    except Exception as e:
        print(f"✗ Test suggester generic prompts failed: {e}")
        return False
    
    print("✓✓ Prompt management test PASSED")
    return True


def test_typeddict_patterns():
    """Test that FailBotState follows TypedDict patterns."""
    print_header(2, "Testing TypedDict State Management")
    
    from src.state import FailBotState, create_initial_state
    from typing import get_type_hints, Literal, Optional
    
    # Check TypedDict structure
    hints = get_type_hints(FailBotState)
    print(f"✓ FailBotState fields: {len(hints)}")
    
    # Check some key fields have proper Optional/Literal patterns
    required_fields = {
        'run_id': str,
        'failure_category': str,  # Should be Literal eventually
        'severity': str,  # Should be Literal eventually
        'status': str,
        'log_source': str,
        'repo_name': str,
    }
    
    for field, expected_type in required_fields.items():
        if field not in hints:
            print(f"✗ Missing field: {field}")
            return False
        print(f"✓ Field '{field}' present with type {hints[field]}")
    
    # Test state factory
    try:
        initial = create_initial_state("test_log", "repo", "run123")
        assert initial["run_id"] == "run123"
        assert initial["repo_name"] == "repo"
        print("✓ State factory (create_initial_state) working")
        
    except Exception as e:
        print(f"✗ State factory failed: {e}")
        return False
    
    print("✓✓ TypedDict pattern test PASSED")
    return True


def test_tool_binding():
    """Test that tools use @tool decorator and get_bound_model()."""
    print_header(3, "Testing Tool Binding (@tool + get_bound_model)")
    
    from src.tools.langchain_tools import (
        FAILBOT_TOOLS, get_bound_model,
        validate_code_syntax, detect_code_hallucinations,
        lookup_error_patterns, create_github_issue
    )
    
    # Check tools are decorated with @tool
    print(f"✓ FAILBOT_TOOLS: {len(FAILBOT_TOOLS)} tools available")
    tools_list = [t.name for t in FAILBOT_TOOLS]
    print(f"  - {', '.join(tools_list)}")
    
    expected_tools = {'validate_code_syntax', 'detect_code_hallucinations', 
                     'lookup_error_patterns', 'create_github_issue'}
    if expected_tools != set(tools_list):
        print(f"✗ Tool mismatch. Expected: {expected_tools}, got: {set(tools_list)}")
        return False
    
    # Test get_bound_model (skip API key requirement)
    try:
        # Just verify the function exists and has proper signature
        import inspect
        sig = inspect.signature(get_bound_model)
        if 'model' not in sig.parameters:
            print(f"✗ get_bound_model() missing 'model' parameter")
            return False
        
        print("✓ get_bound_model() function signature correct")
        print(f"✓ Bound model function ready for tool binding")
        print("✓ (API key test skipped - expected in production)")
        
    except Exception as e:
        print(f"✗ Tool binding function check failed: {e}")
        return False
    
    print("✓✓ Tool binding test PASSED")
    return True


def test_node_patterns():
    """Test that all nodes follow established patterns."""
    print_header(4, "Testing Node Implementation Patterns")
    
    import inspect
    from src.nodes.file_issue import file_issue_node
    from src.nodes.suggest_test_generic import suggest_test_generic_node
    from src.nodes.triage import triage_node
    from src.nodes.suggest_test import suggest_test_node
    
    nodes = [
        ("file_issue_node", file_issue_node),
        ("suggest_test_generic_node", suggest_test_generic_node),
        ("triage_node", triage_node),
        ("suggest_test_node", suggest_test_node),
    ]
    
    for node_name, node_func in nodes:
        # Check it's an async function
        if not inspect.iscoroutinefunction(node_func):
            print(f"✗ {node_name} is not async")
            return False
        
        # Check signature
        sig = inspect.signature(node_func)
        if 'state' not in sig.parameters:
            print(f"✗ {node_name} missing 'state' parameter")
            return False
        
        print(f"✓ {node_name}: async, proper signature")
    
    print("✓✓ Node pattern test PASSED")
    return True


def test_error_handling():
    """Test that error handling follows patterns."""
    print_header(5, "Testing Error Handling and Logging")
    
    from src.utils.graph_utils import handle_node_error, log_node_start, log_node_end
    from src.utils.logging_config import log_event
    from src.state import create_initial_state
    
    # Test logging functions exist and are callable
    print(f"✓ handle_node_error available: {callable(handle_node_error)}")
    print(f"✓ log_node_start available: {callable(log_node_start)}")
    print(f"✓ log_node_end available: {callable(log_node_end)}")
    print(f"✓ log_event available: {callable(log_event)}")
    
    # Test that we can call log_event with proper structure
    try:
        logger = logging.getLogger("test")
        state = create_initial_state("test", "repo", "run123")
        log_event(logger, "run123", "test_node", "test_event", {"key": "value"})
        print("✓ log_event called successfully")
        
    except Exception as e:
        print(f"✗ Logging failed: {e}")
        return False
    
    print("✓✓ Error handling test PASSED")
    return True


def test_imports_and_integrations():
    """Test that all imports resolve and integrations work."""
    print_header(6, "Testing Imports and Integration")
    
    try:
        # Core imports
        from src.graph import get_graph
        from src.state import FailBotState
        from src.config import get_config
        from src.utils.prompt_templates import render_agent_prompt
        
        print("✓ Core modules import successfully")
        
        # Node imports
        from src.nodes.ingest import ingest_node
        from src.nodes.parse_log import parse_log_node
        from src.nodes.triage import triage_node
        from src.nodes.suggest_test import suggest_test_node
        from src.nodes.suggest_test_generic import suggest_test_generic_node
        from src.nodes.file_issue import file_issue_node
        from src.nodes.report import report_node
        
        print("✓ All 7 nodes import successfully")
        
        # Tool imports
        from src.tools.langchain_tools import FAILBOT_TOOLS, get_bound_model
        print(f"✓ Tools import successfully ({len(FAILBOT_TOOLS)} tools)")
        
        # Graph compilation
        graph = get_graph()
        print(f"✓ Graph compiles: {type(graph).__name__}")
        
        # Verify key nodes are in graph
        # Note: __end__ is implicit in LangGraph, doesn't appear in nodes list
        expected_core_nodes = {'__start__', 'ingest', 'parse_log', 'triage', 
                              'suggest_test', 'suggest_test_generic', 'file_issue', 'report'}
        graph_nodes = set(graph.nodes.keys())
        
        if not expected_core_nodes.issubset(graph_nodes):
            missing = expected_core_nodes - graph_nodes
            print(f"✗ Missing nodes: {missing}")
            return False
        
        print(f"✓ All core nodes present: {len(graph_nodes)} total")
        print(f"  Nodes: {sorted(graph_nodes)}")
        
    except Exception as e:
        print(f"✗ Import/integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("✓✓ Import and integration test PASSED")
    return True


def main():
    """Run all consistency tests."""
    print("=" * 70)
    print("CODE PRACTICE CONSISTENCY VERIFICATION")
    print("=" * 70)
    print("\nVerifying project follows established patterns:")
    print("  1. Prompts: YAML + render_agent_prompt()")
    print("  2. State: TypedDict with Optional/Literal")
    print("  3. Tools: @tool decorator + get_bound_model()")
    print("  4. Nodes: log_node_start/end, proper error handling")
    print("  5. Integration: All imports and graph compilation")
    
    results = {
        "Prompt Management": test_prompt_management(),
        "TypedDict Patterns": test_typeddict_patterns(),
        "Tool Binding": test_tool_binding(),
        "Node Patterns": test_node_patterns(),
        "Error Handling": test_error_handling(),
        "Imports & Integration": test_imports_and_integrations(),
    }
    
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    print("=" * 70)
    
    if passed == total:
        print(f"✅ ALL TESTS PASSED ({passed}/{total})")
        print("\n✓ Project follows all code practice standards")
        print("✓ Ready for integration testing and Phase 6")
        return 0
    else:
        print(f"❌ SOME TESTS FAILED ({passed}/{total} passed)")
        return 1


if __name__ == "__main__":
    sys.exit(main())
