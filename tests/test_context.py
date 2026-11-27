"""Tests for diff parsing and context enrichment."""

from ollakit.review import context, diff

SAMPLE_DIFF = """diff --git a/db.py b/db.py
index a732fb9..b086d9e 100644
--- a/db.py
+++ b/db.py
@@ -1,4 +1,5 @@
 import sqlite3
+
 def get_user(conn, name):
     cur = conn.cursor()
     cur.execute("SELECT x")
diff --git a/util.py b/util.py
index 111..222 100644
--- a/util.py
+++ b/util.py
@@ -10,3 +10,4 @@
 def helper():
-    return 1
+    return 2
"""


def test_parse_diff_extracts_files_and_hunks():
    files = diff.parse_diff(SAMPLE_DIFF)
    assert [f.path for f in files] == ["db.py", "util.py"]
    assert len(files[0].hunks) == 1
    assert files[0].hunks[0].new_start == 1
    assert files[1].hunks[0].new_start == 10


def test_parse_diff_ignores_non_b_files():
    raw = "diff --git a/x.py b/x.py\n--- /dev/null\n+++ b/x.py\n@@ -0,0 +1 @@\n+new\n"
    files = diff.parse_diff(raw)
    assert files[0].path == "x.py"


def test_added_lines_are_marked():
    files = diff.parse_diff(SAMPLE_DIFF)
    added = files[0].hunks[0].added_lines()
    assert (2, "") in added  # the blank added line at new line 2


def test_context_python_enclosing_function(tmp_path):
    f = tmp_path / "db.py"
    f.write_text(
        "import sqlite3\n"
        "\n"
        "\n"
        "def get_user(conn, name):\n"
        "    cur = conn.cursor()\n"
        "    cur.execute('SELECT 1')\n"
        "    return cur.fetchone()\n"
        "\n"
        "\n"
        "def other():\n"
        "    pass\n"
    )
    ctx = context.enrich(f, new_start=6, new_end=6)
    assert "def get_user" in ctx
    assert "def other" not in ctx
    assert "6" in ctx  # line numbers present


def test_context_falls_back_to_window(tmp_path):
    f = tmp_path / "app.js"
    f.write_text("\n".join(f"// line {i}" for i in range(1, 101)) + "\n")
    ctx = context.enrich(f, new_start=50, new_end=50)
    assert "// line 50" in ctx
    assert "// line 1" not in ctx  # bounded window, not the whole file


def test_context_caps_size(tmp_path):
    f = tmp_path / "big.py"
    f.write_text("def big():\n" + "    x = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'\n" * 500)
    ctx = context.enrich(f, new_start=100, new_end=200)
    assert len(ctx) <= context.MAX_CONTEXT_CHARS + 100


def test_context_missing_file_returns_empty():
    from pathlib import Path

    assert context.enrich(Path("/nonexistent/file.py"), 1, 2) == ""
