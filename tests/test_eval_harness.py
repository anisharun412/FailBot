"""Tests for the eval harness row generation."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from evals.eval import _evaluate_log


async def _evaluate_log_includes_timing_and_fallback_fields(tmp_path, monkeypatch):
    log_path = tmp_path / "sample.txt"
    log_path.write_text("sample log", encoding="utf-8")

    expected = {
        "expected_category": "infra",
        "expected_severity": "high",
        "expected_test_keywords": ["health", "retry"],
    }

    async def fake_run_failbot(**kwargs):
        return {
            "status": "report_complete",
            "failure_category": "infra",
            "severity": "high",
            "triage_confidence": 0.91,
            "test_language": "strategy",
            "github_issue_url": None,
            "fallback_issue_path": "runs/fallback_issue.md",
            "agent_fallback_used": True,
            "issue_fallback_used": True,
            "node_durations_ms": {"parse_log": 12.5, "file_issue": 8.25},
            "token_counts": {"parse_log": 120, "file_issue": 45},
            "execution_summary_path": "runs/summary.json",
            "errors": [],
            "suggested_test": "retry and health checks",
        }

    monkeypatch.setattr("evals.eval.run_failbot", fake_run_failbot)

    row = await _evaluate_log(
        log_path=log_path,
        repo="owner/repo",
        expected=expected,
        config_path=None,
        output_dir=str(tmp_path),
    )

    assert row["status"] == "report_complete"
    assert row["github_issue_url"] == "runs/fallback_issue.md"
    assert row["agent_fallback_used"] is True
    assert row["issue_fallback_used"] is True
    assert row["total_duration_ms"] == pytest.approx(20.75)
    assert row["total_tokens"] == 165
    assert row["category_accuracy"] == 1.0
    assert row["severity_accuracy"] == 1.0
    assert row["test_keyword_recall"] == 1.0
    assert row["eval_confidence_ok"] is True
    eval_scores = json.loads(row["eval_scores"])
    assert eval_scores["category_match"] is True
    assert eval_scores["severity_match"] is True
    assert eval_scores["test_relevance"] == 1.0
    assert json.loads(row["node_durations_ms"]) == {"file_issue": 8.25, "parse_log": 12.5}


def test_evaluate_log_includes_timing_and_fallback_fields(tmp_path, monkeypatch):
    asyncio.run(_evaluate_log_includes_timing_and_fallback_fields(tmp_path, monkeypatch))