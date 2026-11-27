"""Hunk context enrichment: attach real file content around each hunk.

Raw diffs blind a reviewer to the enclosing function, variable types and
callers — the measured cause of false positives. This module adds bounded
context from the actual file. Tree-sitter AST parsing is future work; the
Python heuristic (nearest def/class boundary) covers the common case.
"""

from pathlib import Path

MAX_CONTEXT_CHARS = 6000
WINDOW = 25


def _python_enclosing(lines: list[str], lineno: int) -> tuple[int, int]:
    """(start, end) 1-indexed of the nearest def/class containing lineno."""
    import re

    top = re.compile(r"^(\s*)(def |class |async def )")
    start = 1
    indent = None
    for i in range(min(lineno, len(lines)), 0, -1):
        m = top.match(lines[i - 1])
        if m:
            indent = len(m.group(1))
            start = i
            break
    if indent is None:
        return (max(1, lineno - WINDOW), min(len(lines), lineno + WINDOW))
    end = start
    for i in range(start + 1, len(lines) + 1):
        stripped = lines[i - 1].strip()
        if stripped and not stripped.startswith("#"):
            cur_indent = len(lines[i - 1]) - len(lines[i - 1].lstrip())
            if cur_indent <= indent and lines[i - 1].strip():
                break
        end = i
    return (start, min(end, len(lines)))


def _window(lines: list[str], lineno: int) -> tuple[int, int]:
    return (max(1, lineno - WINDOW), min(len(lines), lineno + WINDOW))


def _format(lines: list[str], start: int, end: int, marked: set[int]) -> str:
    out = []
    for i in range(start, end + 1):
        marker = ">" if i in marked else " "
        out.append(f"{marker} {i:4d} | {lines[i - 1]}")
    return "\n".join(out)


def enrich(path: Path, new_start: int, new_end: int) -> str:
    """Context text for a changed line range, or '' when unavailable."""
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return ""
    lines = text.splitlines()
    if not lines:
        return ""
    if path.suffix == ".py":
        start, end = _python_enclosing(lines, new_start)
    else:
        start, end = _window(lines, new_start)
    # widen to cover the whole hunk
    start = min(start, max(1, new_start))
    end = max(end, min(len(lines), new_end))
    body = _format(lines, start, end, marked=set(range(new_start, new_end + 1)))
    while len(body) > MAX_CONTEXT_CHARS and start < end:
        end -= 1
        body = _format(lines, start, end, marked=set(range(new_start, new_end + 1)))
    return body
