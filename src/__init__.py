"""
FailBot - Multi-Agent CI Failure Triage and Test Generation Pipeline

A LangGraph-based multi-agent system that:
- Parses CI logs (GitHub Actions, Jenkins, etc.)
- Triages failures into categories (code_bug, flaky, infra, unknown)
- Generates regression tests for code bugs
- Files GitHub issues with suggestions

Version: 0.1.0
"""

__version__ = "0.1.0"
__author__ = "FailBot Team"

from src.state import FailBotState, create_initial_state
from src.config import FailBotConfig, load_config, get_config

__all__ = [
    "FailBotState",
    "create_initial_state",
    "FailBotConfig",
    "load_config",
    "get_config",
]
