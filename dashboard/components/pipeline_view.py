"""Pipeline View – visualise the FailBot LangGraph topology and aggregate node stats."""

from __future__ import annotations
import json
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


PIPELINE_NODES = [
    ("ingest",              "Ingest",              "Fetches & truncates the log"),
    ("parse_log",           "Parse Log",           "LLM parses error signature, language, files"),
    ("triage",              "Triage",              "Classifies failure_category & severity"),
    ("suggest_test",        "Suggest Test",        "Generates targeted test code (code_bug)"),
    ("suggest_test_generic","Generic Test",        "Generates strategy (flaky / infra)"),
    ("file_issue",          "File Issue",          "Creates GitHub issue or local markdown"),
    ("report",              "Report",              "Writes summary JSON & JSONL log"),
]

EDGES = [
    ("ingest",    "parse_log"),
    ("parse_log", "triage"),
    ("triage",    "suggest_test"),
    ("triage",    "suggest_test_generic"),
    ("triage",    "file_issue"),  # unknown
    ("suggest_test",         "file_issue"),
    ("suggest_test_generic", "file_issue"),
    ("file_issue", "report"),
]

NODE_X = {
    "ingest":               0.10,
    "parse_log":            0.28,
    "triage":               0.46,
    "suggest_test":         0.64,
    "suggest_test_generic": 0.64,
    "file_issue":           0.82,
    "report":               0.97,
}
NODE_Y = {
    "ingest":               0.50,
    "parse_log":            0.50,
    "triage":               0.50,
    "suggest_test":         0.72,
    "suggest_test_generic": 0.28,
    "file_issue":           0.50,
    "report":               0.50,
}


def _aggregate_node_stats(df: pd.DataFrame) -> dict:
    """Compute mean duration per node across all runs."""
    totals: dict = {}
    counts: dict = {}
    for _, row in df.iterrows():
        nd = row.get("node_durations_ms") or {}
        if isinstance(nd, str):
            try:
                nd = json.loads(nd)
            except Exception:
                continue
        for node, ms in nd.items():
            totals[node] = totals.get(node, 0) + float(ms)
            counts[node] = counts.get(node, 0) + 1
    return {k: totals[k] / counts[k] for k in totals}


def render_pipeline_view(df: pd.DataFrame) -> None:
    st.markdown("## 🔗 Pipeline View")
    st.markdown(
        '<p style="color:#8b949e;font-size:.85rem;">Visual map of the FailBot LangGraph pipeline with aggregate node timing data.</p>',
        unsafe_allow_html=True,
    )

    # ── Node topology diagram ─────────────────────────────────────────────────
    avg_ms = _aggregate_node_stats(df) if not df.empty else {}

    node_ids   = [n[0] for n in PIPELINE_NODES]
    node_labels= []
    for nid, label, _ in PIPELINE_NODES:
        ms = avg_ms.get(nid)
        if ms:
            node_labels.append(f"{label}<br><span style='font-size:9px'>{ms:.0f}ms avg</span>")
        else:
            node_labels.append(label)

    # Build edge traces
    edge_x, edge_y = [], []
    for src, dst in EDGES:
        x0, y0 = NODE_X[src], NODE_Y[src]
        x1, y1 = NODE_X[dst], NODE_Y[dst]
        edge_x += [x0, x1, None]
        edge_y += [y0, y1, None]

    fig = go.Figure()

    # Edges
    fig.add_trace(go.Scatter(
        x=edge_x, y=edge_y,
        mode="lines",
        line=dict(color="#30363d", width=1.5),
        hoverinfo="none",
        showlegend=False,
    ))

    # Nodes
    node_x = [NODE_X[n] for n in node_ids]
    node_y = [NODE_Y[n] for n in node_ids]

    fig.add_trace(go.Scatter(
        x=node_x, y=node_y,
        mode="markers+text",
        text=[lbl.split("<br>")[0] for lbl in node_labels],
        textposition="bottom center",
        textfont=dict(size=11, color="#e6edf3"),
        marker=dict(
            size=36,
            color="#1e3a5f",
            line=dict(color="#58a6ff", width=2),
        ),
        hovertext=[f"<b>{lbl.replace('<br>', ' ')}</b><br>{desc}"
                   for (_, lbl, desc), lbl2 in zip(PIPELINE_NODES, node_labels)],
        hoverinfo="text",
        showlegend=False,
    ))

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter", color="#e6edf3"),
        margin=dict(l=10, r=10, t=20, b=60),
        height=340,
        xaxis=dict(showgrid=False, zeroline=False, visible=False, range=[-0.02, 1.08]),
        yaxis=dict(showgrid=False, zeroline=False, visible=False, range=[-0.05, 1.05]),
    )
    st.plotly_chart(fig, use_container_width=True, key="pipeline_fig")

    # ── Node reference table ──────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**Node Reference**")
    rows = []
    for nid, label, desc in PIPELINE_NODES:
        ms = avg_ms.get(nid)
        rows.append({
            "Node":           label,
            "ID":             nid,
            "Description":    desc,
            "Avg Duration":   f"{ms:.0f}ms" if ms else "—",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ── Routing logic explanation ─────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**Conditional Routing (after Triage)**")
    st.markdown(
        """
        | `failure_category` | Next Node |
        |---|---|
        | `code_bug` | → **suggest_test** (generates targeted unit test) |
        | `flaky` | → **suggest_test_generic** (generates retry/stability strategy) |
        | `infra` | → **suggest_test_generic** (generates infra resilience strategy) |
        | `unknown` | → **file_issue** directly (no test generated) |
        """
    )

    # ── Per-node average timing bar ──────────────────────────────────────────
    if avg_ms:
        st.markdown("---")
        st.markdown("**Average Node Duration Across All Runs**")
        nd_df = pd.DataFrame(list(avg_ms.items()), columns=["Node", "Avg ms"])
        nd_df = nd_df.sort_values("Avg ms", ascending=True)
        fig2 = go.Figure(go.Bar(
            y=nd_df["Node"],
            x=nd_df["Avg ms"],
            orientation="h",
            marker=dict(
                color=nd_df["Avg ms"],
                colorscale=[[0, "#1e3a5f"], [1, "#58a6ff"]],
                line=dict(width=0),
            ),
            text=nd_df["Avg ms"].map(lambda x: f"{x:.0f}ms"),
            textposition="outside",
        ))
        fig2.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter", color="#e6edf3"),
            margin=dict(l=10, r=60, t=10, b=10),
            xaxis=dict(gridcolor="#21262d"),
            yaxis=dict(gridcolor="#21262d"),
            height=300,
        )
        st.plotly_chart(fig2, use_container_width=True, key="avg_node_bar")
