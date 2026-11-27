import subprocess

import pytest

from ollakit import review


def test_get_diff_staged():
    diff = subprocess.run(
        ["git", "diff", "--staged"], capture_output=True, text=True, cwd="."
    )
    assert diff.returncode == 0


def test_split_diff_by_file_keeps_headers():
    raw = (
        "diff --git a/a.py b/a.py\nindex 111..222 100644\n--- a/a.py\n+++ b/a.py\n"
        "@@ -1 +1 @@\n-x = 1\n+x = 2\n"
        "diff --git a/b.py b/b.py\nindex 333..444 100644\n--- a/b.py\n+++ b/b.py\n"
        "@@ -1 +1 @@\n-y = 1\n+y = 2\n"
    )
    chunks = review.split_diff(raw, max_chars=60)
    assert len(chunks) == 2
    assert chunks[0].startswith("diff --git a/a.py")
    assert "b.py" in chunks[1]


def test_split_diff_merges_small_files():
    raw = (
        "diff --git a/a.py b/a.py\n@@ -1 +1 @@\n-x\n+x\n"
        "diff --git a/b.py b/b.py\n@@ -1 +1 @@\n-y\n+y\n"
    )
    chunks = review.split_diff(raw, max_chars=10_000)
    assert len(chunks) == 1


def test_summarize_findings_counts_severities():
    findings = [
        {"file": "a.py", "line": 1, "severity": "critical", "comment": "sql injection"},
        {"file": "b.py", "line": 2, "severity": "nit", "comment": "naming"},
    ]
    assert review.has_critical(findings) is True
    assert review.has_critical([]) is False


def test_render_findings_groups_by_file(capsys):
    findings = [
        {"file": "a.py", "line": 1, "severity": "critical", "comment": "bad"},
        {"file": "a.py", "line": 5, "severity": "nit", "comment": "ok-ish"},
    ]
    review.render(findings)
    out = capsys.readouterr().out
    assert "a.py:1" in out
    assert "a.py:5" in out
    assert "CRITICAL" in out


def test_run_exits_zero_on_clean_diff(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "f.py").write_text("x = 1\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "f.py"], check=True)
    monkeypatch.setattr(review, "get_diff", lambda args: "")
    assert review.run(review.build_args([])) == 0


def test_run_exit_code_reflects_critical(monkeypatch):
    fake = [{"file": "a.py", "line": 1, "severity": "critical", "comment": "boom",
             "suggested_patch": None, "failure_mode": None, "category": "correctness"}]
    monkeypatch.setattr(review, "get_diff", lambda args: "diff --git a/a.py b/a.py\n+x=1")
    monkeypatch.setattr(review, "collect_findings", lambda diff, model: fake)
    assert review.run(review.build_args(["--fast"])) == 1

    monkeypatch.setattr(review, "collect_findings", lambda diff, model: [])
    assert review.run(review.build_args(["--fast"])) == 0


def _full_finding(comment="c"):
    return {"file": "a.py", "line": 1, "severity": "critical", "comment": comment,
            "suggested_patch": None, "failure_mode": None, "category": "quality"}


def test_model_findings_parsed_and_validated():
    raw = '[{"file": "a.py", "line": 1, "severity": "critical", "comment": "c"}]'
    assert review.to_findings(raw) == [_full_finding()]
    # a bare object (no array) is accepted; severity synonyms map onto the enum
    raw2 = '{"file": "a.py", "severity": "high", "comment": "secret key"}'
    expected2 = _full_finding("secret key") | {"line": None}
    assert review.to_findings(raw2) == [expected2]
    # garbage severity is coerced to nit, non-dict rows dropped
    raw3 = '[{"file": "a.py", "severity": "banana", "comment": "x"}, "junk"]'
    expected3 = _full_finding("x") | {"line": None, "severity": "nit"}
    assert review.to_findings(raw3) == [expected3]


def test_install_hook_bakes_absolute_path(tmp_path, monkeypatch):
    import shutil as sh
    from pathlib import Path as P

    repo = tmp_path
    (repo / ".git" / "hooks").mkdir(parents=True)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(sh, "which", lambda name: "/venv/bin/ollakit")
    review.install_hook()
    hook = (repo / ".git" / "hooks" / "pre-commit").read_text()
    assert '"/venv/bin/ollakit"' in hook
    assert sh.which("ollakit") == "/venv/bin/ollakit"  # sanity on the stub
