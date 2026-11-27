"""Tests for constrained generation."""

from ollakit.review import generate

def test_to_findings_normalizes_new_schema():
    raw = '{"file": "a.py", "line": 3, "severity": "HIGH", "comment": "sql injection", "suggested_patch": "cur.execute(q, p)", "failure_mode": "attacker controls name", "category": "security"}'
    findings = generate.to_findings(raw)
    assert findings == [
        {
            "file": "a.py",
            "line": 3,
            "severity": "critical",
            "comment": "sql injection",
            "suggested_patch": "cur.execute(q, p)",
            "failure_mode": "attacker controls name",
            "category": "security",
        }
    ]

def test_to_findings_defaults_optional_fields():
    raw = '[{"file": "b.py", "comment": "x", "severity": "nit"}]'
    findings = generate.to_findings(raw)
    assert findings[0]["suggested_patch"] is None
    assert findings[0]["failure_mode"] is None
    assert findings[0]["category"] == "quality"

def test_to_findings_drops_rows_without_comment():
    assert generate.to_findings('[{"file": "c.py"}, "junk"]') == []

def test_build_user_prompt_contains_context_and_hunks_and_linter_note():
    prompt = generate.build_user_prompt(
        path="db.py",
        context_text="> 4 | def get_user(conn, name):",
        hunk_text="@@ -1,4 +1,5 @@\n+cur.execute('x' % name)",
        linter_note="[bandit B608] string-formatted SQL",
    )
    assert "db.py" in prompt
    assert "def get_user" in prompt
    assert "cur.execute" in prompt
    assert "[bandit B608]" in prompt
    assert "already reported" in prompt  # model told not to repeat linters

def test_build_user_prompt_without_linters():
    prompt = generate.build_user_prompt("a.py", "ctx", "@@ +1 @@\n+x", None)
    assert "already reported" not in prompt

def test_collect_findings_fast_uses_raw_diff(monkeypatch):
    import ollakit.review as review_pkg

    monkeypatch.setattr(
        generate.client,
        "chat",
        lambda model, msgs, json_mode=False: '[{"file": "a.py", "comment": "x", "severity": "warn"}]',
    )
    findings = generate.collect_findings_fast("diff --git a/a.py b/a.py\n+x", "m")
    assert len(findings) == 1
