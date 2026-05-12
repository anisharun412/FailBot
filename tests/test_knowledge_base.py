"""Tests for the known errors knowledge base."""

import json

from src.tools.knowledge_base import KnownErrorsDB


def test_load_preserves_patterns_key_and_saves_round_trip(tmp_path):
    db_path = tmp_path / "known_errors.json"
    db_path.write_text(
        json.dumps(
            {
                "patterns": [
                    {
                        "id": "py_type_error_001",
                        "signature": "TypeError: NoneType is not iterable",
                        "category": "code_bug",
                        "severity": "high",
                        "description": "Example",
                        "common_causes": ["missing guard"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    db = KnownErrorsDB(str(db_path))

    assert db.errors
    assert any(entry.get("id") == "py_type_error_001" for entry in db.errors)

    record = db.add_error(
        signature="ValueError: invalid literal",
        category="code_bug",
        severity="medium",
        description="Added test record",
        common_causes=["bad input"],
        save=True,
    )

    assert isinstance(record["id"], str)
    assert record["id"].startswith("custom_error_")

    saved = json.loads(db_path.read_text(encoding="utf-8"))
    assert "patterns" in saved
    assert len(saved["patterns"]) == 2
    assert any(entry.get("id", "").startswith("custom_error_") for entry in saved["patterns"])


def test_numeric_ids_increment_when_all_ids_are_ints(tmp_path):
    db_path = tmp_path / "known_errors.json"
    db_path.write_text(
        json.dumps(
            {
                "errors": [
                    {
                        "id": 1,
                        "signature": "Error A",
                        "category": "infra",
                        "severity": "low",
                        "description": "First",
                        "common_causes": [],
                    },
                    {
                        "id": 3,
                        "signature": "Error B",
                        "category": "infra",
                        "severity": "low",
                        "description": "Second",
                        "common_causes": [],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    db = KnownErrorsDB(str(db_path))
    record = db.add_error(
        signature="Error C",
        category="infra",
        severity="low",
        description="Third",
        common_causes=[],
        save=False,
    )

    assert record["id"] == 4
