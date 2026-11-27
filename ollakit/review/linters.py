"""Optional deterministic linters: free findings, zero model tokens.

Detects ruff / bandit / semgrep on PATH and runs them over changed files.
Everything is best-effort: an absent or failing tool is a note, not an error.
"""

import json
import shutil
import subprocess

TIMEOUT = 60

SEVERITY_MAP = {
    "ruff": "nit",
    "bandit": "warn",
    "semgrep": "warn",
}


def available() -> list[str]:
    return [t for t in ("ruff", "bandit", "semgrep") if shutil.which(t)]


def run(tool: str, files: list[str]) -> tuple[list[dict], str]:
    """Findings in the unified schema, plus a note when the tool failed."""
    if tool == "ruff":
        cmd = ["ruff", "check", "--output-format", "json", "--no-cache", *files]
    elif tool == "bandit":
        cmd = ["bandit", "-f", "json", "-q", *files]
    elif tool == "semgrep":
        cmd = ["semgrep", "--json", "--quiet", *files]
    else:
        return [], f"unknown tool: {tool}"
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    except (subprocess.TimeoutExpired, OSError) as e:
        return [], f"{tool} failed: {e}"
    if result.returncode not in (0, 1):  # 1 = findings found, both fine
        return [], f"{tool} exited {result.returncode}"
    try:
        return _parse(tool, result.stdout), ""
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        return [], f"{tool} output unparseable: {e}"


def _parse(tool: str, stdout: str) -> list[dict]:
    findings = []
    if tool == "ruff":
        for item in json.loads(stdout or "[]"):
            findings.append(
                {
                    "tool": "ruff",
                    "file": item["filename"],
                    "line": item["location"]["row"],
                    "severity": "nit",
                    "comment": f"[ruff {item['code']}] {item['message']}",
                    "patch": None,
                }
            )
    elif tool == "bandit":
        data = json.loads(stdout or "{}")
        for item in data.get("results", []):
            sev = "critical" if item["issue_severity"] == "HIGH" else "warn"
            findings.append(
                {
                    "tool": "bandit",
                    "file": item["filename"],
                    "line": item["line_number"],
                    "severity": sev,
                    "comment": f"[bandit {item['test_id']}] {item['issue_text']}",
                    "patch": None,
                }
            )
    elif tool == "semgrep":
        data = json.loads(stdout or "{}")
        for item in data.get("results", []):
            sev = "critical" if item["extra"]["severity"] == "ERROR" else "warn"
            findings.append(
                {
                    "tool": "semgrep",
                    "file": item["path"],
                    "line": item["start"]["line"],
                    "severity": sev,
                    "comment": f"[semgrep {item['check_id']}] {item['extra']['message']}",
                    "patch": item["extra"].get("fix"),
                }
            )
    return findings


def run_all(files: list[str]) -> tuple[list[dict], list[str]]:
    findings: list[dict] = []
    notes: list[str] = []
    for tool in available():
        got, note = run(tool, files)
        findings.extend(got)
        if note:
            notes.append(note)
    return findings, notes
