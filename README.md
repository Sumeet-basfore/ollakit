# ollakit

Local Ollama toolkit: a production-pipeline code reviewer, a RAG chat over your notes, and a
reversible file organizer. All inference runs on your machine through Ollama — no API keys,
no accounts, no cost.

## Install

Requires Python 3.10+ and a running Ollama server (`ollama serve`).

```sh
python3 -m venv .venv
.venv/bin/pip install -e .
# or: uv tool install --editable <repo>
```

## review — the five-stage pipeline

```
git diff → context enrichment → linter pre-filter → two-lens generation
        → factual-judge + actionability gates → report / agent fix prompts
```

```sh
ollakit review                          # review staged changes (full pipeline)
ollakit review --branch main            # review a branch
ollakit review --report out.md          # markdown report with patches + suppressed items
ollakit review --fix-prompt prompts/    # one paste-ready fix brief per finding
ollakit review --fix-prompt-all fix.md  # one combined brief for your coding agent
ollakit review --fast                   # v1 single-pass quick check
ollakit review --install-hook           # pre-commit hook: blocks commits with critical findings
```

What each stage does:

1. **Context enrichment** — the real file content around each hunk (enclosing function for
   Python), because diff-only review is what makes LLMs hallucinate.
2. **Linter pre-filter** — runs ruff/bandit/semgrep when installed (zero model tokens) and
   tells the model not to repeat style complaints.
3. **Two-lens generation** — a general pass plus a security-only pass; findings must carry a
   line, a failure mode ("if X, then Y breaks") and a suggested patch.
4. **Quality gates** — a judge re-verifies every finding against the actual code (fail-closed)
   and an actionability filter drops vague nits. Suppressed items are counted in the report,
   never hidden. Max 5 surfaced, ranked security > correctness > performance > quality.
5. **Outputs** — terminal, markdown report, and `--fix-prompt`: a brief structured for direct
   paste into Claude Code / Codex / Cursor, with current code, failure modes, patches,
   acceptance criteria and a verification step.

**Measured on this machine** (7 planted bugs + 3 clean files, Qwen3.5-uncensored:latest):

| config | detection | false positives |
| --- | --- | --- |
| v1 single-pass (`--fast`) | 2/7 | 4 |
| v2 pipeline | 3/7 | 2 |
| v2 + security lens on gemma4:e2b | 3/7 (different bugs) | 2 |

The pipeline's proven win is precision — half the false positives, hallucinated findings
dropped by the judge, structured patches. Raw detection is bounded by local model size;
bigger local models (7B+) raise it. `eval/run.py` lets you measure on your own machine —
no vendor publishes these numbers, so we publish ours.

Model routing: different local models catch different bugs. Set `security_model` in
`~/.config/ollakit/config.json` (or `--security-model`) to run the security lens on a
second model.

## ask — local RAG over a notes directory

```sh
ollama pull nomic-embed-text              # one-time, ~275MB, stays local
ollakit ask "what did I decide about X?" --index ~/notes
ollakit ask --chat --index ~/notes
```

Chunks text files, embeds locally, answers from top-5 chunks with file citations. The index
is incremental and lives in `~/.cache/ollakit/`. Out-of-context questions get "does not
contain the answer", not an invention.

## organize — AI file sorting, reversibly

```sh
ollakit organize ~/Downloads              # dry-run: prints the plan, changes nothing
ollakit organize ~/Downloads --apply      # asks for confirmation, then moves
ollakit organize --undo ~/.cache/ollakit/organize-<stamp>.json
```

Classifies into `Documents | Images | Videos | Archives | Code | Music | Other`. Never
deletes, skips hidden files, suffixes collisions, preserves mtimes, journals every move.

## Configuration

`~/.config/ollakit/config.json`: `chat_model`, `security_model`, `embed_model`, `notes_dir`.
All optional; ollakit fills them on first use.

## Development

```sh
.venv/bin/python -m pytest          # test suite
.venv/bin/python eval/run.py        # review quality eval (needs Ollama)
```
