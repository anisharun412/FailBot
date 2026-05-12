"""Data loading utilities for the FailBot dashboard."""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

RUNS_DIR   = Path(__file__).resolve().parents[1] / "runs"
EVALS_DIR  = Path(__file__).resolve().parents[1] / "evals"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _safe_load_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ── Summary JSONs ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=30)
def load_all_summaries() -> pd.DataFrame:
    """Load all summary_*.json files from the runs/ directory into a DataFrame."""
    records: List[Dict[str, Any]] = []
    for path in sorted(RUNS_DIR.glob("summary_*.json"), reverse=True):
        data = _safe_load_json(path)
        if not data:
            continue

        # Flatten token_counts totals
        tc = data.get("token_counts") or {}
        total_tokens = (
            data.get("total_tokens")
            or sum(v for v in tc.values() if isinstance(v, (int, float)))
        )

        # Flatten node_durations
        nd = data.get("node_durations_ms") or {}
        total_dur = (
            data.get("total_duration_ms")
            or sum(v for v in nd.values() if isinstance(v, (int, float)))
        )

        # Eval scores
        es = data.get("eval_scores") or {}

        ts_raw = data.get("timestamp") or ""
        try:
            ts = datetime.fromisoformat(ts_raw)
        except Exception:
            ts = None

        records.append({
            "run_id":            data.get("run_id", "")[:8],
            "run_id_full":       data.get("run_id", ""),
            "timestamp":         ts,
            "timestamp_str":     ts_raw[:19] if ts_raw else "",
            "status":            data.get("status", ""),
            "repo_name":         data.get("repo_name", ""),
            "log_source":        Path(data.get("log_source", "")).name,
            "failure_category":  data.get("failure_category", ""),
            "severity":          data.get("severity", ""),
            "triage_confidence": data.get("triage_confidence"),
            "language":          data.get("language", ""),
            "test_generated":    bool(data.get("test_generated", False)),
            "test_language":     data.get("test_language", ""),
            "test_confidence":   data.get("test_confidence"),
            "issue_filed":       bool(data.get("issue_filed", False)),
            "github_issue_url":  data.get("github_issue_url", ""),
            "agent_fallback":    bool(data.get("agent_fallback_used", False)),
            "issue_fallback":    bool(data.get("issue_fallback_used", False)),
            "error_count":       int(data.get("error_count", 0)),
            "total_tokens":      int(total_tokens or 0),
            "total_duration_ms": float(total_dur or 0),
            "node_durations_ms": nd,
            "token_counts":      tc,
            "error_signature":   (data.get("error_signature") or "")[:200],
            "files_changed":     data.get("files_changed") or [],
            "eval_category_match":    es.get("category_match"),
            "eval_severity_match":    es.get("severity_match"),
            "eval_severity_score":    es.get("severity_score"),
            "eval_test_relevance":    es.get("test_relevance"),
            "eval_confidence_ok":     es.get("confidence_ok"),
            "eval_actual_confidence": es.get("actual_confidence"),
            "has_eval":               bool(es),
            "_summary_file":          str(path),
        })

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    if "timestamp" in df.columns:
        df = df.sort_values("timestamp", ascending=False, na_position="last")
    return df


# ── Eval summary ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=30)
def load_eval_summary() -> Optional[Dict[str, Any]]:
    """Load evals/results/eval_summary.json if it exists."""
    path = EVALS_DIR / "results" / "eval_summary.json"
    return _safe_load_json(path)


# ── JSONL run logs ────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def load_jsonl_events(jsonl_path: str) -> List[Dict[str, Any]]:
    events = []
    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except Exception:
        pass
    return events


# ── Issue markdown files ──────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def list_issue_files() -> List[Path]:
    return sorted(RUNS_DIR.glob("issue_*.md"), reverse=True)


def read_issue_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


# ── Ground truth ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=120)
def load_ground_truth() -> Dict[str, Any]:
    path = EVALS_DIR / "ground_truth.json"
    data = _safe_load_json(path)
    return data or {}
