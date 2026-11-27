"""Tests for the quality gates."""

from pathlib import Path

from ollakit.review import gates


FILE_CONTENT = (
    "import sqlite3\n"
    "\n"
    "\n"
    "def get_user(conn, name):\n"
    "    cur = conn.cursor()\n"
    "    cur.execute('SELECT * FROM users WHERE name = ?', (name,))\n"
    "    return cur.fetchone()\n"
)


def _finding(**kw):
    base = {
        "file": "db.py",
        "line": 6,
        "severity": "critical",
        "comment": "SQL injection via string formatting",
        "suggested_patch": "cur.execute(q, (name,))",
        "failure_mode": "attacker controls name",
        "category": "security",
    }
    base.update(kw)
    return base


def test_actionable_passes_concrete_finding():
    assert gates.actionable(_finding()) is True


def test_actionable_drops_missing_line():
    assert gates.actionable(_finding(line=None)) is False


def test_actionable_drops_vague_without_patch():
    assert gates.actionable(_finding(comment="consider refactoring this", suggested_patch=None)) is False


def test_judge_verifies_against_real_content(monkeypatch):
    responses = iter(['{"factually_correct": true}'])

    def fake_chat(model, msgs, json_mode=False):
        return next(responses)

    monkeypatch.setattr(gates.client, "chat", fake_chat)
    ok, why = gates.fact_check(_finding(), FILE_CONTENT)
    assert ok is True
    assert "does not quote the code" not in why


def test_judge_drops_fabricated_finding(monkeypatch):
    def fake_chat(model, msgs, json_mode=False):
        return '{"factually_correct": false, "rationale": "line 6 uses parameterized query"}'

    monkeypatch.setattr(gates.client, "chat", fake_chat)
    # the finding claims string formatting but the code is parameterized
    ok, why = gates.fact_check(_finding(), FILE_CONTENT)
    assert ok is False
    assert "parameterized" in why


def test_judge_unparseable_defaults_to_drop(monkeypatch):
    monkeypatch.setattr(gates.client, "chat", lambda *a, **k: "not json")
    ok, why = gates.fact_check(_finding(), FILE_CONTENT)
    assert ok is False


def test_apply_gates_runs_judge_and_counts(monkeypatch, tmp_path):
    (tmp_path / "db.py").write_text(FILE_CONTENT)
    monkeypatch.setattr(
        gates, "fact_check", lambda f, content: (f["comment"] != "vague one", "ok")
    )
    candidates = [
        _finding(),
        _finding(comment="vague one", suggested_patch=None),
    ]
    kept, stats = gates.apply_gates(candidates, root=tmp_path)
    assert len(kept) == 1
    assert stats["hallucination_dropped"] == 0
    assert stats["actionability_dropped"] == 1


def test_apply_gates_caps_and_ranks(monkeypatch, tmp_path):
    (tmp_path / "db.py").write_text(FILE_CONTENT)
    monkeypatch.setattr(gates, "fact_check", lambda f, c: (True, "ok"))
    candidates = [
        _finding(severity="nit", category="quality", line=6, comment=f"nit {i}")
        for i in range(4)
    ] + [_finding(category="security", comment="the real bug")]
    kept, stats = gates.apply_gates(candidates, root=tmp_path, cap=5)
    # security first despite arriving last
    assert kept[0]["category"] == "security"
    assert len(kept) == 5
    assert stats["capped"] == 0


def test_apply_gates_suppresses_below_cap(monkeypatch, tmp_path):
    (tmp_path / "db.py").write_text(FILE_CONTENT)
    monkeypatch.setattr(gates, "fact_check", lambda f, c: (True, "ok"))
    candidates = [_finding(comment=f"f{i}", line=i + 1) for i in range(8)]
    kept, stats = gates.apply_gates(candidates, root=tmp_path, cap=5)
    assert len(kept) == 5
    assert stats["capped"] == 3


def test_rank_order_security_before_quality():
    findings = [
        _finding(category="quality", severity="nit"),
        _finding(category="security", severity="critical"),
    ]
    ranked = gates.rank(findings)
    assert ranked[0]["category"] == "security"
