"""Evaluation metrics for FailBot outputs."""

from __future__ import annotations

from typing import Iterable, Dict, Any


SEVERITY_ORDER = ["low", "medium", "high", "critical"]


def _index_or_none(value: str, ordered: list[str]) -> int | None:
    try:
        return ordered.index(value)
    except ValueError:
        return None


def score_category(predicted: str | None, expected: str | None) -> float:
    if not predicted or not expected:
        return 0.0
    return 1.0 if predicted == expected else 0.0


def score_severity(predicted: str | None, expected: str | None) -> float:
    if not predicted or not expected:
        return 0.0
    pred_idx = _index_or_none(predicted, SEVERITY_ORDER)
    exp_idx = _index_or_none(expected, SEVERITY_ORDER)
    if pred_idx is None or exp_idx is None:
        return 0.0
    if pred_idx == exp_idx:
        return 1.0
    if abs(pred_idx - exp_idx) == 1:
        return 0.5
    return 0.0


def score_keyword_recall(text: str | None, keywords: Iterable[str]) -> float:
    keyword_list = [kw for kw in keywords if kw]
    if not keyword_list:
        return 0.0
    if not text:
        return 0.0
    lowered = text.lower()
    hits = sum(1 for kw in keyword_list if kw.lower() in lowered)
    return hits / max(len(keyword_list), 1)


def compute_row_metrics(state: Dict[str, Any], expected: Dict[str, Any]) -> Dict[str, Any]:
    predicted_category = state.get("failure_category")
    predicted_severity = state.get("severity")
    predicted_test = state.get("suggested_test") or ""

    expected_category = expected.get("expected_category")
    expected_severity = expected.get("expected_severity")
    expected_keywords = expected.get("keywords_in_test")
    if expected_keywords is None:
        expected_keywords = expected.get("expected_test_keywords", [])

    min_confidence = expected.get("min_confidence")
    actual_confidence = state.get("triage_confidence")
    confidence_ok = 1.0
    if min_confidence is not None and actual_confidence is not None:
        confidence_ok = 1.0 if float(actual_confidence) >= float(min_confidence) else 0.0

    return {
        "category_accuracy": score_category(predicted_category, expected_category),
        "severity_accuracy": score_severity(predicted_severity, expected_severity),
        "test_keyword_recall": score_keyword_recall(predicted_test, expected_keywords),
        "confidence_ok": confidence_ok,
    }


def summarize(rows: Iterable[Dict[str, Any]]) -> Dict[str, float]:
    totals = {
        "category_accuracy": 0.0,
        "severity_accuracy": 0.0,
        "test_keyword_recall": 0.0,
        "confidence_ok": 0.0,
    }
    count = 0
    for row in rows:
        count += 1
        for key in totals:
            totals[key] += float(row.get(key, 0.0))

    if count == 0:
        return {key: 0.0 for key in totals}

    return {key: totals[key] / count for key in totals}
