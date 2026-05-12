"""Eval Dashboard – evaluation scores and ground-truth comparison."""

from __future__ import annotations
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

from dashboard.data_loader import load_ground_truth


PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter", color="#e6edf3"),
    margin=dict(l=10, r=10, t=30, b=10),
)


def _pct(v) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.0%}"
    except Exception:
        return str(v)


def _yn(v) -> str:
    if v is None:
        return "—"
    return ":material/check_circle:" if v else ":material/cancel:"


def render_eval_dashboard(eval_data: Optional[Dict[str, Any]], df: pd.DataFrame) -> None:
    st.markdown("## 🎯 Eval Dashboard")
    EVAL_TIMEOUT_SECONDS = 1800

    # ── Harness Controls ──────────────────────────────────────────────────────
    with st.expander("🛠️ Run Evaluation Harness & Upload Logs", expanded=False):
        c1, c2 = st.columns([1, 1])
        
        with c1:
            st.markdown("#### Upload Test Logs")
            uploaded_files = st.file_uploader(
                "Upload log files to `evals/test_logs/`", 
                accept_multiple_files=True,
                type=["txt", "log"]
            )
            if uploaded_files and st.button("Save Uploaded Logs"):
                logs_dir = Path("evals/test_logs")
                logs_dir.mkdir(parents=True, exist_ok=True)
                saved_count = 0
                for f in uploaded_files:
                    safe_name = Path(f.name).name.strip().lstrip(".")
                    if not safe_name or safe_name != f.name:
                        st.warning(f"Skipping unsafe upload name: {f.name}")
                        continue
                    target_path = logs_dir / safe_name
                    with open(target_path, "wb") as out:
                        out.write(f.getvalue())
                    saved_count += 1
                st.success(f"Saved {saved_count} file(s) to `evals/test_logs/`")

        with c2:
            st.markdown("#### Run Harness")
            eval_repo = st.text_input("Repository (owner/repo)", value="owner/repo").strip()
            repo_valid = bool(re.match(r"^[^\s/]+/[^\s/]+$", eval_repo))
            if st.button("Execute Eval Pipeline", type="primary"):
                if not repo_valid:
                    st.error("Invalid repository format. Use owner/repo")
                else:
                    with st.spinner("Running eval harness (this may take a while)..."):
                        try:
                            # Run the eval script as a subprocess
                            result = subprocess.run(
                                [sys.executable, "-m", "evals.eval", "--repo", eval_repo],
                                capture_output=True,
                                text=True,
                                check=True,
                                timeout=EVAL_TIMEOUT_SECONDS,
                            )
                            st.success("Evaluation completed successfully!")
                            with st.expander("Subprocess Output", expanded=False):
                                st.code(result.stdout)
                            # Clear cache so new results are loaded
                            st.cache_data.clear()
                            # Reload the page to reflect new eval data
                            st.rerun()
                        except subprocess.TimeoutExpired:
                            st.error(f"Evaluation timed out after {EVAL_TIMEOUT_SECONDS} seconds")
                        except subprocess.CalledProcessError as e:
                            st.error(f"Evaluation failed with exit code {e.returncode}")
                            st.code(e.stderr)

    # ── Summary from eval_summary.json ───────────────────────────────────────
    if eval_data and "summary" in eval_data:
        summary = eval_data["summary"]
        st.markdown("### Aggregate Evaluation Scores")
        st.markdown(
            '<p style="color:#8b949e;font-size:.82rem;">Computed by the FailBot evaluation harness against ground-truth labels.</p>',
            unsafe_allow_html=True,
        )
        e1, e2, e3, e4 = st.columns(4)
        e1.metric("Category Accuracy",     _pct(summary.get("category_accuracy")))
        e2.metric("Severity Accuracy",     _pct(summary.get("severity_accuracy")))
        e3.metric("Test Keyword Recall",   _pct(summary.get("test_keyword_recall")))
        e4.metric("Confidence OK",         _pct(summary.get("confidence_ok")))

        # Gauge charts
        st.markdown("<br>", unsafe_allow_html=True)
        gc1, gc2, gc3, gc4 = st.columns(4)

        metrics_map = {
            gc1: ("Category Accuracy", summary.get("category_accuracy", 0), "#3fb950"),
            gc2: ("Severity Accuracy", summary.get("severity_accuracy", 0), "#e3b341"),
            gc3: ("Test Recall",       summary.get("test_keyword_recall", 0), "#58a6ff"),
            gc4: ("Confidence OK",     summary.get("confidence_ok", 0), "#bc8cff"),
        }
        for col, (label, val, color) in metrics_map.items():
            fig = go.Figure(go.Indicator(
                mode="gauge+number",
                value=float(val or 0) * 100,
                number=dict(suffix="%", font=dict(size=24, color=color)),
                gauge=dict(
                    axis=dict(range=[0, 100], tickcolor="#30363d",
                              tickfont=dict(color="#8b949e", size=10)),
                    bar=dict(color=color),
                    bgcolor="#1c2333",
                    borderwidth=0,
                    steps=[dict(range=[0, 100], color="#21262d")],
                    threshold=dict(line=dict(color="#30363d", width=2), thickness=0.75, value=80),
                ),
                title=dict(text=label, font=dict(size=11, color="#8b949e")),
            ))
            fig.update_layout(**PLOTLY_LAYOUT, height=200)
            col.plotly_chart(fig, use_container_width=True, key=f"gauge_{label}")

        # Per-row table
        if "rows" in eval_data and eval_data["rows"]:
            st.markdown("---")
            st.markdown("### Per-Run Eval Results")
            rows = eval_data["rows"]
            rows_df = pd.DataFrame(rows)
            display = [c for c in [
                "log_file", "status", "failure_category", "severity",
                "triage_confidence", "eval_category_match", "eval_severity_match",
                "eval_test_relevance", "eval_confidence_ok",
                "category_accuracy", "severity_accuracy", "test_keyword_recall",
                "total_tokens", "total_duration_ms", "error_count",
            ] if c in rows_df.columns]
            st.dataframe(rows_df[display], use_container_width=True, hide_index=True)

    else:
        st.info(
            "No `evals/results/eval_summary.json` found. "
            "Run the eval harness to generate scores:\n\n"
            "```bash\npython -m evals.eval --repo owner/repo\n```",
            
        )

    st.markdown("---")

    # ── Inline eval scores from run summaries ────────────────────────────────
    eval_df = df[df["has_eval"]].copy() if not df.empty else pd.DataFrame()

    if not eval_df.empty:
        st.markdown("### Eval Scores from Run Summaries")
        st.markdown(
            f'<p style="color:#8b949e;font-size:.82rem;">{len(eval_df)} run(s) have embedded eval scores.</p>',
            unsafe_allow_html=True,
        )

        ec1, ec2 = st.columns(2)
        with ec1:
            cat_match_pct = eval_df["eval_category_match"].mean() * 100
            sev_match_pct = eval_df["eval_severity_match"].mean() * 100
            fig = go.Figure()
            for label, val, color in [
                ("Category Match", cat_match_pct, "#3fb950"),
                ("Severity Match", sev_match_pct, "#58a6ff"),
            ]:
                fig.add_trace(go.Bar(name=label, x=[label], y=[val],
                                     marker_color=color, text=[f"{val:.0f}%"],
                                     textposition="outside"))
            fig.update_layout(**PLOTLY_LAYOUT, height=260, showlegend=False,
                              yaxis=dict(range=[0, 115], gridcolor="#21262d"),
                              xaxis=dict(gridcolor="#21262d"))
            st.plotly_chart(fig, use_container_width=True, key="match_bar")

        with ec2:
            avg_rel = eval_df["eval_test_relevance"].mean() * 100
            conf_ok  = eval_df["eval_confidence_ok"].mean() * 100
            fig2 = go.Figure()
            for label, val, color in [
                ("Test Relevance",  avg_rel, "#e3b341"),
                ("Confidence OK",   conf_ok, "#bc8cff"),
            ]:
                fig2.add_trace(go.Bar(name=label, x=[label], y=[val],
                                      marker_color=color, text=[f"{val:.0f}%"],
                                      textposition="outside"))
            fig2.update_layout(**PLOTLY_LAYOUT, height=260, showlegend=False,
                               yaxis=dict(range=[0, 115], gridcolor="#21262d"),
                               xaxis=dict(gridcolor="#21262d"))
            st.plotly_chart(fig2, use_container_width=True, key="rel_bar")

        # Scatter: confidence vs severity_score
        if "eval_severity_score" in eval_df.columns and "eval_actual_confidence" in eval_df.columns:
            scat_df = eval_df.dropna(subset=["eval_actual_confidence", "eval_severity_score"])
            if not scat_df.empty:
                st.markdown("**Triage Confidence vs Severity Score**")
                fig3 = px.scatter(
                    scat_df,
                    x="eval_actual_confidence",
                    y="eval_severity_score",
                    color="failure_category",
                    color_discrete_map={
                        "code_bug": "#f85149", "infra": "#e3b341",
                        "flaky": "#bc8cff", "unknown": "#8b949e",
                    },
                    hover_data=["run_id", "severity"],
                    labels={"eval_actual_confidence": "Confidence", "eval_severity_score": "Severity Score"},
                )
                fig3.update_layout(**PLOTLY_LAYOUT, height=320,
                                   xaxis=dict(gridcolor="#21262d"),
                                   yaxis=dict(gridcolor="#21262d"))
                fig3.update_traces(marker=dict(size=9, line=dict(width=0)))
                st.plotly_chart(fig3, use_container_width=True, key="conf_scatter")

    # ── Ground truth browser ─────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### Ground Truth Labels")
    gt = load_ground_truth()
    if gt:
        gt_rows = []
        for key, val in gt.items():
            gt_rows.append({
                "Log File": key,
                "Expected Category": val.get("expected_category", "—"),
                "Expected Severity": val.get("expected_severity", "—"),
                "Min Confidence": val.get("min_confidence", "—"),
                "Keywords": ", ".join(val.get("expected_test_keywords") or val.get("keywords_in_test") or []),
            })
        st.dataframe(pd.DataFrame(gt_rows), use_container_width=True, hide_index=True)
    else:
        st.info("No ground truth file found at `evals/ground_truth.json`.")
