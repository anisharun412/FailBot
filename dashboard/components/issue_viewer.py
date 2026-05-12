"""Issue Viewer – browse generated issue markdown files."""

from __future__ import annotations
import streamlit as st
from pathlib import Path

from dashboard.data_loader import list_issue_files, read_issue_file, RUNS_DIR


SEVERITY_COLORS = {
    "HIGH":     "#f85149",
    "CRITICAL": "#ff7b72",
    "MEDIUM":   "#e3b341",
    "LOW":      "#3fb950",
}


def _parse_issue_meta(filename: str) -> dict:
    """Extract severity and a short title from the issue filename."""
    name = filename.replace("issue_", "").replace(".md", "")
    parts = name.split("_")
    # Format: timestamp_SEVERITY_...
    meta = {"timestamp": "", "severity": "UNKNOWN", "title": filename}
    if len(parts) >= 2:
        meta["timestamp"] = parts[0]
        sev_raw = parts[1].upper() if len(parts) > 1 else ""
        if sev_raw in SEVERITY_COLORS:
            meta["severity"] = sev_raw
            meta["title"] = " ".join(parts[2:]).replace("_", " ")
        else:
            meta["title"] = " ".join(parts[1:]).replace("_", " ")
    return meta


def render_issue_viewer() -> None:
    st.markdown("## 📋 Issue Viewer")

    issue_files = list_issue_files()

    if not issue_files:
        st.info("No issue files found in `runs/`. Run the pipeline to generate issues.")
        return

    # ── Sidebar filter ────────────────────────────────────────────────────────
    col_list, col_detail = st.columns([1, 2])

    with col_list:
        st.markdown(f"**{len(issue_files)} issue(s) found**")

        sev_filter = st.selectbox(
            "Filter by severity:",
            ["All", "CRITICAL", "HIGH", "MEDIUM", "LOW"],
            key="iv_sev_filter",
        )
        search_term = st.text_input("Search title:", placeholder="e.g. ConnectionError", key="iv_search")

        def _matches(f: Path) -> bool:
            meta = _parse_issue_meta(f.name)
            if sev_filter != "All" and meta["severity"] != sev_filter:
                return False
            if search_term and search_term.lower() not in f.name.lower():
                return False
            return True

        filtered = [f for f in issue_files if _matches(f)]

        if not filtered:
            st.warning("No issues match current filter.")
            return

        # Build display labels
        labels = []
        for f in filtered:
            meta = _parse_issue_meta(f.name)
            color = SEVERITY_COLORS.get(meta["severity"], "#8b949e")
            labels.append(f"[{meta['severity']}] {meta['title'][:45]}")

        sel_idx   = st.radio("Issues:", list(range(len(labels))),
                             format_func=lambda i: labels[i],
                             label_visibility="collapsed", key="iv_radio")
        sel_file  = filtered[sel_idx]

    with col_detail:
        meta = _parse_issue_meta(sel_file.name)
        color = SEVERITY_COLORS.get(meta["severity"], "#8b949e")

        st.markdown(
            f"""
            <div style="background:#1c2333;border:1px solid #30363d;border-radius:12px;
                        padding:16px 20px;margin-bottom:16px;">
                <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;">
                    <span style="padding:3px 10px;border-radius:20px;font-size:.75rem;font-weight:600;
                                 background:rgba(88,166,255,.15);color:{color};">
                        {meta['severity']}
                    </span>
                    <span style="color:#8b949e;font-size:.78rem;">{sel_file.name}</span>
                </div>
                <div style="color:#f9fafb;font-size:.88rem; display:flex; align-items:center; gap:6px;">
                    📅 Created: <b>{meta['timestamp']}</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        content = read_issue_file(sel_file)
        if content:
            st.markdown(content, unsafe_allow_html=False)
        else:
            st.error("Could not read the issue file.")

        # Download button
        st.download_button(
            label="⬇️ Download Issue Markdown",
            data=content,
            file_name=sel_file.name,
            mime="text/markdown",
            key="iv_download",
        )
