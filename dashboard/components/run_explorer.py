"""Run Explorer – drill-down into individual FailBot runs."""

from __future__ import annotations
import json
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from pathlib import Path

from dashboard.data_loader import load_jsonl_events, RUNS_DIR


CATEGORY_COLORS = {
    "code_bug": "#f85149", "infra": "#e3b341",
    "flaky": "#bc8cff",    "unknown": "#8b949e",
}


def _severity_icon(sev: str) -> str:
    colors = {"critical": "#ff7b72", "high": "#f85149", "medium": "#e3b341", "low": "#3fb950"}
    c = colors.get(sev, "#8b949e")
    return f'<span style="color:{c}; font-size:1.2rem; vertical-align:middle; margin-right:4px;">●</span>'


def _status_color(status: str) -> str:
    if "complete" in status or status == "completed":
        return "#3fb950"
    if "failed" in status:
        return "#f85149"
    return "#e3b341"


def render_run_explorer(df: pd.DataFrame) -> None:
    st.markdown("## 🔍 Run Explorer")

    if df.empty:
        st.info("No runs found.", icon="ℹ️")
        return

    # ── Filters ──────────────────────────────────────────────────────────────
    with st.expander("Filters", expanded=True):
        fc1, fc2, fc3 = st.columns(3)
        cats     = ["All"] + sorted(df["failure_category"].dropna().unique().tolist())
        sevs     = ["All"] + sorted(df["severity"].dropna().unique().tolist())
        statuses = ["All"] + sorted(df["status"].dropna().unique().tolist())

        sel_cat  = fc1.selectbox("Category",  cats,     key="re_cat")
        sel_sev  = fc2.selectbox("Severity",  sevs,     key="re_sev")
        sel_stat = fc3.selectbox("Status",    statuses, key="re_stat")

        fc4, fc5 = st.columns(2)
        only_errors   = fc4.checkbox("Show only runs with errors")
        only_fallback = fc5.checkbox("Show only fallback runs")

    fdf = df.copy()
    if sel_cat  != "All": fdf = fdf[fdf["failure_category"] == sel_cat]
    if sel_sev  != "All": fdf = fdf[fdf["severity"] == sel_sev]
    if sel_stat != "All": fdf = fdf[fdf["status"] == sel_stat]
    if only_errors:   fdf = fdf[fdf["error_count"] > 0]
    if only_fallback: fdf = fdf[fdf["issue_fallback"]]

    st.markdown(f"**{len(fdf)} run(s) matched**")

    # ── Run list ─────────────────────────────────────────────────────────────
    if fdf.empty:
        st.warning("No runs match the selected filters.")
        return

    run_labels = [
        f"{r['run_id']} · {r['timestamp_str']} · {r['failure_category']} · {r['severity']}"
        for _, r in fdf.head(50).iterrows()
    ]
    sel_label = st.selectbox("Select a run to inspect:", run_labels, key="re_select")
    sel_idx   = run_labels.index(sel_label)
    row       = fdf.iloc[sel_idx]

    st.markdown("---")
    _render_run_detail(row)


