"""File issue node: Create GitHub issue with triage and test results."""

import logging
from datetime import datetime
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.config import get_config
from src.state import FailBotState
from src.tools.langchain_tools import get_bound_model
from src.utils.graph_utils import handle_node_error, log_node_end, log_node_start
from src.utils.logging_config import log_event
from src.utils.prompt_templates import render_agent_prompt
from src.utils.token_counter import TokenCounter
from src.utils.tool_runner import parse_tool_message, run_tool_calls


logger = logging.getLogger(__name__)


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
    # Build issue title
    title = f"[{state.get('severity', 'UNKNOWN').upper()}] {state.get('error_signature', 'Unknown Error')[:80]}"
    
    # Format affected files list
    files_changed = state.get('files_changed', [])
    affected_files = "\n".join(f"- `{f}`" for f in files_changed[:5]) if files_changed else "- N/A"
    
    # Format suggested test/strategy
    suggested_test = state.get('suggested_test', 'No suggestion generated')
    if state.get('test_language') == 'strategy':
        # For flaky/infra issues, it's a strategy
        remediation = f"**Strategy**: {state.get('test_description', 'Unknown')}\n\n{suggested_test}"
    else:
        # For code bugs, it's actual test code
        lang = state.get('test_language', 'unknown')
        remediation = f"**Test ({lang}):**\n```{lang}\n{suggested_test}\n```"
    
    # Use project's prompt template system - template from config/prompts.yaml
    body = render_agent_prompt(
        "file_issue",
        "format_issue_body",
        summary=state.get('parsed_summary', 'N/A')[:200],
        category=state.get('failure_category', 'unknown'),
        severity=state.get('severity', 'unknown'),
        confidence=f"{state.get('triage_confidence', 0):.0%}",
        affected_files=affected_files,
        error_signature=state.get('error_signature', 'N/A')[:500],
        suggested_test=remediation,
        reasoning=state.get('triage_reasoning', 'N/A')[:300],
        timestamp=datetime.now().isoformat(),
        run_id=state.get('run_id', 'N/A')[:8],
    )
    
    return title, body



async def file_issue_node(state: FailBotState) -> dict[str, Any]:
    """
    File issue node: Create GitHub issue with triage results and test suggestion.
    
    Uses LLM with tool binding to create GitHub issues. The model can decide
    to use the create_github_issue tool when appropriate.
    
    Follows project patterns:
    - Uses render_agent_prompt() for prompts (from config/prompts.yaml)
    - Uses tool binding (get_bound_model) for agent decision-making
    - Proper error handling with fallbacks
    - Structured logging with log_event
    
    Args:
        state: FailBotState with all triage and test info
        
    Returns:
        Updated state dict with:
        - github_issue_url: URL of created issue, or path to markdown file
        - fallback_issue_path: Path if fallback used
        - status: Updated to 'file_issue_complete'
        - errors: Appended with any errors
    """
    start_time = log_node_start(
        logger, state["run_id"], "file_issue", state
    )
    
    try:
        config = get_config()
        repo_name = state.get("repo_name", "unknown")
        owner = "unknown"
        repo = repo_name
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
        
        # Initialize LLM with tools bound
        model = ChatOpenAI(
            model=config.get_model("test_suggester"),  # Use general model
            temperature=0.0,  # Deterministic for issue filing
            max_tokens=500
        )
        bound_model = get_bound_model(model)
        
        # Prepare context for LLM using project templates
        system_prompt = render_agent_prompt("file_issue", "system")
        
        user_prompt = f"""Please file this GitHub issue:

    Repository: {owner}/{repo}
    Title: {title}

    Body:
    {body}

    Failure Category: {state.get('failure_category')}
    Severity: {state.get('severity')}

    Use the create_github_issue tool to file this issue with appropriate labels."""
        
        # Call model (it will decide whether to use tools)
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        response = await bound_model.ainvoke(messages)
        
        # Extract result from model response
        issue_url = None
        method_used = None
        
        tool_messages = await run_tool_calls(response)
        for tool_message in tool_messages:
            if tool_message.name == "create_github_issue":
                result = parse_tool_message(tool_message)
                if result.get("success"):
                    issue_url = result.get("issue_url")
                    method_used = result.get("method")

                    log_event(
                        logger, state["run_id"], "file_issue",
                        "issue_filed_via_tool",
                        {
                            "url": issue_url[:80],
                            "method": method_used
                        }
                    )
        
        # Fallback: If no tool was called, use direct tool invocation
        if not issue_url:
            logger.info("Model did not call tool directly, using fallback...")
            from src.tools.langchain_tools import create_github_issue as create_issue_tool
            
            result = await create_issue_tool.ainvoke({
                "title": title,
                "body": body,
                "owner": owner,
                "repo": repo,
                "labels": ["failbot", state.get("failure_category", "unknown")]
            })
            
            if result.get("success"):
                issue_url = result.get("issue_url")
                method_used = result.get("method")
                
                log_event(
                    logger, state["run_id"], "file_issue",
                    "issue_filed_via_fallback",
                    {"method": method_used}
                )
            else:
                raise Exception(result.get("error", "Issue filing failed"))
        
        # Update state
        state["github_issue_url"] = issue_url
        if method_used == "local_markdown":
            state["fallback_issue_path"] = issue_url
        
        # Track tokens used
        if "token_counts" not in state or state["token_counts"] is None:
            state["token_counts"] = {}
        
        token_counter = TokenCounter("gpt-4o-mini")
        state["token_counts"]["file_issue_input"] = token_counter.count_tokens(user_prompt)
        state["token_counts"]["file_issue_output"] = 0  # Tool calls don't count toward output
        
        state["status"] = "file_issue_complete"
        
        log_event(
            logger, state["run_id"], "file_issue",
            "issue_filing_complete",
            {
                "issue_url": issue_url[:80] if issue_url else None,
                "method": method_used,
                "status": "success"
            }
        )
        
        log_node_end(logger, state["run_id"], "file_issue", state, start_time)
        
        return state
        
    except Exception as e:
        error_msg = f"File issue node failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        if "errors" not in state or state["errors"] is None:
            state["errors"] = []
        
        state["errors"].append({
            "node": "file_issue",
            "error": str(e),
            "type": type(e).__name__,
            "stage": "issue_filing"
        })
        
        state["status"] = "file_issue_failed"
        
        log_event(
            logger, state["run_id"], "file_issue",
            "issue_filing_failed",
            {
                "error": str(e)[:100],
                "error_type": type(e).__name__
            }
        )
        
        handle_node_error(logger, state["run_id"], "file_issue", e, state)
        
        raise

