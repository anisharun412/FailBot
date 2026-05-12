"""Run FailBot – submit a log file or URL and execute the pipeline from the dashboard."""

from __future__ import annotations
import asyncio
import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

import streamlit as st

# Project root on path
_ROOT = Path(__file__).resolve().parents[2]
logger = logging.getLogger(__name__)


def _card(content: str) -> None:
    st.markdown(
        f'<div class="fb-card">{content}</div>',
        unsafe_allow_html=True,
    )


def _step_row(icon: str, label: str, status: str, detail: str = "") -> str:
    dot_cls = {
        "done": "dot-done", "running": "dot-running",
        "waiting": "dot-waiting", "error": "dot-error",
    }.get(status, "dot-waiting")
    detail_html = f'<span style="color:#8b949e;font-size:.78rem;margin-left:6px;">{detail}</span>' if detail else ""
    return f'<div class="step-item"><div class="step-dot {dot_cls}"></div><div><span style="font-weight:600">{icon} {label}</span>{detail_html}</div></div>'


def _render_result(state: dict) -> None:
    """Render final state as a structured result card."""
    st.markdown("---")
    st.markdown("### :material/check_circle: Pipeline Complete — Results")

    status = state.get("status", "")
    cat    = state.get("failure_category", "—")
    sev    = state.get("severity", "—")
    conf   = state.get("triage_confidence")
    lang   = state.get("language", "—")
    test_gen  = state.get("test_generated") or bool(state.get("suggested_test"))
    test_lang = state.get("test_language", "—")
    issue_url = state.get("github_issue_url", "") or state.get("fallback_issue_path", "")
    errors    = state.get("errors", [])

    CATEGORY_COLORS = {
        "code_bug": "#f85149", "infra": "#e3b341",
        "flaky": "#bc8cff",    "unknown": "#8b949e",
    }
    SEVERITY_COLORS = {
        "critical": "#ff7b72", "high": "#f85149",
        "medium": "#e3b341",   "low": "#3fb950",
    }
    cat_color = CATEGORY_COLORS.get(cat, "#8b949e")
    sev_color = SEVERITY_COLORS.get(sev, "#8b949e")

    # KPIs
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Category",   cat.upper())
    k2.metric("Severity",   sev.upper())
    k3.metric("Confidence", f"{conf:.0%}" if conf else "—")
    k4.metric("Errors",     str(len(errors)))

    st.markdown("<br>", unsafe_allow_html=True)
    t1, t2, t3 = st.tabs(["🏷️ Triage", "🧪 Test / Fix", "📊 Raw State"])

    with t1:
        sig = state.get("error_signature", "")
        files = state.get("files_changed", [])
        triage_reasoning = state.get("triage_reasoning", "")
        st.markdown(
            f"""
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:16px;">
                <div style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:16px 20px;">
                    <div style="font-size:1.15rem;font-weight:700;color:{cat_color};margin-bottom:6px;">{cat.upper()}</div>
                    <div style="color:#8b949e;font-size:.82rem;">Failure category</div>
                </div>
                <div style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:16px 20px;">
                    <div style="font-size:1.15rem;font-weight:700;color:{sev_color};margin-bottom:6px;">{sev.upper()}</div>
                    <div style="color:#8b949e;font-size:.82rem;">Severity</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if triage_reasoning:
            st.markdown("**Triage Reasoning**")
            st.info(triage_reasoning)
        if sig:
            st.markdown("**Error Signature**")
            st.code(sig, language="")
        if files:
            st.markdown("**Files Changed**")
            for f in files:
                st.markdown(f"&nbsp;&nbsp;`{f}`")

    with t2:
        if test_gen:
            st.success(f"✅ Test generated in **{test_lang}**")
            test_code = state.get("suggested_test", "")
            test_desc = state.get("test_description", "")
            if test_desc:
                st.markdown(f"> {test_desc}")
            if test_code:
                lang_map = {"python": "python", "javascript": "javascript",
                            "typescript": "typescript", "java": "java", "strategy": ""}
                st.code(test_code, language=lang_map.get(test_lang, ""))
        else:
            st.warning("No test was generated for this run.")

        if issue_url:
            st.markdown("---")
            st.markdown(f"**📝 Issue:** `{issue_url}`")
            if not issue_url.startswith(("http://", "https://")):
                try:
                    issue_path = Path(issue_url)
                    resolved_path = issue_path.resolve()
                    allowed_base = (_ROOT / "runs").resolve()
                    if resolved_path.is_file() and resolved_path.is_relative_to(allowed_base):
                        content = resolved_path.read_text(encoding="utf-8")
                        with st.expander("View issue content"):
                            st.markdown(content)
                    else:
                        st.warning(f"Issue path is outside expected directory: {issue_url}")
                except (OSError, ValueError) as exc:
                    st.warning(f"Unable to read issue file: {exc}")

    with t3:
        # Show full state as formatted JSON (excluding large raw logs)
        display_state = {
            k: v for k, v in state.items()
            if k not in ("log_text_full", "log_text") and not callable(v)
        }
        st.json(display_state)

    # Token / timing summary
    if state.get("token_counts") or state.get("node_durations_ms"):
        st.markdown("---")
        mc1, mc2 = st.columns(2)
        with mc1:
            st.markdown("**Token Usage**")
            tc = state.get("token_counts") or {}
            for k, v in tc.items():
                st.markdown(f"&nbsp;&nbsp;`{k}`: **{v:,}**")
            total = state.get("total_tokens") or sum(tc.values())
            st.markdown(f"&nbsp;&nbsp;**Total: {total:,}**")
        with mc2:
            st.markdown("**Node Durations**")
            nd = state.get("node_durations_ms") or {}
            for k, v in nd.items():
                st.markdown(f"&nbsp;&nbsp;`{k}`: **{v:.0f}ms**")
            total_d = state.get("total_duration_ms") or sum(nd.values())
            st.markdown(f"&nbsp;&nbsp;**Total: {total_d:.0f}ms**")


def render_run_failbot() -> None:
    st.markdown("## ⚡ Pipeline Runner")
    st.markdown(
        '<p style="color:#9ca3af;font-size:.85rem;font-weight:500;">Submit a CI log to the analysis pipeline. '
        'The system will triage the failure, suggest a fix, and prepare a detailed report.</p>',
        unsafe_allow_html=True,
    )

    # ── Input form ────────────────────────────────────────────────────────────
    with st.expander("Configuration Settings", expanded=True):
        input_mode = st.radio(
            "Input Mode",
            ["📁 Upload File", "🔗 URL / Path"],
            horizontal=True,
            key="rf_input_mode",
        )

        uploaded_file = None
        log_source_str = ""

        if input_mode == "📁 Upload File":
            uploaded_file = st.file_uploader(
                "Select CI log file (.log, .txt)",
                type=["log", "txt", "out"],
                key="rf_upload",
                help="Accepts plain-text CI log files",
            )
            if uploaded_file:
                st.markdown(
                    f'<p style="color:#3fb950;font-size:.82rem;">✓ {uploaded_file.name} ({uploaded_file.size:,} bytes)</p>',
                    unsafe_allow_html=True,
                )
        else:
            log_source_str = st.text_input(
                "Log URL or file path",
                placeholder="https://github.com/.../logs/123  or  tests/test_log_files/my.log",
                key="rf_log_src",
            )

        c1, c2 = st.columns(2)
        repo_name = c1.text_input(
            "GitHub Repo (owner/repo)",
            value="unknown",
            placeholder="owner/repo",
            key="rf_repo",
            help="Used when filing GitHub issues",
        )
        output_dir = c2.text_input(
            "Output Directory",
            value="runs",
            key="rf_output",
            help="Where JSONL logs and summaries are saved",
        )

        config_path_str = st.text_input(
            "Config path (optional)",
            placeholder="config/prompts.yaml",
            key="rf_config",
            help="Leave blank to use default config",
        )
        verbose = st.checkbox("Verbose logging", key="rf_verbose")

    # Validation
    can_run = bool(uploaded_file or log_source_str.strip())

    if not can_run:
        st.info("Provide a log file or URL above, then click **Run FailBot**.", icon="💡")

    run_clicked = st.button(
        "▶ Execute Pipeline",
        disabled=not can_run,
        type="primary",
        key="rf_run_btn",
    )

    if not run_clicked:
        return

    # ── Execute pipeline ──────────────────────────────────────────────────────
    # Save uploaded file to a temp path if needed
    tmp_path: Optional[Path] = None
    if uploaded_file is not None:
        suffix = Path(uploaded_file.name).suffix or ".log"
        tmp = tempfile.NamedTemporaryFile(
            delete=False, suffix=suffix,
            prefix="failbot_upload_"
        )
        tmp.write(uploaded_file.read())
        tmp.close()
        tmp_path = Path(tmp.name)
        final_log_source = str(tmp_path)
    else:
        final_log_source = log_source_str.strip()

    config_path = config_path_str.strip() or None

    st.markdown("---")
    st.markdown("### ⏳ Running Pipeline…")

    # Step progress UI
    STEPS = [
        ("ingest",               "download",  "Ingest"),
        ("parse_log",            "analytics", "Parse Log"),
        ("triage",               "label",     "Triage"),
        ("test_or_strategy",     "science",   "Test / Strategy"),
        ("file_issue",           "history_edu", "File Issue"),
        ("report",               "summarize", "Report"),
    ]

    step_placeholder = st.empty()

    def _draw_steps(current_idx: int, done: bool = False, error: bool = False) -> None:
        html = ""
        for i, (sid, icon, label) in enumerate(STEPS):
            if i < current_idx:
                s = "done"
            elif i == current_idx and not done:
                s = "error" if error else "running"
            elif i == current_idx and done:
                s = "done"
            else:
                s = "waiting"
            html += _step_row("", label, s)
        step_placeholder.markdown(
            f'<div style="background:#1c2333;border:1px solid #30363d;'
            f'border-radius:12px;padding:16px 20px;">{html}</div>',
            unsafe_allow_html=True,
        )

    _draw_steps(0)
    status_box = st.empty()

    try:
        # Import pipeline
        status_box.markdown(
            '<p style="color:#8b949e;font-size:.82rem;">Importing pipeline modules…</p>',
            unsafe_allow_html=True,
        )
        os.chdir(str(_ROOT))

        from src.main import run_failbot

        _draw_steps(1)
        status_box.markdown(
            f'<p style="color:#8b949e;font-size:.82rem;">Starting pipeline for: <code>{final_log_source}</code></p>',
            unsafe_allow_html=True,
        )

        # Run the async pipeline
        t0 = time.time()
        final_state = asyncio.run(
            run_failbot(
                log_source=final_log_source,
                repo_name=repo_name or "unknown",
                config_path=config_path,
                output_dir=output_dir or "runs",
            )
        )
        elapsed = time.time() - t0

        # Show all steps done
        _draw_steps(len(STEPS) - 1, done=True)
        status_box.markdown(
            f'<p style="color:#3fb950;font-size:.85rem;">✓ Pipeline finished in <b>{elapsed:.1f}s</b></p>',
            unsafe_allow_html=True,
        )

        # Cache bust the data loader so new run appears in other pages
        from dashboard import data_loader
        data_loader.load_all_summaries.clear()

        # Render results
        _render_result(dict(final_state))

    except Exception as exc:
        _draw_steps(0, error=True)
        status_box.error(f"Pipeline failed: {exc}")
        st.exception(exc)
    finally:
        # Clean up temp file
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception as exc:
                logger.warning("Failed to clean up temp file %s: %s", tmp_path, exc)
