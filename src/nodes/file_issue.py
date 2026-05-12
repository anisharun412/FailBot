"""File issue node: Create GitHub issue with triage and test results."""

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from src.config import get_config
from src.state import FailBotState
from src.tools.langchain_tools import get_bound_model
from src.utils.graph_utils import handle_node_error, log_node_end, log_node_start
from src.utils.llm_factory import get_chat_model
from src.utils.logging_config import log_event
from src.utils.prompt_templates import render_agent_prompt
from src.utils.response_utils import extract_token_usage, format_error_slug
from src.utils.token_counter import TokenCounter
from src.utils.tool_runner import parse_tool_message, run_tool_calls


logger = logging.getLogger(__name__)


def save_fallback_issue_markdown(
    title: str,
    body: str,
    state: FailBotState,
    output_dir: str = "runs"
) -> str:
    """
    Save issue as markdown file with clean naming.
    
    Filename format: {run_id_short}_{severity}_{category}_{error_slug}.md
    
    Args:
        title: Issue title
        body: Issue body markdown
        state: FailBotState for context
        output_dir: Directory to save markdown
        
    Returns:
        Path to saved markdown file
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Extract components for clean filename
    run_id_short = state.get("run_id", "unknown")[:8]
    severity = (state.get("severity") or "unknown").lower()
    category = (state.get("failure_category") or "unknown").lower()
    error_sig = state.get("error_signature") or "error"
    error_slug = format_error_slug(error_sig, max_len=40)
    
    # Build clean filename
    filename = f"{run_id_short}_{severity}_{category}_{error_slug}.md"
    file_path = output_path / filename

    error_signature = state.get("error_signature") or "N/A"
    suggested_fix = state.get("suggested_test") or "No suggestions generated"
    files_changed = state.get("files_changed") or []
    affected_files = "\n".join(f"- {f}" for f in files_changed[:5]) if files_changed else "- N/A"
    
    # Build well-formatted markdown
    issue_content = f"""# {title}

## Summary
FailBot could not create the GitHub issue through the API, so the issue was saved locally for follow-up.

## Details

### Triage
- **Category**: {category}
- **Severity**: {severity.upper()}
- **Confidence**: {state.get('triage_confidence', 0):.0%}
- **Run ID**: {run_id_short}

### Error Information
```
{error_signature}
```

### Affected Files
{affected_files}

### Suggested Fix
{suggested_fix}

---
**Created by FailBot** | Timestamp: {datetime.now().isoformat()}
"""
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(issue_content)
    
    logger.info(f"Fallback issue saved to {file_path}")
    return str(file_path)


def format_github_issue_body(state: FailBotState) -> tuple[str, str]:
    """
    Format the GitHub issue body using project prompt templates.
    
    Uses the configured prompt template from config/prompts.yaml to maintain
    consistency with project standards and enable configuration without code changes.
    
    Args:
        state: FailBotState with all triage and test info
        
    Returns:
        Tuple of (title, body) for GitHub issue
    """
    # Build issue title - safely handle None values
    severity: str = (state.get('severity') or 'UNKNOWN').upper()
    error_sig: str = state.get('error_signature') or 'Unknown Error'
    title = f"[{severity}] {error_sig[:80]}"
    
    # Format affected files list
    files_changed: Optional[list[str]] = state.get('files_changed')
    affected_files = "\n".join(f"- `{f}`" for f in (files_changed[:5] if files_changed else [])) if files_changed else "- N/A"
    
    # Format suggested test/strategy
    suggested_test: str = state.get('suggested_test') or 'No suggestion generated'
    test_lang: Optional[str] = state.get('test_language')
    if test_lang == 'strategy':
        # For flaky/infra issues, it's a strategy
        test_desc: str = state.get('test_description') or 'Unknown'
        remediation = f"**Strategy**: {test_desc}\n\n{suggested_test}"
    else:
        # For code bugs, it's actual test code
        lang = test_lang or 'unknown'
        remediation = f"**Test ({lang}):**\n```{lang}\n{suggested_test}\n```"
    
    # Use project's prompt template system - template from config/prompts.yaml
    parsed_summary: str = state.get('parsed_summary') or 'N/A'
    error_signature: str = state.get('error_signature') or 'N/A'
    triage_reasoning: str = state.get('triage_reasoning') or 'N/A'
    run_id: str = state.get('run_id') or 'N/A'
    
    body = render_agent_prompt(
        "file_issue",
        "format_issue_body",
        summary=parsed_summary[:200],
        category=state.get('failure_category') or 'unknown',
        severity=severity.lower(),
        confidence=f"{state.get('triage_confidence') or 0:.0%}",
        affected_files=affected_files,
        error_signature=error_signature[:500],
        suggested_test=remediation,
        reasoning=triage_reasoning[:300],
        timestamp=datetime.now().isoformat(),
        run_id=run_id[:8],
    )
    
    return title, body



async def file_issue_node(state: FailBotState) -> FailBotState:
    """
    File issue node: Create GitHub issue with triage results and test suggestion.
    
    Uses LLM with tool binding to create GitHub issues. The model can decide
    to use the create_github_issue tool when appropriate.
    
    Follows project patterns:
    - Uses render_agent_prompt() for prompts (from config/prompts.yaml)
    - Uses tool binding (get_bound_model) for agent decision-making
    - Proper error handling with fallbacks
    - Structured logging with log_event
    - Tracks agent_fallback_used and issue_fallback_used separately
    
    Args:
        state: FailBotState with all triage and test info
        
    Returns:
        Updated FailBotState with:
        - github_issue_url: URL of created issue, or path to markdown file
        - issue_fallback_used: True if markdown fallback used
        - status: Updated to 'file_issue_complete'
        - node_durations_ms: Updated with execution time
        - errors: Appended with any errors
    """
    start_time = log_node_start(
        logger, state["run_id"], "file_issue", state
    )
    node_start_time = time.perf_counter()
    
    try:
        config = get_config()
        repo_name: str = state.get("repo_name") or "unknown"
        owner: str = "unknown"
        repo: str = repo_name
        if repo_name and "/" in repo_name:
            owner, repo = repo_name.split("/", 1)
        
        log_event(
            logger, state["run_id"], "file_issue",
            "issue_filing_start",
            {
                "repo": repo_name,
                "category": state.get("failure_category"),
                "severity": state.get("severity")
            }
        )
        
        # Validate prerequisites
        if not state.get("error_signature"):
            raise ValueError("Error signature not available")
        if not state.get("failure_category"):
            raise ValueError("Failure category not available")
        
        # Format GitHub issue
        title, body = format_github_issue_body(state)
        
        log_event(
            logger, state["run_id"], "file_issue",
            "issue_formatted",
            {"title": title[:80], "body_length": len(body)}
        )
        
        # Initialize LLM with tools bound (don't force tool use - let model decide)
        model = get_chat_model(
            role="test_suggester",  # Use general model
            temperature=0.0,
            max_tokens=500,
        )
        bound_model = get_bound_model(
            model,
            tool_choice=None,  # Let model decide whether to use tools
        )
        
        # Prepare context for LLM using project templates
        system_prompt: str = render_agent_prompt("file_issue", "system")
        
        user_prompt = f"""Please file this GitHub issue:

