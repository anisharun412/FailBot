"""Tests for CLI exit status mapping."""

import sys

import pytest

import src.main as main_module


def test_main_exits_zero_for_report_complete(monkeypatch):
    async def fake_run_failbot(**kwargs):
        return {"status": "report_complete", "errors": []}

    monkeypatch.setattr(main_module, "run_failbot", fake_run_failbot)
    monkeypatch.setattr(main_module, "print_summary", lambda state: None)
    monkeypatch.setattr(sys, "argv", ["failbot", "--log-source", "https://example.com/log.txt", "--repo", "owner/repo"])

    with pytest.raises(SystemExit) as exc:
        main_module.main()

    assert exc.value.code == 0


def test_main_exits_zero_for_file_issue_complete(monkeypatch):
    async def fake_run_failbot(**kwargs):
        return {"status": "file_issue_complete", "errors": []}

    monkeypatch.setattr(main_module, "run_failbot", fake_run_failbot)
    monkeypatch.setattr(main_module, "print_summary", lambda state: None)
    monkeypatch.setattr(sys, "argv", ["failbot", "--log-source", "https://example.com/log.txt", "--repo", "owner/repo"])

    with pytest.raises(SystemExit) as exc:
        main_module.main()

    assert exc.value.code == 0
