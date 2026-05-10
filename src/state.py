"""
FailBot State Definition

Defines the FailBotState TypedDict that flows through the LangGraph pipeline.
Each node updates this state with its outputs.
"""

from typing import TypedDict, List, Optional, Literal, Dict, Any
from datetime import datetime


class FailBotState(TypedDict):
    """
    Shared state for the FailBot multi-agent pipeline.
    
    This state is passed through all nodes in the LangGraph StateGraph.
    Each node reads from this state and updates it with its outputs.
    """
    
    # ========== INPUT FIELDS ==========
    log_source: str                    # Raw log text or URL
    repo_name: str                     # GitHub repo (e.g., "owner/repo")
    run_id: str                        # Unique run identifier (UUID)
    
    # ========== LOG PREPROCESSING (Ingest Node Output) ==========
    log_text_full: Optional[str]       # Raw log before truncation
    log_text: Optional[str]            # Truncated log for LLM input
    log_truncated_reason: Optional[str]  # Why truncated (e.g., "exceeded 8k tokens")
    raw_log_length: Optional[int]      # Character count of raw log
    
    # ========== TOKEN TRACKING ==========
    token_counts: Dict[str, Dict[str, int]]  # Per-node token usage
    # Example: {"parse_log": {"input": 3420, "output": 210}, ...}
    
    # ========== TIMESTAMPS ==========
    started_at: datetime               # Pipeline start time
    node_timestamps: Dict[str, float]  # Per-node execution times (ms)
    
    # ========== LOG PARSER AGENT OUTPUT ==========
    parsed_summary: Optional[str]      # Structured summary (JSON string)
    error_signature: Optional[str]     # Key error lines (3-5 lines)
    files_changed: Optional[List[str]] # Files mentioned in log
    
    # ========== TRIAGE AGENT OUTPUT ==========
    failure_category: Optional[Literal["flaky", "infra", "code_bug", "unknown"]]
    severity: Optional[Literal["low", "medium", "high", "critical"]]
    triage_confidence: Optional[float]  # 0.0-1.0
    
    # ========== TEST SUGGESTER AGENT OUTPUT ==========
    suggested_test: Optional[str]      # Generated test code or description
    test_language: Optional[str]       # e.g., "python", "javascript"
    test_validation_errors: Optional[List[str]]  # Syntax/validation errors
    
    # ========== ISSUE FILING OUTPUT ==========
    github_issue_url: Optional[str]    # URL of created GitHub issue
    github_issue_created_at: Optional[str]  # ISO8601 timestamp
    
    # ========== STATUS TRACKING ==========
    status: Literal["pending", "in_progress", "completed", "failed"]
    errors: List[str]                  # Accumulated error messages
    step_times: Dict[str, float]       # Latency per node (deprecated, use node_timestamps)
    
    # ========== FALLBACK PATHS ==========
    fallback_issue_path: Optional[str] # Local markdown file if GitHub fails
    skipped_nodes: List[str]           # Nodes skipped due to routing
    
    # ========== METADATA ==========
    execution_graph: Dict[str, Any]    # Graph execution trace (for debugging)


# Default state factory function
def create_initial_state(
    log_source: str, 
    repo_name: str, 
    run_id: Optional[str] = None
) -> FailBotState:
    """
    Create an initial FailBotState with all fields set to defaults.
    
    Args:
        log_source: Raw log text or URL to fetch
        repo_name: GitHub repository (owner/repo)
        run_id: Optional unique run identifier (UUID will be generated if None)
    
    Returns:
        Initialized FailBotState
    """
    import uuid
    
    return FailBotState(
        # Input
        log_source=log_source,
        repo_name=repo_name,
        run_id=run_id or str(uuid.uuid4()),
        
        # Log preprocessing
        log_text_full=None,
        log_text=None,
        log_truncated_reason=None,
        raw_log_length=None,
        
        # Token tracking
        token_counts={},
        
        # Timestamps
        started_at=datetime.now(),
        node_timestamps={},
        
        # Parser outputs
        parsed_summary=None,
        error_signature=None,
        files_changed=None,
        
        # Triage outputs
        failure_category=None,
        severity=None,
        triage_confidence=None,
        
        # Test outputs
        suggested_test=None,
        test_language=None,
        test_validation_errors=None,
        
        # Issue outputs
        github_issue_url=None,
        github_issue_created_at=None,
        
        # Status
        status="pending",
        errors=[],
        step_times={},
        
        # Fallbacks
        fallback_issue_path=None,
        skipped_nodes=[],
        
        # Metadata
        execution_graph={},
    )
