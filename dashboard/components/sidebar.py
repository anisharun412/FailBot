"""Sidebar navigation component."""

import streamlit as st
from pathlib import Path


PAGES = ["Run Pipeline", "Overview", "Run Explorer", "Eval Dashboard", "Issue Viewer", "Pipeline View"]

ICONS = {
    "Run Pipeline":    "▶",
    "Overview":        "⊞",
    "Run Explorer":    "⌕",
    "Eval Dashboard":  "◠",
    "Issue Viewer":    "▤",
    "Pipeline View":   "⛙",
}


def render_sidebar() -> str:
    with st.sidebar:
        # Logo / title
        st.markdown(
            """
            <div style="text-align:center; padding: 16px 0 24px;">
                <div style="font-size:2.8rem; color:#10b981;">
                    <span style="font-weight:900; font-family:'JetBrains Mono', monospace;">>_</span>
                </div>
                <div style="font-size:1.4rem; font-weight:800; color:#f9fafb; letter-spacing:0.04em; margin-top:8px;">FailBot</div>
                <div style="font-size:0.75rem; color:#9ca3af; margin-top:2px; font-weight:500; text-transform:uppercase; letter-spacing:0.1em;">Enterprise CI Triage</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("---")
        st.markdown(
            "<p style='color:#8b949e;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px;'>Navigation</p>",
            unsafe_allow_html=True,
        )

        page = st.radio(
            label="Navigation",
            options=PAGES,
            format_func=lambda p: f"{ICONS.get(p, '')}  {p}",
            label_visibility="collapsed",
        )

        st.markdown("---")

        # Runs dir info
        runs_dir = Path(__file__).resolve().parents[2] / "runs"
        n_summaries = len(list(runs_dir.glob("summary_*.json")))
        n_issues    = len(list(runs_dir.glob("issue_*.md")))

        st.markdown(
            f"""
            <div style="background:#1c2333;border:1px solid #30363d;border-radius:10px;padding:14px 16px;">
                <div style="color:#8b949e;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:10px;">Runs Directory</div>
                <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
                    <span style="color:#8b949e;font-size:0.82rem;">Summaries</span>
                    <span style="color:#58a6ff;font-weight:600;font-size:0.82rem;">{n_summaries}</span>
                </div>
                <div style="display:flex;justify-content:space-between;">
                    <span style="color:#8b949e;font-size:0.82rem;">Issues filed</span>
                    <span style="color:#58a6ff;font-weight:600;font-size:0.82rem;">{n_issues}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            "<div style='color:#8b949e;font-size:0.68rem;text-align:center;padding:16px 0 0;'>FailBot v0.1 • LangGraph Pipeline</div>",
            unsafe_allow_html=True,
        )

    return page
