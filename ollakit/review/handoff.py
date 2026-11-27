"""Report rendering and agent handoff prompts.

The fix prompt is the flagship output: a paste-ready brief for AI coding
agents (Claude Code, Codex, Cursor) with goal, exact code, issue, failure
mode, patch, acceptance criteria and verification — the local, free
equivalent of Greptile's agent handoff.
"""

SEVERITY_LABEL = {"critical": "CRITICAL", "warn": "WARN", "nit": "NIT"}


def _loc(f: dict) -> str:
    return f"{f['file']}:{f['line']}" if f.get("line") is not None else str(f["file"])


def render_terminal(findings: list[dict], stats: dict | None = None) -> None:
    if not findings:
        print("No findings.")
    for f in findings:
        print(f"{_loc(f)}  [{SEVERITY_LABEL[f['severity']]}]  {f['comment']}")
    if stats:
        counts = {s: sum(1 for f in findings if f["severity"] == s) for s in ("critical", "warn", "nit")}
        parts = [f"{counts[s]} {s}" for s in ("critical", "warn", "nit")]
        line = f"\n{', '.join(parts)} surfaced"
        drops = []
        if stats.get("hallucination_dropped"):
            drops.append(f"{stats['hallucination_dropped']} hallucination(s) dropped by judge")
        if stats.get("actionability_dropped"):
            drops.append(f"{stats['actionability_dropped']} vague finding(s) dropped")
        if stats.get("capped"):
            drops.append(f"{stats['capped']} lower-ranked finding(s) suppressed")
        if drops:
            line += " | " + "; ".join(drops)
        print(line)


def report_markdown(
    findings: list[dict],
    stats: dict,
    linter_findings: list[dict],
    linter_notes: list[str],
) -> str:
    lines = ["# ollakit review report", ""]
    if linter_findings or linter_notes:
        lines += ["## Linters", ""]
        for f in linter_findings:
            lines.append(f"- `{_loc(f)}` [{f['tool']}] {f['comment']}")
        for note in linter_notes:
            lines.append(f"- (note) {note}")
        lines.append("")
    lines += ["## Findings", ""]
    if not findings:
        lines.append("No findings passed the quality gates.")
    for f in findings:
        lines.append(f"### [{SEVERITY_LABEL[f['severity']]}] `{_loc(f)}` ({f.get('category', 'quality')})")
        lines.append("")
        lines.append(f"{f['comment']}")
        if f.get("failure_mode"):
            lines.append("")
            lines.append(f"**Failure mode:** {f['failure_mode']}")
        if f.get("suggested_patch"):
            lines.append("")
            lines.append("```suggestion")
            lines.append(f["suggested_patch"])
            lines.append("```")
        lines.append("")
    dropped = stats.get("hallucination_dropped", 0) + stats.get("actionability_dropped", 0) + stats.get("capped", 0)
    if dropped or stats.get("candidates"):
        lines += ["## Suppressed", ""]
        if stats.get("hallucination_dropped"):
            lines.append(f"- {stats['hallucination_dropped']} candidate(s) dropped: judge found them factually wrong")
            for r in stats.get("hallucination_reasons", []):
                lines.append(f"  - `{r['file']}:{r.get('line')}` — {r['comment']} ({r['why']})")
        if stats.get("actionability_dropped"):
            lines.append(f"- {stats['actionability_dropped']} vague candidate(s) dropped")
        if stats.get("capped"):
            lines.append(f"- {stats['capped']} lower-ranked finding(s) suppressed (cap)")
        lines.append("")
    return "\n".join(lines)


def fix_prompt(findings: list[dict], file_contents: dict[str, str] | None = None) -> str:
    file_contents = file_contents or {}
    files = sorted({f["file"] for f in findings})
    issues = "\n".join(
        f"- `{_loc(f)}` [{SEVERITY_LABEL[f['severity']]}] {f['comment']}"
        + (f"\n  Failure mode: {f['failure_mode']}" if f.get("failure_mode") else "")
        for f in findings
    )
    code_blocks = []
    for path in files:
        if path in file_contents:
            code_blocks.append(f"### `{path}` (current content)\n```\n{file_contents[path]}\n```")
    patches = "\n\n".join(
        f"- `{_loc(f)}`:\n```\n{f['suggested_patch']}\n```"
        for f in findings
        if f.get("suggested_patch")
    )
    parts = [
        "Fix the following code review findings.",
        "",
        "## Goal",
        "Resolve every finding below without changing unrelated behavior.",
        "",
        "## Findings",
        issues,
        "",
    ]
    if code_blocks:
        parts += ["## Current code", *code_blocks, ""]
    if patches:
        parts += ["## Suggested patches (verify before applying — the reviewer is a small local model)", patches, ""]
    parts += [
        "## Acceptance",
        "- Each finding is addressed or explicitly justified in the commit message.",
        "- No new findings of the same class are introduced.",
        "",
        "## Verification",
        "Run the project's test suite and paste the output before claiming done.",
        "",
    ]
    return "\n".join(parts)


def fix_prompt_all(findings: list[dict], file_contents: dict[str, str] | None = None) -> str:
    return fix_prompt(findings, file_contents)
