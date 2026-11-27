"""Tests for the handoff module: report rendering and agent fix prompts."""

from ollakit.review import handoff

FINDINGS = [
    {
        "file": "db.py",
        "line": 6,
        "severity": "critical",
        "comment": "SQL injection via string formatting",
        "suggested_patch": "cur.execute('SELECT * FROM users WHERE name = ?', (name,))",
        "failure_mode": "If name contains a quote, the query breaks or executes attacker SQL.",
        "category": "security",
    },
    {
        "file": "db.py",
        "line": 12,
        "severity": "nit",
        "comment": "unused import",
        "suggested_patch": None,
        "failure_mode": None,
        "category": "quality",
    },
]


def test_render_terminal_groups_by_severity(capsys):
    handoff.render_terminal(FINDINGS, stats={"candidates": 4, "hallucination_dropped": 1,
                                             "actionability_dropped": 1, "capped": 0})
    out = capsys.readouterr().out
    assert "db.py:6" in out and "critical" in out
    assert "db.py:12" in out and "nit" in out
    assert "1 hallucination" in out or "hallucination" in out


def test_report_markdown_contains_all_sections():
    md = handoff.report_markdown(FINDINGS, stats={"candidates": 4, "hallucination_dropped": 1,
                                                  "actionability_dropped": 1, "capped": 0},
                                 linter_findings=[], linter_notes=[])
    assert "## Findings" in md
    assert "suggested_patch" in md or "```" in md
    assert "Suppressed" in md
    assert "SQL injection" in md


def test_report_includes_linter_section():
    lf = [{"tool": "ruff", "file": "a.py", "line": 1, "severity": "nit", "comment": "[ruff F841] x"}]
    md = handoff.report_markdown(FINDINGS, stats={}, linter_findings=lf, linter_notes=["bandit failed"])
    assert "## Linters" in md and "ruff" in md and "bandit failed" in md


def test_fix_prompt_is_paste_ready():
    md = handoff.fix_prompt(FINDINGS[:1], file_contents={"db.py": FILE_SNIPPET})
    for marker in ("Goal", "db.py", "SQL injection", "Acceptance", "Verification"):
        assert marker in md, f"missing {marker}"
    assert "cur.execute('SELECT * FROM users WHERE name = ?'" in md


FILE_SNIPPET = (
    "import sqlite3\n\n\ndef get_user(conn, name):\n    cur = conn.cursor()\n"
    "    cur.execute(\"SELECT * FROM users WHERE name = '%s'\" % name)\n"
    "    return cur.fetchone()\n"
)


def test_fix_prompt_all_combines_and_mentions_files():
    md = handoff.fix_prompt_all(FINDINGS, file_contents={"db.py": FILE_SNIPPET})
    # one combined brief containing every finding
    assert md.count("## Findings") == 1
    assert "SQL injection" in md and "unused import" in md
    assert "db.py" in md


def test_fix_prompt_includes_file_code():
    md = handoff.fix_prompt(FINDINGS[:1], file_contents={"db.py": FILE_SNIPPET})
    assert "def get_user" in md
