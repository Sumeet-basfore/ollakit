"""Tests for the linter pre-filter."""

import json

from ollakit.review import linters


def _fake_which(names):
    return lambda tool: f"/usr/bin/{tool}" if tool in names else None


def test_available_detects_only_installed(monkeypatch):
    monkeypatch.setattr(linters.shutil, "which", _fake_which({"ruff"}))
    assert linters.available() == ["ruff"]
    monkeypatch.setattr(linters.shutil, "which", _fake_which(set()))
    assert linters.available() == []


def test_run_ruff_parses_findings(monkeypatch):
    payload = json.dumps(
        [
            {
                "code": "F841",
                "message": "unused variable",
                "filename": "a.py",
                "location": {"row": 3, "column": 5},
            }
        ]
    )

    class R:
        returncode = 0
        stdout = payload
        stderr = ""

    monkeypatch.setattr(linters.subprocess, "run", lambda *a, **k: R())
    findings, note = linters.run("ruff", ["a.py"])
    assert note == ""
    assert findings == [
        {
            "tool": "ruff",
            "file": "a.py",
            "line": 3,
            "severity": "nit",
            "comment": "[ruff F841] unused variable",
            "patch": None,
        }
    ]


def test_run_failure_becomes_note_not_error(monkeypatch):
    class R:
        returncode = 2
        stdout = ""
        stderr = "boom"

    monkeypatch.setattr(linters.subprocess, "run", lambda *a, **k: R())
    findings, note = linters.run("ruff", ["a.py"])
    assert findings == [] and "exited 2" in note


def test_run_timeout_becomes_note(monkeypatch):
    def boom(*a, **k):
        raise linters.subprocess.TimeoutExpired(cmd="ruff", timeout=60)

    monkeypatch.setattr(linters.subprocess, "run", boom)
    findings, note = linters.run("ruff", ["a.py"])
    assert findings == [] and "failed" in note


def test_bandit_high_maps_to_critical(monkeypatch):
    payload = json.dumps(
        {
            "results": [
                {
                    "filename": "s.py",
                    "line_number": 4,
                    "issue_severity": "HIGH",
                    "test_id": "B105",
                    "issue_text": "hardcoded password",
                }
            ]
        }
    )

    class R:
        returncode = 1
        stdout = payload
        stderr = ""

    monkeypatch.setattr(linters.subprocess, "run", lambda *a, **k: R())
    findings, _ = linters.run("bandit", ["s.py"])
    assert findings[0]["severity"] == "critical"


def test_run_all_aggregates(monkeypatch):
    monkeypatch.setattr(linters, "available", lambda: ["ruff", "bandit"])
    monkeypatch.setattr(
        linters, "run", lambda tool, files: ([{"tool": tool}], [] if tool == "ruff" else "oops")
    )
    findings, notes = linters.run_all(["a.py"])
    assert [f["tool"] for f in findings] == ["ruff", "bandit"]
    assert notes == ["oops"]
