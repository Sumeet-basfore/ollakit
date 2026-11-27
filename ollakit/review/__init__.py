"""ollakit review: production-pipeline code review on a local model.

Pipeline: diff → context enrichment → linter pre-filter (free) →
constrained generation → factual-judge + actionability gates → outputs
(terminal / report / agent fix prompts). `--fast` keeps the v1
single-pass behavior.
"""

import json as _json
import sys
from pathlib import Path

from .. import client
from . import context, gates, generate, handoff, linters
from .diff import get_diff, parse_diff, split_diff  # noqa: F401 (re-exported)

MAX_DIFF_CHARS = 120_000

HOOK_TEMPLATE = """#!/bin/sh
# Installed by `ollakit review --install-hook`; blocks commits with critical findings.
"{ollakit_bin}" review --staged || {{
  echo ""
  echo "pre-commit: ollakit found critical issues. Fix them or commit with --no-verify."
  exit 1
}}
"""


def build_args(argv: list[str]):
    import argparse

    parser = argparse.ArgumentParser(prog="ollakit review")
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--branch", metavar="REF")
    parser.add_argument("--model")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--install-hook", action="store_true", dest="install_hook")
    parser.add_argument("--fast", action="store_true", help="single-pass raw-diff review (v1)")
    parser.add_argument("--no-gates", action="store_true", help="skip judge/actionability gates")
    parser.add_argument("--report", metavar="PATH", help="write a markdown report")
    parser.add_argument(
        "--fix-prompt", metavar="DIR", nargs="?", const=".", dest="fix_prompt",
        help="write one paste-ready fix prompt per finding (default dir: .)"
    )
    parser.add_argument(
        "--fix-prompt-all", metavar="PATH", nargs="?", const="ollakit-fix.md", dest="fix_prompt_all",
        help="write one combined fix brief for a coding agent"
    )
    return parser.parse_args(argv)


def has_critical(findings: list[dict]) -> bool:
    return any(f.get("severity") == "critical" for f in findings)


def _collect_changed_paths(files) -> list[str]:
    return [f.path for f in files if f.path != "?" and not f.path.startswith("/dev/")]


def _gather_model_findings(files, model: str, linter_findings: list[dict]) -> list[dict]:
    file_data = []
    for fd in files:
        hunk_text = "\n".join(
            f"@@ -{h.old_start} +{h.new_start} @@\n" + "\n".join(h.lines) for h in fd.hunks
        )
        spans = fd.spans()
        if not spans:
            continue
        first = spans[0]
        ctx = context.enrich(Path(fd.path), first[0], first[-1])
        own = "\n".join(f"{f['comment']}" for f in linter_findings if f["file"] == fd.path) or None
        file_data.append((fd.path, ctx, hunk_text, own))
    return generate.generate_for_files(file_data, model)


def install_hook() -> None:
    import os
    import shutil as _shutil

    ollakit_bin = _shutil.which("ollakit") or sys.argv[0]
    if not os.path.isabs(ollakit_bin):
        raise SystemExit("Cannot resolve the ollakit executable path; run from an install.")
    hook = Path(".git") / "hooks" / "pre-commit"
    if hook.exists():
        raise SystemExit(f"{hook} already exists; refusing to overwrite. Remove it first.")
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(HOOK_TEMPLATE.format(ollakit_bin=ollakit_bin))
    hook.chmod(hook.stat().st_mode | 0o111)
    print(f"Installed pre-commit hook at {hook}. Undo: rm {hook}")


def _write_fix_prompts(findings: list[dict], out_dir: str, root: Path) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    contents = {}
    for path in {f["file"] for f in findings}:
        p = root / path
        contents[path] = context.enrich(p, 1, 10**9)
    written = []
    for i, f in enumerate(findings, 1):
        name = f"fix-{i:02d}-{Path(f['file']).stem}-{f.get('line') or 0}.md"
        target = out / name
        target.write_text(handoff.fix_prompt([f], contents))
        written.append(str(target))
    print(f"\nWrote {len(written)} fix prompt(s):")
    for w in written:
        print(f"  {w}")


def run(args) -> int:
    if args.install_hook:
        install_hook()
        return 0
    diff_text = get_diff(args)
    if not diff_text.strip():
        print("No changes to review." + (" (staged)" if not args.branch else f" vs {args.branch}"))
        return 0
    if len(diff_text) > MAX_DIFF_CHARS:
        raise SystemExit(
            f"Diff is {len(diff_text)} chars (limit {MAX_DIFF_CHARS}). Review it in smaller commits."
        )
    root = Path.cwd()
    model = client.pick_chat_model(args.model)
    files = parse_diff(diff_text)

    linter_findings, linter_notes = linters.run_all(_collect_changed_paths(files))

    if args.fast:
        surfaced = collect_findings(diff_text, model)
        stats: dict = {"candidates": len(surfaced), "hallucination_dropped": 0,
                       "actionability_dropped": 0, "capped": 0, "hallucination_reasons": []}
    else:
        candidates = _gather_model_findings(files, model, linter_findings)
        if args.no_gates:
            surfaced = candidates
            stats = {"candidates": len(candidates), "hallucination_dropped": 0,
                     "actionability_dropped": 0, "capped": 0, "hallucination_reasons": []}
        else:
            surfaced, stats = gates.apply_gates(candidates, root)

    findings = linter_findings + surfaced

    if args.as_json:
        print(_json.dumps(findings, indent=2))
    else:
        handoff.render_terminal(surfaced, stats)
        if linter_findings or linter_notes:
            print(f"\nLinter pre-filter: {len(linter_findings)} finding(s)"
                  + (f" ({len(linter_notes)} tool note(s))" if linter_notes else ""))
    if args.report:
        Path(args.report).write_text(
            handoff.report_markdown(findings, stats, linter_findings, linter_notes)
        )
        print(f"Report written to {args.report}")
    if args.fix_prompt and findings:
        _write_fix_prompts(findings, args.fix_prompt, root)
    if args.fix_prompt_all and findings:
        contents = {p: context.enrich(root / p, 1, 10**9) for p in {f["file"] for f in findings}}
        Path(args.fix_prompt_all).write_text(handoff.fix_prompt(findings, contents))
        print(f"Combined fix brief written to {args.fix_prompt_all}")
    return 1 if has_critical(findings) else 0


# Backward-compatible re-exports for the v1 surface (tests, hooks).
render = handoff.render_terminal
to_findings = generate.to_findings
collect_findings = generate.collect_findings_fast
