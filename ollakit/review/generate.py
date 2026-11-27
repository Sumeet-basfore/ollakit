"""Constrained finding generation: per-file, enriched, guideline-partitioned.

The prompt follows the production template (persona / task / guidelines /
context partition) and hard-requires what makes a finding actionable:
exact line, failure mode, suggested patch. The fast path is the v1
single-pass raw-diff review, kept for quick checks.
"""

from .. import client
from .diff import parse_diff, split_diff

SYSTEM_PROMPT = (
    "You are a senior code reviewer. Review the ADDED (+) lines of the diff using the "
    "provided file context, and output ONLY a JSON array of findings, each: "
    '{"file": str, "line": int, "severity": "critical"|"warn"|"nit", '
    '"comment": str, "suggested_patch": str|null, "failure_mode": str|null, '
    '"category": "security"|"correctness"|"performance"|"quality"}. '
    "critical = bug, security issue, data loss, or ANY hardcoded credential (API key, "
    "token, password, private key). warn = likely problem. nit = style. "
    "Rules: report issues only on added (+) lines; a change that FIXES a problem is not a "
    "finding; every finding needs a concrete failure mode (\"If X occurs, Y fails because "
    "Z\") and a copy-pasteable replacement patch when one exists; do NOT report formatting, "
    "naming, or style issues a linter would catch; if there is nothing to report return []. "
    "No prose outside the JSON."
)

SEVERITY_ALIASES = {
    "critical": "critical", "high": "critical", "blocker": "critical",
    "warn": "warn", "warning": "warn", "medium": "warn",
    "nit": "nit", "low": "nit", "info": "nit", "minor": "nit",
}

CATEGORIES = ("security", "correctness", "performance", "quality")


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
        category = str(row.get("category", "quality")).lower()
        if category not in CATEGORIES:
            category = "quality"
        findings.append(
            {
                "file": str(row.get("file", "?")),
                "line": line if isinstance(line, int) else None,
                "severity": severity,
                "comment": str(row["comment"]),
                "suggested_patch": row.get("suggested_patch") or None,
                "failure_mode": row.get("failure_mode") or None,
                "category": category,
            }
        )
    return findings


SECURITY_PROMPT = (
    "You are a security auditor. Scan the added (+) lines for ONLY security issues: "
    "hardcoded credentials (API keys, tokens, passwords, private keys), injection "
    "(SQL, command, path), unsafe deserialization, weak crypto, missing input "
    "validation on external input. Output ONLY a JSON array with the same finding "
    "schema as before "
    '{"file": str, "line": int, "severity": "critical"|"warn"|"nit", "comment": str, '
    '"suggested_patch": str|null, "failure_mode": str|null, "category": "security"}. '
    'If there are no security issues, return []. No prose.'
)


def build_user_prompt(
    path: str, context_text: str, hunk_text: str, linter_note: str | None
) -> str:
    parts = [f"File: {path}"]
    if context_text:
        parts.append(f"File content around the change (>' marks changed lines):\n{context_text}")
    parts.append(f"Diff hunks:\n{hunk_text}")
    if linter_note:
        parts.append(
            f"These issues are already reported by deterministic linters — do NOT repeat them "
            f"or report similar style issues:\n{linter_note}"
        )
    return "\n\n".join(parts)


def generate_for_files(file_data: list[tuple], model: str) -> list[dict]:
    """file_data: (path, context_text, hunk_text, linter_note) tuples.

    Two lens passes per file: the general reviewer, then a security-only
    scan. Small local models attend better to one concern at a time, and
    the security lens reliably catches credentials the general pass
    skips. Duplicates are harmless — the gates dedupe by file+line.
    """
    findings: list[dict] = []
    for path, context_text, hunk_text, linter_note in file_data:
        user_prompt = build_user_prompt(path, context_text, hunk_text, linter_note)
        for system_prompt in (SYSTEM_PROMPT, SECURITY_PROMPT):
            raw = client.chat(
                model,
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                json_mode=True,
            )
            for f in to_findings(raw):
                f.setdefault("file", path)
                findings.append(f)
    return findings


def collect_findings_fast(diff_text: str, model: str) -> list[dict]:
    """v1 fast path: single-pass over raw diff chunks, no context or gates."""
    findings: list[dict] = []
    for chunk in split_diff(diff_text):
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
