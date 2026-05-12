"""Unit tests for evaluation metrics."""

from evals.metrics import compute_row_metrics, summarize


def test_compute_row_metrics():
    state = {
        "failure_category": "code_bug",
        "severity": "high",
        "suggested_test": "assert True"
    }
    expected = {
        "expected_category": "code_bug",
        "expected_severity": "high",
        "expected_test_keywords": ["assert"]
    }

    metrics = compute_row_metrics(state, expected)
    assert metrics["category_accuracy"] == 1.0
    assert metrics["severity_accuracy"] == 1.0
    assert metrics["test_keyword_recall"] == 1.0


def test_summarize_metrics():
    rows = [
        {"category_accuracy": 1.0, "severity_accuracy": 0.5, "test_keyword_recall": 0.0},
        {"category_accuracy": 0.0, "severity_accuracy": 1.0, "test_keyword_recall": 1.0},
    ]
    summary = summarize(rows)
    assert summary["category_accuracy"] == 0.5
    assert summary["severity_accuracy"] == 0.75
    assert summary["test_keyword_recall"] == 0.5


def test_compute_row_metrics_missing_values():
    state = {
        "failure_category": None,
        "severity": None,
        "suggested_test": None,
    }
    expected = {
        "expected_category": "code_bug",
        "expected_severity": "high",
        "expected_test_keywords": ["assert"],
    }

    metrics = compute_row_metrics(state, expected)
    assert metrics["category_accuracy"] == 0.0
    assert metrics["severity_accuracy"] == 0.0
    assert metrics["test_keyword_recall"] == 0.0


def test_summarize_empty_rows():
    summary = summarize([])
    assert summary["category_accuracy"] == 0.0
    assert summary["severity_accuracy"] == 0.0
    assert summary["test_keyword_recall"] == 0.0


def test_compute_row_metrics_confidence_threshold():
    state = {
        "failure_category": "infra",
        "severity": "high",
        "triage_confidence": 0.62,
        "suggested_test": "check network",
    }
    expected = {
        "expected_category": "infra",
        "expected_severity": "high",
        "keywords_in_test": ["network"],
        "min_confidence": 0.7,
    }

    metrics = compute_row_metrics(state, expected)
    assert metrics["category_accuracy"] == 1.0
    assert metrics["severity_accuracy"] == 1.0
    assert metrics["test_keyword_recall"] == 1.0
    assert metrics["confidence_ok"] == 0.0
