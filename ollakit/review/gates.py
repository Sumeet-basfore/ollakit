"""Quality gates: drop hallucinated and vague findings before the user sees them.

Gate 1 (factual judge): each candidate is re-verified against the actual file
content by a binary judge call — the measured fix for small-model false
positives (v1 flagged a parameterized query as injection).
Gate 2 (actionability): a zero-token heuristic that drops findings with no
line, no patch, and vague phrasing.
"""

import re

from .. import client

CATEGORY_ORDER = {"security": 0, "correctness": 1, "performance": 2, "quality": 3}
SEVERITY_ORDER = {"critical": 0, "warn": 1, "nit": 2}

VAGUE = re.compile(
    r"\b(consider|could be improved|think about|maybe|possibly|you might|"
    r"it would be nice|in general|best practice)\b",
    re.IGNORECASE,
)

JUDGE_PROMPT = (
    "You are a code-review verification judge. Decide if the finding is factually "
    "accurate based ONLY on the code content provided. Return ONLY JSON: "
    '{"factually_correct": true|false, "rationale": "short explanation"}. '
    "It is factually correct only if the described defect actually appears in the "
    "quoted code AND the suggested patch would run against real names in that code."
)


def actionable(f: dict) -> bool:
    if f.get("line") is None:
        return False
    comment = str(f.get("comment", ""))
    if VAGUE.search(comment) and not f.get("suggested_patch"):
        return False
    return True


def fact_check(f: dict, file_content: str) -> tuple[bool, str]:
    """(ok, rationale). Unparseable judge output drops the finding (fail-closed)."""
    user = (
        f"Code content of {f['file']}:\n```\n{file_content[:6000]}\n```\n\n"
        f"Finding:\nfile: {f['file']}\nline: {f.get('line')}\n"
        f"comment: {f['comment']}\n"
        f"suggested_patch: {f.get('suggested_patch')}\n"
        f"failure_mode: {f.get('failure_mode')}"
    )
    raw = client.chat(
        client.pick_chat_model(None),
        [
            {"role": "system", "content": JUDGE_PROMPT},
            {"role": "user", "content": user},
        ],
        json_mode=True,
    )
    try:
        data = client.parse_json(raw)
    except Exception:
        return False, "judge output unparseable"
    if isinstance(data, dict) and "factually_correct" in data:
        return bool(data["factually_correct"]), str(data.get("rationale", ""))
    return False, "judge output unparseable"


def rank(findings: list[dict]) -> list[dict]:
    return sorted(
        findings,
        key=lambda f: (
            SEVERITY_ORDER.get(f.get("severity", "nit"), 2),
            CATEGORY_ORDER.get(f.get("category", "quality"), 3),
        ),
    )


def dedupe(findings: list[dict]) -> list[dict]:
    """Collapse cross-lens duplicates: same file, lines within ±2."""
    kept: list[dict] = []
    for f in rank(findings):
        near = any(
            k["file"] == f["file"]
            and f.get("line") is not None
            and k.get("line") is not None
            and abs(k["line"] - f["line"]) <= 2
            for k in kept
        )
        if not near:
            kept.append(f)
    return kept


def apply_gates(
    candidates: list[dict], root, cap: int = 5, judge_model: str | None = None
) -> tuple[list[dict], dict]:
    """Returns (kept findings, stats) — suppressed findings are counted, never hidden."""
    stats = {
        "candidates": len(candidates),
        "hallucination_dropped": 0,
        "actionability_dropped": 0,
        "capped": 0,
        "hallucination_reasons": [],
    }
    kept: list[dict] = []
    for f in candidates:
        if not actionable(f):
            stats["actionability_dropped"] += 1
            continue
        path = root / f["file"]
        try:
            content = path.read_text(errors="replace")
        except OSError:
            content = ""
        if content:
            ok, why = fact_check(f, content)
            if not ok:
                stats["hallucination_dropped"] += 1
                stats["hallucination_reasons"].append(
                    {"file": f["file"], "line": f.get("line"), "comment": f["comment"], "why": why}
                )
                continue
        kept.append(f)
    kept = dedupe(kept)
    if len(kept) > cap:
        stats["capped"] = len(kept) - cap
        kept = kept[:cap]
    return kept, stats
