"""Measure ollakit review quality on planted-bug fixtures.

Usage:
    .venv/bin/python eval/run.py            # gated pipeline
    .venv/bin/python eval/run.py --fast     # v1 single-pass baseline
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ollakit import client  # noqa: E402
from ollakit.review import context, gates, generate, linters  # noqa: E402
from ollakit.review.diff import parse_diff  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
LINE_TOLERANCE = 2


def staged_diff(directory: Path, filename: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(directory), "diff", "--staged"], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise SystemExit(f"git diff failed in {directory}: {result.stderr}")
    return result.stdout


def review_diff(diff_text: str, workdir: Path, fast: bool, model: str, security_model: str | None = None) -> tuple[list[dict], dict]:
    files = parse_diff(diff_text)
    linter_findings, _ = linters.run_all([f.path for f in files if f.path != "?"])
    if fast:
        surfaced = generate.collect_findings_fast(diff_text, model)
        stats = {"candidates": len(surfaced), "hallucination_dropped": 0,
                 "actionability_dropped": 0, "capped": 0}
    else:
        file_data = []
        for fd in files:
            hunk_text = "\n".join(
                f"@@ -{h.old_start} +{h.new_start} @@\n" + "\n".join(h.lines) for h in fd.hunks
            )
            spans = fd.spans()
            if not spans:
                continue
            ctx = context.enrich(workdir / fd.path, spans[0][0], spans[-1][1])
            file_data.append((fd.path, ctx, hunk_text, None))
        candidates = generate.generate_for_files(file_data, model, security_model)
        surfaced, stats = gates.apply_gates(candidates, workdir)
    return linter_findings + surfaced, stats


def evaluate(fast: bool, model: str, security_model: str | None = None) -> dict:
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    results = {
        "model": model,
        "security_model": security_model or model,
        "config": "fast" if fast else "gated",
        "planted_total": 0,
        "detected": 0,
        "false_positives": 0,
        "gate_stats": {"candidates": 0, "hallucination_dropped": 0, "actionability_dropped": 0},
        "detail": [],
    }

    for kind in ("buggy", "clean"):
        for fixture in sorted((FIXTURES / kind).glob("*.py")):
            with tempfile.TemporaryDirectory() as tmp:
                repo = Path(tmp) / "repo"
                repo.mkdir()
                subprocess.run(["git", "init", "-q", str(repo)], check=True)
                staged = repo / fixture.name
                staged.write_text(fixture.read_text())
                subprocess.run(["git", "-C", str(repo), "add", fixture.name], check=True)
                diff_text = staged_diff(repo, fixture.name)
                # review inside the with-block: the judge reads file content
                surfaced, stats = review_diff(diff_text, repo, fast, model, security_model)
            results["gate_stats"]["candidates"] += stats.get("candidates", len(surfaced))
            results["gate_stats"]["hallucination_dropped"] += stats.get("hallucination_dropped", 0)
            results["gate_stats"]["actionability_dropped"] += stats.get("actionability_dropped", 0)

            planted = manifest.get(fixture.name, []) if kind == "buggy" else []
            results["planted_total"] += len(planted)
            detected_lines = set()
            fp = 0
            for f in surfaced:
                line = f.get("line")
                if kind == "clean":
                    fp += 1
                    continue
                hits = [p for p in planted if line and abs(line - p["line"]) <= LINE_TOLERANCE]
                if hits:
                    detected_lines.update(p["line"] for p in hits)
                else:
                    fp += 1
            results["detected"] += len(detected_lines)
            results["false_positives"] += fp
            results["detail"].append(
                {
                    "fixture": f"{kind}/{fixture.name}",
                    "planted": [p["class"] for p in planted],
                    "found_lines": sorted(detected_lines),
                    "false_positives": fp,
                    "finding_count": len(surfaced),
                }
            )
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fast", action="store_true")
    parser.add_argument("--model")
    parser.add_argument("--security-model")
    args = parser.parse_args()
    model = client.pick_chat_model(args.model)
    r = evaluate(args.fast, model, args.security_model)
    det = f"{r['detected']}/{r['planted_total']}"
    print(f"\n=== ollakit review eval [{r['config']}] model={r['model']} ===")
    print(f"detection:      {det}")
    print(f"false positives: {r['false_positives']}")
    gs = r["gate_stats"]
    print(f"gate stats:      {gs['candidates']} candidates, "
          f"{gs['hallucination_dropped']} hallucinations dropped, "
          f"{gs['actionability_dropped']} vague dropped")
    for d in r["detail"]:
        print(f"  {d['fixture']:20} planted={','.join(d['planted']) or '-':45} "
              f"found@{d['found_lines']} fp={d['false_positives']}")
    out = Path(__file__).parent / f"results-{r['config']}.json"
    out.write_text(json.dumps(r, indent=2))
    print(f"\nresults written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