def _render_run_detail(row: pd.Series) -> None:
    sev_icon = _severity_icon(row.get("severity", ""))
    status_color = _status_color(row.get("status", ""))

    # Header card
    st.markdown(
        f"""
        <div style="background:#1c2333;border:1px solid #30363d;border-radius:14px;padding:20px 26px;margin-bottom:20px;">
            <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;">
                <span style="font-size:1.4rem;font-weight:700;color:#58a6ff;font-family:'JetBrains Mono',monospace;">{row['run_id']}</span>
                <span style="padding:3px 10px;border-radius:20px;font-size:.75rem;font-weight:600;
                             background:rgba(88,166,255,.15);color:#58a6ff;">{row.get('status','')}</span>
                <span style="padding:3px 10px;border-radius:20px;font-size:.75rem;font-weight:600;
                             background:rgba(227,179,65,.15);color:#e3b341;">{sev_icon} {(row.get('severity') or '').upper()}</span>
                <span style="color:#8b949e;font-size:.82rem;">{row.get('timestamp_str','')}</span>
            </div>
            <div style="margin-top:10px; color:#9ca3af; font-size:.85rem; font-weight:500; display:flex; gap:15px;">
                <span><b style="font-size:1rem; vertical-align:middle;">📁</b> <b style='color:#f9fafb'>{row.get('log_source','')}</b></span>
                <span><b style="font-size:1rem; vertical-align:middle;">🏷️</b> <b style='color:#f9fafb'>{row.get('repo_name','')}</b></span>
                <span><b style="font-size:1rem; vertical-align:middle;">🌐</b> <b style='color:#f9fafb'>{row.get('language','')}</b></span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # KPI row
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Triage Confidence",  f"{row.get('triage_confidence') or 0:.0%}")
    k2.metric("Total Tokens",       f"{row.get('total_tokens', 0):,}")
    k3.metric("Duration",           f"{row.get('total_duration_ms', 0)/1000:.2f}s")
    k4.metric("Errors",             str(row.get("error_count", 0)))

    st.markdown("<br>", unsafe_allow_html=True)
    t1, t2, t3 = st.tabs(["📄 Triage & Test", "⏱️ Node Timings", "🪙 Token Breakdown"])

    # Tab 1 – Triage & Test
    with t1:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Triage Result**")
            cat = row.get("failure_category") or "unknown"
            color = CATEGORY_COLORS.get(cat, "#8b949e")
            st.markdown(
                f"""
                <div style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:16px 20px;">
                    <div style="font-size:1.3rem;font-weight:700;color:{color};margin-bottom:8px;">{cat.upper()}</div>
                    <div style="color:#8b949e;font-size:.82rem;">Severity: <b style='color:#e6edf3'>{(row.get('severity') or '').upper()}</b></div>
                    <div style="color:#8b949e;font-size:.82rem;margin-top:4px;">Confidence: <b style='color:#58a6ff'>{row.get('triage_confidence') or 0:.0%}</b></div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown("**Test Generation**")
            test_gen = row.get("test_generated", False)
            status_text = 'Generated' if test_gen else 'Not Generated'
            icon_color = '#10b981' if test_gen else '#f85149'
            st.markdown(
                f"""
                <div style="background:#1f2937;border:1px solid #374151;border-radius:10px;padding:16px 20px;">
                    <div style="font-size:1.3rem;font-weight:700;margin-bottom:8px; display:flex; align-items:center; gap:8px;">
                        <b style="color:{icon_color}; font-size:1.2rem;">●</b> {status_text}
                    </div>
                    <div style="color:#9ca3af;font-size:.82rem;">Language: <b style='color:#f9fafb'>{row.get('test_language') or '—'}</b></div>
                    <div style="color:#9ca3af;font-size:.82rem;margin-top:4px;">Confidence: <b style='color:#10b981'>{(row.get('test_confidence') or 0):.0%}</b></div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Error signature
        sig = row.get("error_signature", "")
        if sig:
            st.markdown("**Error Signature**")
            st.code(sig, language="")

        # Files changed
        files = row.get("files_changed", [])
        if files:
            st.markdown("**Files Changed**")
            for f in files:
                st.markdown(f"&nbsp;&nbsp;`{f}`")

        # Flags
        flags = []
        if row.get("agent_fallback"):   flags.append("🔄 Agent regex fallback used")
        if row.get("issue_fallback"):   flags.append("💾 Issue saved locally (GitHub fallback)")
        if row.get("issue_filed"):      flags.append("✅ Issue filed")
        if row.get("has_eval"):         flags.append("📊 Eval scores present")
        if flags:
            st.markdown("**Flags**")
            for fl in flags:
                st.markdown(f"- {fl}")

        # Eval scores
        if row.get("has_eval"):
            st.markdown("**Eval Scores**")
            ec1, ec2, ec3, ec4 = st.columns(4)
            def _yn(v): return ":material/check_circle:" if v else ":material/cancel:"
            ec1.metric("Category Match", _yn(row.get("eval_category_match")))
            ec2.metric("Severity Match", _yn(row.get("eval_severity_match")))
            ec3.metric("Test Relevance", f"{(row.get('eval_test_relevance') or 0):.0%}")
            ec4.metric("Confidence OK",  _yn(row.get("eval_confidence_ok")))

    # Tab 2 – Node timings
    with t2:
        nd = row.get("node_durations_ms") or {}
        if isinstance(nd, str):
            try:
                nd = json.loads(nd)
            except Exception:
                nd = {}
        if nd:
            nd_df = pd.DataFrame(list(nd.items()), columns=["Node", "Duration (ms)"])
            nd_df = nd_df.sort_values("Duration (ms)", ascending=True)
            fig = go.Figure(go.Bar(
                y=nd_df["Node"], x=nd_df["Duration (ms)"],
                orientation="h",
                marker=dict(color="#58a6ff", line=dict(width=0)),
                text=nd_df["Duration (ms)"].map(lambda x: f"{x:.0f}ms"),
                textposition="outside",
            ))
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(family="Inter", color="#e6edf3"),
                margin=dict(l=0, r=60, t=10, b=10),
                xaxis=dict(gridcolor="#21262d"),
                yaxis=dict(gridcolor="#21262d"),
                height=280,
            )
            st.plotly_chart(fig, use_container_width=True, key="nd_bar")
        else:
            st.info("No node timing data available for this run.")

    # Tab 3 – Token breakdown
    with t3:
        tc = row.get("token_counts") or {}
        if isinstance(tc, str):
            try:
                tc = json.loads(tc)
            except Exception:
                tc = {}
        if tc:
            tc_df = pd.DataFrame(list(tc.items()), columns=["Key", "Tokens"])
            tc_df = tc_df.sort_values("Tokens", ascending=False)
            fig2 = go.Figure(go.Bar(
                x=tc_df["Key"], y=tc_df["Tokens"],
                marker=dict(color="#bc8cff", line=dict(width=0)),
                text=tc_df["Tokens"],
                textposition="outside",
            ))
            fig2.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(family="Inter", color="#e6edf3"),
                margin=dict(l=10, r=10, t=10, b=10),
                xaxis=dict(gridcolor="#21262d", tickangle=-30),
                yaxis=dict(gridcolor="#21262d"),
                height=300,
            )
            st.plotly_chart(fig2, use_container_width=True, key="tc_bar")
        else:
            st.info("No token count data available for this run.")
