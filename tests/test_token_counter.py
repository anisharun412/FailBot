"""Unit tests for token counting and truncation."""

from src.utils.token_counter import TokenCounter


class _DummyEncoding:
    def encode(self, text: str) -> list[int]:
        return list(range(len(text.split())))

    def decode(self, tokens: list[int]) -> str:
        return "|".join(str(token) for token in tokens)


def test_count_tokens_empty():
    counter = TokenCounter("gpt-4o-mini")
    assert counter.count_tokens("") == 0


def test_truncate_no_change():
    counter = TokenCounter("gpt-4o-mini")
    text = "hello world"
    truncated, reason = counter.truncate_to_limit(text, max_tokens=200)
    assert truncated == text
    assert reason == ""


def test_truncate_head_tail():
    counter = TokenCounter("gpt-4o-mini")
    text = "word " * 2000
    truncated, reason = counter.truncate_to_limit(text, max_tokens=50)
    assert "TRUNCATED" in truncated
    assert "head+tail" in reason


def test_truncate_head_tail_clamps_small_limits():
    counter = TokenCounter("gpt-4o-mini")
    counter.encoding = _DummyEncoding()
    text = " ".join(f"tok{i}" for i in range(600))

    truncated, reason = counter.truncate_to_limit(text, max_tokens=1)

    assert "TRUNCATED" in truncated
    assert "head+tail" in reason
    assert "599" in truncated
    assert "tok0" not in truncated
