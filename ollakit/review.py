"""ollakit review: review a git diff with a local Ollama model."""

import subprocess
import sys

from . import client

MAX_CHUNK_CHARS = 40_000

SYSTEM_PROMPT = (
    "You are a strict code reviewer. Review the unified diff and output ONLY a JSON array of "
    "findings, each: {\"file\": str, \"line\": int|null, \"severity\": \"critical\"|\"warn\"|\"nit\", "
    "\"comment\": str}. critical = bug, security issue, data loss, or ANY hardcoded credential "
    "(API key, token, password, private key). warn = likely problem. nit = style. Report issues only in ADDED (+) lines. A change that FIXES a problem is not a "
    "finding — if the diff only removes bugs or fixes code, return []. No prose outside the JSON."
)

MAX_DIFF_CHARS = 120_000  # refuse diffs past this; review in commits instead


def build_args(argv: list[str]):
    import argparse

    parser = argparse.ArgumentParser(prog="ollakit review")
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--branch", metavar="REF")
    parser.add_argument("--model")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--install-hook", action="store_true", dest="install_hook")
    return parser.parse_args(argv)


def get_diff(args) -> str:
    if args.branch:
        cmd = ["git", "diff", f"{args.branch}...HEAD"]
    else:
        cmd = ["git", "diff", "--staged"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"git diff failed: {result.stderr.strip()}")
    return result.stdout


def split_diff(raw: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    if len(raw) <= max_chars:
        return [raw]
    files: list[str] = []
    current: list[str] = []
    size = 0
    for line in raw.splitlines(keepends=True):
        if line.startswith("diff --git ") and size > max_chars // 2:
            files.append("".join(current))
            current, size = [], 0
        current.append(line)
        size += len(line)
    if current:
        files.append("".join(current))
    return files


SEVERITY_ALIASES = {
    "critical": "critical", "high": "critical", "blocker": "critical",
    "warn": "warn", "warning": "warn", "medium": "warn",
    "nit": "nit", "low": "nit", "info": "nit", "minor": "nit",
}


def to_findings(raw: str) -> list[dict]:
    data = client.parse_json(raw)
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []
    findings = []
    for row in data:
        if not isinstance(row, dict) or "comment" not in row:
            continue
        severity = SEVERITY_ALIASES.get(str(row.get("severity", "")).lower(), "nit")
        line = row.get("line")
        findings.append(
            {
                "file": str(row.get("file", "?")),
                "line": line if isinstance(line, int) else None,
                "severity": severity,
                "comment": str(row["comment"]),
            }
        )
    return findings


def collect_findings(diff: str, model: str) -> list[dict]:
    findings: list[dict] = []
    for chunk in split_diff(diff):
        raw = client.chat(
            model,
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": chunk},
            ],
            json_mode=True,
        )
        findings.extend(to_findings(raw))
    return findings


def has_critical(findings: list[dict]) -> bool:
    return any(f["severity"] == "critical" for f in findings)


def render(findings: list[dict]) -> None:
    if not findings:
        print("No findings.")
        return
    by_file: dict[str, list[dict]] = {}
    for f in findings:
        by_file.setdefault(f["file"], []).append(f)
    for file, rows in by_file.items():
        for f in rows:
            loc = f"{file}:{f['line']}" if f["line"] is not None else file
            print(f"{loc}  [{f['severity']}]  {f['comment']}")
    counts = {s: sum(1 for f in findings if f["severity"] == s) for s in ("critical", "warn", "nit")}
    print(
        f"\n{counts['critical']} critical, {counts['warn']} warn, {counts['nit']} nit"
        f" across {len(by_file)} file(s)"
    )


HOOK = """#!/bin/sh
# Installed by `ollakit review --install-hook`; blocks commits with critical findings.
ollakit review --staged || {
  echo ""
  echo "pre-commit: ollakit found critical issues. Fix them or commit with --no-verify."
  exit 1
}
"""


def install_hook() -> None:
    import os
    from pathlib import Path

    hook = Path(".git") / "hooks" / "pre-commit"
    if hook.exists():
        raise SystemExit(f"{hook} already exists; refusing to overwrite. Remove it first.")
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(HOOK)
    hook.chmod(hook.stat().st_mode | 0o111)
    print(f"Installed pre-commit hook at {hook}. Undo: rm {hook}")


def run(args) -> int:
    if args.install_hook:
        install_hook()
        return 0
    diff = get_diff(args)
    if not diff.strip():
        print("No changes to review." + (" (staged)" if not args.branch else f" vs {args.branch}"))
        return 0
    if len(diff) > MAX_DIFF_CHARS:
        raise SystemExit(
            f"Diff is {len(diff)} chars (limit {MAX_DIFF_CHARS}). Review it in smaller commits."
        )
    model = client.pick_chat_model(args.model)
    findings = collect_findings(diff, model)
    if args.as_json:
        import json

        print(json.dumps(findings, indent=2))
    else:
        render(findings)
    return 1 if has_critical(findings) else 0
