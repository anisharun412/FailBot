"""
FailBot LangGraph StateGraph

Builds the multi-agent pipeline using LangGraph.
"""

from typing import Optional, List
import logging
from langgraph.graph import StateGraph, START, END
from langchain_core.callbacks.base import BaseCallbackHandler

from src.nodes import (
    file_issue_node,
    ingest_node,
    parse_log_node,
    report_node,
    suggest_test_generic_node,
    suggest_test_node,
    triage_node,
)
from src.state import FailBotState
from src.utils.graph_utils import route_after_triage
from src.callbacks.logging_callback import FailBotEventLogger


def build_failbot_graph(callbacks: Optional[List[BaseCallbackHandler]] = None):
    """
    Build the FailBot LangGraph StateGraph.
    
    Args:
        callbacks: Optional list of callback handlers for event logging
    
    Returns:
        Compiled CompiledStateGraph
    """
    builder = StateGraph(FailBotState)
    
    # Add nodes
    builder.add_node("ingest", ingest_node)
    builder.add_node("parse_log", parse_log_node)
    builder.add_node("triage", triage_node)
    builder.add_node("suggest_test", suggest_test_node)
    builder.add_node("suggest_test_generic", suggest_test_generic_node)
    builder.add_node("file_issue", file_issue_node)
    builder.add_node("report", report_node)
    
    # Add edges
    builder.add_edge(START, "ingest")
    builder.add_edge("ingest", "parse_log")
    builder.add_edge("parse_log", "triage")
    
    # Conditional edge after triage
    builder.add_conditional_edges(
        "triage",
        route_after_triage,
        {
            "suggest_test": "suggest_test",
            "suggest_test_generic": "suggest_test_generic",
            "file_issue": "file_issue",
        }
    )
    
    # Converge test branches to file_issue
    builder.add_edge("suggest_test", "file_issue")
    builder.add_edge("suggest_test_generic", "file_issue")
    
    # End edges
    builder.add_edge("file_issue", "report")
    builder.add_edge("report", END)
    
    # Compile with optional callbacks
    if callbacks:
        graph = builder.compile()
        # Note: In LangGraph 0.0.20+, callbacks are passed to ainvoke/invoke,
        # not during compilation. This is a placeholder for future callback attachment.
    else:
        graph = builder.compile()
    
    return graph


# Global graph instance
_graph_instance = None


def get_graph(callbacks: Optional[List[BaseCallbackHandler]] = None):
    """
    Get or create the compiled graph.
    
    Args:
        callbacks: Optional list of callback handlers
    
    Returns:
        CompiledStateGraph
    """
    global _graph_instance
    
    if _graph_instance is None:
        _graph_instance = build_failbot_graph(callbacks=callbacks)
    
    return _graph_instance


if __name__ == "__main__":
    # Test graph building
    graph = get_graph()
    print(f"✓ Graph built successfully")
    print(f"✓ Nodes: {list(graph.nodes.keys())}")
    print(f"✓ Graph ready for execution")
