"""Unified diff fetching and hunk parsing for ollakit review."""

import subprocess
from dataclasses import dataclass, field

MAX_DIFF_CHARS = 120_000


@dataclass
class Hunk:
    old_start: int
    new_start: int
    lines: list[str] = field(default_factory=list)

    def added_lines(self) -> list[tuple[int, str]]:
        """(new-file line number, text) for added lines."""
        out = []
        lineno = self.new_start
        for line in self.lines:
            if line.startswith("+"):
                out.append((lineno, line[1:]))
                lineno += 1
            elif line.startswith("-"):
                pass
            else:  # context line
                lineno += 1
        return out

    def new_end(self) -> int:
        count = sum(1 for l in self.lines if not l.startswith("-"))
        return self.new_start + max(count - 1, 0)


@dataclass
class FileDiff:
    path: str
    hunks: list[Hunk] = field(default_factory=list)

    def added_lines(self) -> list[tuple[int, str]]:
        return [x for h in self.hunks for x in h.added_lines()]

    def spans(self) -> list[tuple[int, int]]:
        return [(h.new_start, h.new_end()) for h in self.hunks]


def get_diff(args) -> str:
    if args.branch:
        cmd = ["git", "diff", f"{args.branch}...HEAD"]
    else:
        cmd = ["git", "diff", "--staged"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"git diff failed: {result.stderr.strip()}")
    return result.stdout


def parse_diff(raw: str) -> list[FileDiff]:
    files: list[FileDiff] = []
    current: FileDiff | None = None
    hunk: Hunk | None = None
    for line in raw.splitlines():
        if line.startswith("diff --git "):
            current = FileDiff(path="?")
            files.append(current)
            hunk = None
        elif line.startswith("+++ ") and current is not None:
            path = line[4:].strip()
            if path.startswith("b/"):
                path = path[2:]
            current.path = path
        elif line.startswith("@@") and current is not None:
            # @@ -old,count +new,count @@
            try:
                plus = line.split("+", 1)[1].split(" ", 1)[0]
                new_start = int(plus.split(",")[0])
            except (IndexError, ValueError):
                new_start = 1
            hunk = Hunk(old_start=0, new_start=new_start)
            current.hunks.append(hunk)
        elif hunk is not None and current is not None:
            if line.startswith("\\"):  # "\ No newline at end of file"
                continue
            hunk.lines.append(line)
    return files


def split_diff(raw: str, max_chars: int = 40_000) -> list[str]:
    if len(raw) <= max_chars:
        return [raw]
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for line in raw.splitlines(keepends=True):
        if line.startswith("diff --git ") and size > max_chars // 2:
            chunks.append("".join(current))
            current, size = [], 0
        current.append(line)
        size += len(line)
    if current:
        chunks.append("".join(current))
    return chunks
