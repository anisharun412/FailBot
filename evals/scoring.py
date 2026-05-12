"""Shared evaluation scoring helpers for FailBot runs and batch evals."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple, Mapping

from evals.metrics import score_category, score_severity, score_keyword_recall


DEFAULT_GROUND_TRUTH_PATH = Path(__file__).resolve().parent / "ground_truth.json"


def load_ground_truth(ground_truth_path: str | Path | None = None) -> Dict[str, Any]:
    path = Path(ground_truth_path) if ground_truth_path else DEFAULT_GROUND_TRUTH_PATH
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def _candidate_log_keys(log_source: str) -> list[str]:
    normalized = Path(log_source).as_posix().replace("\\", "/")
    candidates = [normalized, Path(normalized).name]

    for marker in ("test_log_files", "test_logs", "logs"):
        marker_index = normalized.rfind(marker)
        if marker_index >= 0:
            candidates.append(normalized[marker_index:])

    # Preserve order but drop duplicates
    deduped: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in deduped:
            deduped.append(candidate)
    return deduped


def lookup_expected_entry(
    log_source: str,
    ground_truth: Dict[str, Any],
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    for candidate in _candidate_log_keys(log_source):
        if candidate in ground_truth:
            entry = ground_truth[candidate]
            if isinstance(entry, dict):
                return candidate, entry
    return None, None


def score_eval_run(
    state: Mapping[str, Any],
    expected: Dict[str, Any],
) -> Dict[str, Any]:
    predicted_test = state.get("suggested_test") or ""
    expected_keywords = expected.get("keywords_in_test")
    if expected_keywords is None:
        expected_keywords = expected.get("expected_test_keywords", [])

    remediation_type = expected.get("remediation_type")
    if remediation_type == "strategy":
        test_relevance = 1.0 if state.get("test_language") == "strategy" and predicted_test else 0.0
    else:
        test_relevance = score_keyword_recall(predicted_test, expected_keywords or [])

    confidence_threshold = expected.get("min_confidence")
    actual_confidence = state.get("triage_confidence")

    confidence_ok = True
    if confidence_threshold is not None and actual_confidence is not None:
        confidence_ok = float(actual_confidence) >= float(confidence_threshold)

    severity_score = score_severity(state.get("severity"), expected.get("expected_severity"))

    return {
        "category_match": score_category(state.get("failure_category"), expected.get("expected_category")) == 1.0,
        "severity_match": severity_score > 0.0,
        "severity_score": severity_score,
        "test_relevance": float(test_relevance),
        "confidence_ok": confidence_ok,
        "confidence_threshold": confidence_threshold,
        "actual_confidence": actual_confidence,
        "remediation_type_match": (
            remediation_type is None or remediation_type == state.get("test_language")
        ),
    }


def score_run_with_ground_truth(
    state: Mapping[str, Any],
    log_source: str,
    ground_truth_path: str | Path | None = None,
) -> tuple[Optional[str], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    ground_truth = load_ground_truth(ground_truth_path)
    if not ground_truth:
        return None, None, None

    matched_key, expected = lookup_expected_entry(log_source, ground_truth)
    if not matched_key or not expected:
        return None, None, None

    scores = score_eval_run(state, expected)
    scores["ground_truth_key"] = matched_key
    return matched_key, expected, scores


def update_summary_file(summary_path: str | Path, eval_scores: Dict[str, Any]) -> None:
    path = Path(summary_path)
    if not path.exists():
        return

    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)

    data["eval_scores"] = eval_scores

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, default=str)
