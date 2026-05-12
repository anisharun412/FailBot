"""
FailBot Monitoring Dashboard
Streamlit app for visualizing FailBot pipeline runs, eval scores, and system health.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st

st.set_page_config(
    page_title="FailBot Dashboard",
    page_icon=":material/terminal:",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Load custom CSS
with open(os.path.join(os.path.dirname(__file__), "style.css")) as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

from dashboard.components.sidebar import render_sidebar
from dashboard.components.overview import render_overview
from dashboard.components.run_explorer import render_run_explorer
from dashboard.components.eval_dashboard import render_eval_dashboard
from dashboard.components.issue_viewer import render_issue_viewer
from dashboard.components.pipeline_view import render_pipeline_view
from dashboard.components.run_failbot import render_run_failbot
from dashboard.data_loader import load_all_summaries, load_eval_summary

# ── Sidebar navigation ──────────────────────────────────────────────────────
page = render_sidebar()

# ── Data loading (cached) ───────────────────────────────────────────────────
summaries = load_all_summaries()
eval_data  = load_eval_summary()

# ── Page routing ────────────────────────────────────────────────────────────
if page == "Run Pipeline":
    render_run_failbot()
elif page == "Overview":
    render_overview(summaries)
elif page == "Run Explorer":
    render_run_explorer(summaries)
elif page == "Eval Dashboard":
    render_eval_dashboard(eval_data, summaries)
elif page == "Issue Viewer":
    render_issue_viewer()
elif page == "Pipeline View":
    render_pipeline_view(summaries)
