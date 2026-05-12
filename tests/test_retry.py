"""Tests for retry helpers."""

import pytest

from src.utils.retry import PermanentError, sync_retry


def test_sync_retry_uses_sleep_and_retries(monkeypatch):
    calls = {"count": 0, "sleep": []}

    def fake_sleep(delay):
        calls["sleep"].append(delay)

    monkeypatch.setattr("src.utils.retry.time.sleep", fake_sleep)

    @sync_retry(max_attempts=3, initial_delay=0.1, max_delay=1.0, backoff_factor=2.0, jitter=False)
    def flaky_operation():
        calls["count"] += 1
        if calls["count"] < 2:
            raise ConnectionError("temporary failure")
        return "ok"

    assert flaky_operation() == "ok"
    assert calls["count"] == 2
    assert calls["sleep"] == [0.1]


def test_sync_retry_does_not_retry_permanent_error(monkeypatch):
    calls = {"count": 0, "sleep": []}

    def fake_sleep(delay):
        calls["sleep"].append(delay)

    monkeypatch.setattr("src.utils.retry.time.sleep", fake_sleep)

    @sync_retry(max_attempts=3, initial_delay=0.1, max_delay=1.0, jitter=False)
    def failing_operation():
        calls["count"] += 1
        raise PermanentError("do not retry")

    with pytest.raises(PermanentError):
        failing_operation()

    assert calls["count"] == 1
    assert calls["sleep"] == []