Repository: {owner}/{repo}
Title: {title}

Body:
{body}

Failure Category: {state.get('failure_category')}
Severity: {state.get('severity')}

Use the create_github_issue tool to file this issue with appropriate labels."""
        
        # Extract result from model response
        issue_url: Optional[str] = None
        method_used: Optional[str] = None
        issue_fallback_used: bool = False
        
        # Try tool calling first
        try:
            # Call model (it will decide whether to use tools)
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]
            log_event(logger, state["run_id"], "file_issue", "Tool call: create_github_issue", {})
            response = await bound_model.ainvoke(messages)
            log_event(logger, state["run_id"], "file_issue", "Tool call completed", {})
            
            tool_messages = await run_tool_calls(response)
            for tool_message in tool_messages:
                if tool_message.name == "create_github_issue":
                    result: dict[str, Any] = parse_tool_message(tool_message)
                    if result.get("success"):
                        issue_url = result.get("issue_url")
                        method_used = result.get("method")

                        if issue_url:
                            log_event(
                                logger, state["run_id"], "file_issue",
                                "issue_filed_via_tool",
                                {
                                    "url": issue_url[:80] if isinstance(issue_url, str) else issue_url,
                                    "method": method_used
                                }
                            )
                            
                            # Check if this was actually a fallback (local markdown)
                            if method_used == "local_markdown":
                                issue_fallback_used = True
        except Exception as tool_call_error:
            # Tool calling failed (e.g., model doesn't support it) - use fallback
            logger.warning(
                f"Tool calling failed, attempting fallback: {str(tool_call_error)[:80]}"
            )
            log_event(
                logger, state["run_id"], "file_issue",
                "tool_calling_fallback",
                {"error": str(tool_call_error)[:80]}
            )
        
        # Fallback: If no tool was called or tool calling failed, use markdown
        if not issue_url:
            logger.info("Filing issue via markdown fallback...")
            issue_fallback_used = True
            issue_url = save_fallback_issue_markdown(title, body, state)
            method_used = "local_markdown"
            
            log_event(
                logger, state["run_id"], "file_issue",
                "issue_filed_via_fallback",
                {"path": issue_url[:80], "method": "markdown"}
            )
        
        # Update state
        state["github_issue_url"] = issue_url
        state["issue_fallback_used"] = issue_fallback_used
        
        # Track tokens (estimate for tool calling, which doesn't return usage stats)
        token_counter = TokenCounter("gpt-4o-mini")
        issue_tokens = token_counter.count_tokens(user_prompt)
        state["token_counts"]["file_issue"] = issue_tokens
        
        # Track execution time
        node_duration_ms = (time.perf_counter() - node_start_time) * 1000
        state["node_durations_ms"]["file_issue"] = node_duration_ms
        
        state["status"] = "file_issue_complete"
        
        log_event(
            logger, state["run_id"], "file_issue",
            "issue_filing_complete",
            {
                "fallback_used": issue_fallback_used,
                "method": method_used,
                "duration_ms": node_duration_ms
            }
        )
        
        log_node_end(logger, state["run_id"], "file_issue", state, start_time)
        
        return state
        
    except Exception as e:
        error_msg = f"File issue node failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        state["errors"].append({
            "node": "file_issue",
            "error": str(e),
            "type": type(e).__name__
        })
        
        # Track execution time even on error
        node_duration_ms = (time.perf_counter() - node_start_time) * 1000
        state["node_durations_ms"]["file_issue"] = node_duration_ms
        
        state["status"] = "file_issue_failed"
        handle_node_error(logger, state["run_id"], "file_issue", e, state)
        
        raise
