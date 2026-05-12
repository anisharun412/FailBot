"""Small runner to launch the Streamlit dashboard from an installed package entrypoint.

This script calls the local `streamlit` CLI to run the dashboard app.
It is intentionally minimal and uses subprocess so Streamlit's own runner handles the server.
"""
from __future__ import annotations
import os
import shutil
import subprocess
import sys


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = list(sys.argv[1:])
    else:
        argv = list(argv)

    # Ensure streamlit is available
    streamlit_cmd = shutil.which("streamlit")
    if not streamlit_cmd:
        print("Error: `streamlit` not found in PATH. Install the dashboard extras: `pip install .[dashboard]`", file=sys.stderr)
        return 2

    # Default to dashboard/app.py in project root
    proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app_path = os.path.join(proj_root, "dashboard", "app.py")
    if not os.path.exists(app_path):
        print(f"Error: dashboard app not found at {app_path}", file=sys.stderr)
        return 3

    cmd = [streamlit_cmd, "run", app_path] + argv
    try:
        return subprocess.call(cmd)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
