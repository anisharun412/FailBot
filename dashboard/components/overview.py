"""Overview / home page component."""

from __future__ import annotations
from typing import Any, Optional
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


CATEGORY_COLORS = {
    "code_bug": "#f85149",
    "infra":    "#e3b341",
    "flaky":    "#bc8cff",
    "unknown":  "#8b949e",
}
SEVERITY_COLORS = {
    "critical": "#ff7b72",
    "high":     "#f85149",
    "medium":   "#e3b341",
    "low":      "#3fb950",
}
PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter", color="#e6edf3"),
    margin=dict(l=10, r=10, t=30, b=10),
)


def _badge(text: str, kind: str) -> str:
    css = {
        "code_bug": "background:rgba(248,81,73,.15);color:#f85149",
        "infra":    "background:rgba(227,179,65,.15);color:#e3b341",
        "flaky":    "background:rgba(188,140,255,.15);color:#bc8cff",
        "unknown":  "background:rgba(139,148,158,.15);color:#8b949e",
        "high":     "background:rgba(248,81,73,.15);color:#f85149",
        "critical": "background:rgba(248,81,73,.2);color:#ff7b72",
        "medium":   "background:rgba(227,179,65,.15);color:#e3b341",
        "low":      "background:rgba(63,185,80,.15);color:#3fb950",
    }.get(kind, "background:rgba(139,148,158,.15);color:#8b949e")
    return f'<span style="display:inline-block;padding:2px 9px;border-radius:20px;font-size:.72rem;font-weight:600;{css}">{text.upper()}</span>'


def render_overview(df: pd.DataFrame) -> None:
    # Hero
    st.markdown(
        """
        <div style="background:linear-gradient(135deg,#1f2937,#111827); border:1px solid #374151;
                    border-radius:16px; padding:28px 32px; margin-bottom:28px; display:flex; align-items:center; gap:20px;">
            <div style="background:#10b98122; padding:15px; border-radius:12px; border:1px solid #10b98144;">
                 <span style="font-size:2.8rem; font-weight:800; color:#10b981; display:block;">📈</span>
            </div>
            <div>
                <div style="font-size:1.8rem; font-weight:800; color:#f9fafb; margin-bottom:4px; letter-spacing:-0.02em;">System Analytics</div>
                <div style="color:#9ca3af; font-size:0.95rem; font-weight:500;">
                    Automated CI Failure Triage & Multi-Agent Pipeline Monitoring
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if df.empty:
        st.info("No run summaries found. Run FailBot to populate data.", icon="ℹ️")
        return

    # ── KPI Row ──────────────────────────────────────────────────────────────
    total        = len(df)
    success_mask = df["error_count"] == 0
    success_rate = success_mask.mean() * 100
    avg_ms       = df["total_duration_ms"].mean()
    avg_tokens   = df["total_tokens"].mean()
    fallback_pct = df["issue_fallback"].mean() * 100

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total Runs",       f"{total:,}")
    k2.metric("Success Rate",     f"{success_rate:.1f}%")
    k3.metric("Avg Duration",     f"{avg_ms/1000:.1f}s")
    k4.metric("Avg Tokens / Run", f"{avg_tokens:,.0f}")
    k5.metric("GitHub Fallback",  f"{fallback_pct:.0f}%")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Charts Row 1 ──────────────────────────────────────────────────────────
    c1, c2 = st.columns(2)

    with c1:
        st.markdown("**Failure Category Distribution**")
        cat_counts = df["failure_category"].value_counts().reset_index()
        cat_counts.columns = ["category", "count"]
        fig = px.pie(
            cat_counts, names="category", values="count",
            color="category", color_discrete_map=CATEGORY_COLORS,
            hole=0.55,
        )
        fig.update_layout(**PLOTLY_LAYOUT, showlegend=True,
                          legend=dict(orientation="h", y=-0.12))
        fig.update_traces(textposition="inside", textinfo="percent+label",
                          marker=dict(line=dict(color="#0d1117", width=2)))
        st.plotly_chart(fig, use_container_width=True, key="cat_pie")

    with c2:
        st.markdown("**Severity Distribution**")
        sev_counts = df["severity"].value_counts().reset_index()
        sev_counts.columns = ["severity", "count"]
        sev_order = ["critical", "high", "medium", "low"]
        sev_counts["severity"] = pd.Categorical(sev_counts["severity"],
                                                 categories=sev_order, ordered=True)
        sev_counts = sev_counts.sort_values("severity")
        fig2 = px.bar(
            sev_counts, x="severity", y="count",
            color="severity", color_discrete_map=SEVERITY_COLORS,
            text="count",
        )
        fig2.update_layout(**PLOTLY_LAYOUT, showlegend=False,
                           xaxis=dict(gridcolor="#21262d"),
                           yaxis=dict(gridcolor="#21262d"))
        fig2.update_traces(textposition="outside", marker_line_width=0)
        st.plotly_chart(fig2, use_container_width=True, key="sev_bar")

    # ── Charts Row 2 ──────────────────────────────────────────────────────────
    c3, c4 = st.columns(2)

    with c3:
        st.markdown("**Token Usage per Run**")
        recent = df.head(30).copy()
        recent["label"] = recent["run_id"] + " · " + recent["failure_category"].fillna("?")
        fig3 = px.bar(
            recent[::-1], x="total_tokens", y="label",
            orientation="h", color="failure_category",
            color_discrete_map=CATEGORY_COLORS,
        )
        fig3.update_layout(**PLOTLY_LAYOUT, showlegend=False,
                           height=340,
                           yaxis=dict(tickfont=dict(size=10), gridcolor="#21262d"),
                           xaxis=dict(gridcolor="#21262d"))
        st.plotly_chart(fig3, use_container_width=True, key="token_bar")

    with c4:
        st.markdown("**Pipeline Duration (ms) – last 30 runs**")
        ts_df = df.dropna(subset=["timestamp"]).head(30)[::-1]
        fig4 = go.Figure()
        fig4.add_trace(go.Scatter(
            x=ts_df["timestamp"], y=ts_df["total_duration_ms"],
            mode="lines+markers",
            line=dict(color="#58a6ff", width=2),
            marker=dict(size=5, color="#58a6ff"),
            fill="tozeroy",
            fillcolor="rgba(88,166,255,0.08)",
        ))
        fig4.update_layout(**PLOTLY_LAYOUT, height=340,
                           xaxis=dict(gridcolor="#21262d"),
                           yaxis=dict(gridcolor="#21262d", title="ms"))
        st.plotly_chart(fig4, use_container_width=True, key="dur_line")

    # ── Recent Runs Table ─────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**Recent Runs**")

    display_cols = ["run_id", "timestamp_str", "log_source", "failure_category",
                    "severity", "triage_confidence", "total_tokens",
                    "total_duration_ms", "error_count", "issue_filed"]

    recent_df = df[display_cols].head(15).copy()
    recent_df["total_duration_ms"] = recent_df["total_duration_ms"].map(lambda x: f"{x:.0f}")
    recent_df["triage_confidence"] = recent_df["triage_confidence"].map(
        lambda x: f"{x:.0%}" if pd.notna(x) else "—"
    )
    recent_df.columns = ["Run ID", "Timestamp", "Log Source", "Category",
                         "Severity", "Confidence", "Tokens", "Duration(ms)", "Errors", "Issue Filed"]
    st.dataframe(recent_df, use_container_width=True, hide_index=True)
