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
    token_counts: Dict[str, int]  # Per-node token usage (flat key structure)
    # Example: {"parse_log_input": 3420, "parse_log_output": 210, ...}
    
    # ========== TIMING & PERFORMANCE ==========
    started_at: datetime               # Pipeline start time
    node_timestamps: Dict[str, float]  # Per-node execution times (ms) - DEPRECATED
    node_durations_ms: Dict[str, float]  # Per-node execution duration in milliseconds
    
    # ========== LOG PARSER AGENT OUTPUT ==========
    parsed_summary: Optional[str]      # Structured summary (JSON string)
    error_signature: Optional[str]     # Key error lines (3-5 lines)
    files_changed: Optional[List[str]] # Files mentioned in log
    language: Optional[str]            # Programming language detected
    
    # ========== TRIAGE AGENT OUTPUT ==========
    failure_category: Optional[Literal["flaky", "infra", "code_bug", "unknown"]]
    severity: Optional[Literal["low", "medium", "high", "critical"]]
    triage_confidence: Optional[float]  # 0.0-1.0
    triage_reasoning: Optional[str]    # Explanation for triage decision
    
    # ========== TEST SUGGESTER AGENT OUTPUT ==========
    suggested_test: Optional[str]      # Generated test code or description
    test_language: Optional[str]       # e.g., "python", "javascript"
    test_validation_errors: Optional[List[str]]  # Syntax/validation errors
    test_confidence: Optional[float]   # Confidence in test suggestion (0.0-1.0)
    test_description: Optional[str]    # Description of test or strategy
    
    # ========== ISSUE FILING OUTPUT ==========
    github_issue_url: Optional[str]    # URL of created GitHub issue
    github_issue_created_at: Optional[str]  # ISO8601 timestamp

    # ========== STATUS TRACKING ==========
    status: Literal["pending", "in_progress", "completed", "failed", "parse_complete", 
                   "parse_failed", "triage_complete", "triage_failed", "suggest_test_complete",
                   "suggest_test_failed", "file_issue_complete", "file_issue_failed", 
                   "suggest_test_generic_complete", "suggest_test_generic_failed", 
                   "report_complete", "report_failed"]
    errors: List[Dict[str, Any]]       # Accumulated error dicts with details
    step_times: Dict[str, float]       # Latency per node (deprecated, use node_timestamps)
    execution_summary_path: Optional[str]  # Saved report summary JSON
    
    # ========== FALLBACK TRACKING ==========
    agent_fallback_used: bool          # True if LLM parsing fell back to regex
    issue_fallback_used: bool          # True if GitHub issue creation fell back to local markdown
    fallback_issue_path: Optional[str] # Local markdown file if GitHub fails
    skipped_nodes: List[str]           # Nodes skipped due to routing
    
    # ========== METADATA ==========
    execution_graph: Dict[str, Any]    # Graph execution trace (for debugging)


# Default state factory function
def create_initial_state(
    log_source: str,
    repo_name: Optional[str] = None,
    run_id: Optional[str] = None
) -> FailBotState:
    """
    Create an initial FailBotState with all fields set to defaults.
    
    Args:
        log_source: Raw log text or URL to fetch
        repo_name: GitHub repository (owner/repo). Defaults to "unknown" if omitted.
        run_id: Optional unique run identifier (UUID will be generated if None)
    
    Returns:
        Initialized FailBotState
    """
    import uuid
    
    state: FailBotState = {
        # Input
        "log_source": log_source,
        "repo_name": repo_name or "unknown",
        "run_id": run_id or str(uuid.uuid4()),
        
        # Log preprocessing
        "log_text_full": None,
        "log_text": None,
        "log_truncated_reason": None,
        "raw_log_length": None,
        
        # Token tracking
        "token_counts": {},
        
        # Timing
        "started_at": datetime.now(),
        "node_timestamps": {},
        "node_durations_ms": {},
        
        # Parser outputs
        "parsed_summary": None,
        "error_signature": None,
        "files_changed": None,
        "language": None,
        
        # Triage outputs
        "failure_category": None,
        "severity": None,
        "triage_confidence": None,
        "triage_reasoning": None,
        
        # Test outputs
        "suggested_test": None,
        "test_language": None,
        "test_validation_errors": None,
        "test_confidence": None,
        "test_description": None,
        
        # Issue outputs
        "github_issue_url": None,
        "github_issue_created_at": None,

        # Summary output
        "execution_summary_path": None,

        # Status
        "status": "pending",
        "errors": [],
        "step_times": {},
        
        # Fallback tracking
        "agent_fallback_used": False,
        "issue_fallback_used": False,
        "fallback_issue_path": None,
        "skipped_nodes": [],
        
        # Metadata
        "execution_graph": {},
    }
    return state
