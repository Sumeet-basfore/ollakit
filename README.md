# ollakit

Local AI developer toolkit built on [Ollama](https://ollama.com): a production-pipeline code
reviewer, a RAG chat over your notes, and a reversible file organizer. Every inference runs on
your machine — no API keys, no accounts, no subscription, no code leaving your disk.

## Key Features

- **`review`** — reviews staged changes or a branch diff with a five-stage pipeline: context
  enrichment, deterministic linter pre-filter, two-lens generation, hallucination-judging
  quality gates, and paste-ready fix prompts for AI coding agents
- **`ask`** — asks questions over a local index of your notes with file citations; refuses to
  answer beyond the indexed context
- **`organize`** — sorts messy directories into a fixed taxonomy with dry-run default,
  confirmation, and exact undo; never deletes anything
- **`--install-hook`** — a pre-commit hook that blocks commits containing critical findings
- **Measured quality** — a planted-bug eval harness (`eval/run.py`) so review quality is a
  number, not a marketing claim; we publish ours, no vendor does

## Table of Contents

- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Getting Started](#getting-started)
- [Usage](#usage)
  - [review](#review--code-review-before-it-lands)
  - [ask](#ask--local-rag-over-your-notes)
  - [organize](#organize--reversible-ai-file-sorting)
- [Architecture](#architecture)
- [Configuration](#configuration)
- [Model Selection](#model-selection)
- [Available Commands Reference](#available-commands-reference)
- [Testing](#testing)
- [Evaluation](#evaluation)
- [Using the Pre-commit Hook in CI](#using-the-pre-commit-hook-in-ci)
- [Troubleshooting](#troubleshooting)
- [Project Layout](#project-layout)
- [Design Principles](#design-principles)
- [Contributing](#contributing)
- [License](#license)

## Tech Stack

- **Language**: Python 3.10+
- **LLM runtime**: Ollama (any local model)
- **Python dependency**: `ollama` (the only one)
- **Config format**: JSON (`~/.config/ollakit/config.json`)
- **Packaging**: setuptools (`pyproject.toml`), console-script entry point
- **Tests**: pytest (62 tests)
- **Optional system tools**: ruff, bandit, semgrep (used by `review` when installed; never required)

## Prerequisites

- **Python 3.10 or higher** — `python3 --version`
- **Ollama** installed and running — [install guide](https://ollama.com/download), then
  `ollama serve` (or the desktop app)
- **At least one Ollama model** — see [Model Selection](#model-selection) for what works
- **git** (for `review`)
- Optional, for `ask`: an embedding model — `ollama pull nomic-embed-text` (~275 MB, stays local)
- Optional, for `review`'s linter stage: `ruff`, `bandit`, and/or `semgrep` on your `PATH`

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/Sumeet-basfore/ollakit.git
cd ollakit
```

### 2. Create a virtual environment

A venv keeps ollakit's dependency out of your system Python (system pip may refuse installs
anyway — PEP 668):

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

The `-e` (editable) install means changes to the source apply immediately.

### 3. Make the CLI available everywhere (optional)

Either add the venv to your `PATH`:

```bash
export PATH="$PWD/.venv/bin:$PATH"   # put this in your shell rc
```

or install once with [uv](https://docs.astral.sh/uv/), which is what the maintainers use:

```bash
uv tool install --editable /path/to/ollakit
```

### 4. Verify Ollama is reachable

```bash
ollama list          # shows your installed models
ollakit review --help
```

`ollakit` errors with a clear message if it cannot reach `localhost:11434` — start `ollama serve`.

### 5. First run

On first use, ollakit auto-selects a chat model from what you have installed and remembers it in
`~/.config/ollakit/config.json`:

```text
[ollakit] selected chat model: Qwen3.5-uncensored:latest (set --model to override)
```

That's it — see [Usage](#usage).

## Usage

### review — code review before it lands

```bash
ollakit review                          # staged changes (default)
ollakit review --branch main            # everything main..HEAD
ollakit review --json                   # machine-readable findings
ollakit review --fast                   # v1 single-pass quick check (no gates)
ollakit review --no-gates               # pipeline, but skip the judge
```

Example output on a staged diff with a hardcoded password:

```text
auth.py:1  [CRITICAL]  Hardcoded plaintext password is exposed in the source code.
  Failure mode: If an attacker gains read access to this file (e.g., via backup,
  public repository, or source control), they obtain the database password immediately.

1 critical, 0 warn, 0 nit surfaced
```

Exit code is **1 when any critical finding surfaced**, 0 otherwise — that is what makes the git
hook and CI usage work.

#### Reports and agent handoff

```bash
ollakit review --report out.md          # full markdown report: findings, patches, suppressed items
ollakit review --fix-prompt prompts/    # one paste-ready fix brief per finding
ollakit review --fix-prompt-all fix.md  # one combined brief for your coding agent
```

The fix prompt is the flagship output — a complete brief for Claude Code, Codex, Cursor or any
AI coding agent:

```markdown
Fix the following code review findings.

## Goal
Resolve every finding below without changing unrelated behavior.

## Findings
- `auth.py:1` [CRITICAL] Hardcoded plaintext password ...
  Failure mode: If an attacker gains read access ...

## Current code
### `auth.py` (current content)
...
## Acceptance
- Each finding is addressed or explicitly justified in the commit message.
## Verification
Run the project's test suite and paste the output before claiming done.
```

Workflow: `ollakit review --fix-prompt-all` → paste the file into your agent → let it fix →
re-run `ollakit review` to confirm the finding is gone.

#### The five-stage pipeline

```text
git diff → 1. context enrichment      (real file content around each hunk)
         → 2. linter pre-filter       (ruff/bandit/semgrep if installed — zero model tokens)
         → 3. two-lens generation     (general pass + security-only pass)
         → 4. quality gates           (factual judge per finding, fail-closed)
         → 5. outputs                 (terminal / report / fix prompts)
```

Why this exists: piping a raw diff into one model pass produces false positives and vague nits —
measured, not anecdotal (see [Evaluation](#evaluation)). Stage 1 fixes diff-blindness (the #1
cause of hallucinated findings), stage 2 moves style checking to tools that never hallucinate,
stage 3 makes small local models attend to one concern at a time, and stage 4 drops findings the
judge cannot verify against the real code. Suppressed findings are counted and reported — never
silently hidden.

### ask — local RAG over your notes

```bash
# one-time setup
ollama pull nomic-embed-text

ollakit ask "what did I decide about the auth flow?" --index ~/notes
ollakit ask --chat --index ~/notes     # interactive session ('exit' or Ctrl-C to quit)
ollakit ask "..." --index ~/notes --reindex
ollakit ask "..." --k 8                # retrieve more chunks
```

Example:

```text
Project Phoenix is an internal CLI for batch photo renaming. Its version 2 is
scheduled to ship in December.

Sources:
  project.md  (1 chunk)
```

- Indexes `.md`, `.txt`, code and config files (hidden dirs, `node_modules`, `.git` skipped)
- ~800-character chunks, 100-character overlap, newline-aware splitting
- Top-5 chunks by cosine similarity, embedded by a local embedding model
- The index lives in `~/.cache/ollakit/` and is incremental: files re-embed only when mtime or
  size changes
- Questions the context cannot answer get "does not contain the answer" — never an invention

Tip: set `notes_dir` in the config (below) to skip `--index` on every call.

### organize — reversible AI file sorting

```bash
ollakit organize ~/Downloads              # dry-run: prints the plan, changes NOTHING
ollakit organize ~/Downloads --apply      # confirmation prompt, then moves
ollakit organize ~/Downloads --apply --yes  # skip the prompt (scripts)
ollakit organize ~/Downloads --recursive
ollakit organize --undo ~/.cache/ollakit/organize-20261127-221950.json
```

Dry-run output:

```text
IMG_2024.jpg                             -> Images/IMG_2024.jpg
Quarterly Report.pdf                     -> Documents/Quarterly Report.pdf
installer.zip                            -> Archives/installer.zip
track1.mp3                               -> Music/track1.mp3

5 file(s) would move.

Dry run: nothing changed. Pass --apply to execute.
```

Safety rules, by design:

- **Never deletes** — moves and renames only
- **Dry-run is the default** — `--apply` is always explicit
- **Every move is journaled** to `~/.cache/ollakit/organize-<timestamp>.json`
- **`--undo` replays the journal in reverse** — verified to restore the exact original layout
- Name collisions get `report (2).pdf` suffixes; mtimes are preserved; hidden files are skipped

## Architecture

### Directory structure

```text
ollakit/
├── ollakit/                  # the package
│   ├── cli.py                # argparse dispatch to subcommand modules
│   ├── client.py             # shared Ollama client: model selection, chat, embed
│   ├── config.py             # ~/.config/ollakit/config.json (stdlib json)
│   ├── review/               # the code reviewer (see below)
│   │   ├── __init__.py       # run(): the five-stage pipeline + CLI surface
│   │   ├── diff.py           # diff fetch (git) + unified-diff/hunk parsing
│   │   ├── context.py        # hunk context enrichment (enclosing function / ±25 lines)
│   │   ├── linters.py        # ruff / bandit / semgrep integration, best-effort
│   │   ├── generate.py       # two-lens constrained generation + finding normalization
│   │   ├── gates.py          # factual judge, actionability filter, rank, cap, dedupe
│   │   └── handoff.py        # terminal rendering, markdown report, agent fix prompts
│   ├── ask.py                # RAG: chunker, indexer, cosine retrieval, cited answers
│   └── organize.py           # classifier, planner, journal, undo
├── tests/                    # pytest — one file per module, model calls mocked
├── eval/
│   ├── run.py                # drives fixtures through the pipeline, prints metrics
│   └── fixtures/             # buggy/ (planted defects) + clean/ twins + manifest.json
└── pyproject.toml
```

### Request lifecycle (review)

1. `git diff --staged` (or `git diff <ref>...HEAD`) is fetched and parsed into per-file hunks
2. Each hunk is enriched with the actual file content — the enclosing Python function when
   detectable, a ±25-line window otherwise, capped at 6 KB
3. Deterministic linters run over the changed files (subprocess, 60 s timeout, best-effort);
   their findings become output directly and the model is told not to repeat them
4. Two generation passes per file (general, then security-only) return JSON findings; a
   normalizer tolerates small-model quirks (bare objects, severity synonyms like "high",
   duplicate JSON keys)
5. Every candidate is re-verified against the real file content by a binary judge call —
   unparseable judge output drops the finding (fail-closed). A zero-token actionability filter
   drops line-less and vague-without-patch findings. Cross-lens duplicates collapse (same file,
   lines within ±2). Findings rank security > correctness > performance > quality, capped at 5
6. Outputs render; exit code 1 iff a critical finding (model or linter) surfaced

### Request lifecycle (ask)

1. The notes directory is walked (text extensions only); unchanged files reuse the persisted
   index (`~/.cache/ollakit/ask-index-<dirhash>.json`)
2. New/changed files are chunked and embedded locally
3. The question embeds; chunks rank by cosine similarity; top-k join the prompt
4. The model answers from context only; sources print below the answer

### Data flow (organize)

```text
scan (skip hidden) → classify via model (per-file backfill) → plan (taxonomy + collision check)
   → dry-run print → confirm → shutil.move (mtime preserved) → journal
                                                        ↓
                                              --undo replays reversed
```

## Configuration

`~/.config/ollakit/config.json` — created on first use, all keys optional:

| Key              | Used by   | Meaning                                                    | Default                    |
| ---------------- | --------- | ---------------------------------------------------------- | -------------------------- |
| `chat_model`     | all       | default chat model; auto-selected on first run             | auto (see below)           |
| `security_model` | `review`  | model for the security lens pass (model routing)           | same as `chat_model`       |
| `embed_model`    | `ask`     | embedding model                                            | first `*embed*` model      |
| `notes_dir`      | `ask`     | default `--index` directory                                | unset (flag required)      |

Example:

```json
{
  "chat_model": "Qwen3.5-uncensored:latest",
  "security_model": "gemma4:e2b",
  "embed_model": "nomic-embed-text",
  "notes_dir": "/home/you/notes"
}
```

An explicit `--model` flag updates `chat_model` (the operator's choice is remembered).

## Model Selection

Auto-selection prefers, in order: a model with `coder`/`code` in its name, then qwen-family
models, then the largest local model by size (cloud models are excluded unless nothing local
exists). Every flag accepts `--model` to override per run.

Measured guidance from the eval harness on this project (7 planted bugs, 3 clean twins):

| config                                    | detection | false positives |
| ----------------------------------------- | --------- | --------------- |
| single-pass raw-diff review (v1, `--fast`) | 2/7       | 4               |
| full pipeline                              | 3/7       | 2               |
| pipeline + security lens on a second model | 3/7       | 2               |

The honest reading: the pipeline's proven win is **precision** — half the false positives,
hallucinated findings dropped by the judge, structured patches with failure modes. Raw detection
is bounded by local model size; 7B+ models raise it. Run `eval/run.py` on your own machine and
model — that is what it is for. No commercial vendor publishes comparable numbers.

Different local models catch different bugs: on this machine gemma4:e2b found hardcoded
credentials that the qwen family missed, which is why `security_model` exists.

## Available Commands Reference

| Command                                     | Description                                              |
| ------------------------------------------- | -------------------------------------------------------- |
| `ollakit review`                            | Review staged changes (five-stage pipeline)              |
| `ollakit review --branch REF`               | Review REF...HEAD                                        |
| `ollakit review --model M`                  | Override the chat model                                  |
| `ollakit review --security-model M`         | Override the security-lens model                         |
| `ollakit review --json`                     | Emit findings as JSON                                    |
| `ollakit review --report PATH`              | Write the markdown report                                |
| `ollakit review --fix-prompt [DIR]`         | One agent fix brief per finding                          |
| `ollakit review --fix-prompt-all [PATH]`    | One combined agent fix brief                             |
| `ollakit review --fast`                     | v1 single-pass review (skip context/gates/lens)          |
| `ollakit review --no-gates`                 | Full pipeline but skip the judge/actionability gates     |
| `ollakit review --install-hook`             | Install the pre-commit hook (blocks critical commits)    |
| `ollakit ask "question" --index DIR`        | One-shot RAG answer with citations                       |
| `ollakit ask --chat --index DIR`            | Interactive RAG session                                  |
| `ollakit ask --reindex`                     | Force index rebuild                                      |
| `ollakit ask --k N`                         | Retrieve N chunks (default 5)                            |
| `ollakit organize DIR`                      | Dry-run the organization plan                            |
| `ollakit organize DIR --apply`              | Confirm, then move files                                 |
| `ollakit organize DIR --apply --yes`        | Apply without the confirmation prompt                    |
| `ollakit organize DIR --recursive`          | Include subdirectories                                   |
| `ollakit organize --undo JOURNAL`           | Revert a previous apply exactly                          |

## Testing

```bash
# full suite (62 tests, no Ollama calls — model interactions are mocked)
.venv/bin/python -m pytest

# one module
.venv/bin/python -m pytest tests/test_gates.py

# verbose, stop at first failure
.venv/bin/python -m pytest -x -v
```

Test structure mirrors the package: `test_review.py` (v1 surface), `test_context.py`,
`test_linters.py`, `test_generate.py`, `test_gates.py`, `test_handoff.py`, `test_organize.py`,
`test_ask.py`, `test_scaffold.py`. Design rules: model calls are monkeypatched with deterministic
stubs, `--fast`/gates seams are monkeypatch targets, and every bug found in verification got a
regression test — including the OOM on whole-file `context.enrich()` calls.

## Evaluation

```bash
# gated pipeline (default)
.venv/bin/python eval/run.py

# v1 baseline for comparison
.venv/bin/python eval/run.py --fast

# route the security lens through a second model
.venv/bin/python eval/run.py --security-model gemma4:e2b
```

The harness stages each fixture in a scratch git repo, drives the real pipeline (real model
calls — needs Ollama running), and scores:

- **detection** — planted bugs found within ±2 lines of the manifest line
- **false positives** — findings on clean fixtures, or far from any planted bug
- **gate drops** — candidates removed by the judge / actionability filter

Fixtures live in `eval/fixtures/` (`buggy/` plants SQL injection, hardcoded credentials,
resource leaks, off-by-one, None dereference, bare-except swallowing, shared mutable defaults;
`clean/` are their no-bug twins). Results are written to `eval/results-<config>.json`.

## Using the Pre-commit Hook in CI

```bash
cd your-repo
ollakit review --install-hook
```

The hook runs `ollakit review --staged` before each commit and blocks it on any critical
finding. It bakes in the **absolute path** of the ollakit executable, so it works even when the
venv is not active. Uninstall with `rm .git/hooks/pre-commit`. To bypass for a known-good
commit: `git commit --no-verify`.

For CI (no hook needed), the exit code is the interface:

```yaml
# GitHub Actions example
- name: ollakit review
  run: |
    ollakit review --branch ${{ github.base_ref }}
```

Exit 0 = no critical findings; exit 1 = at least one critical finding (the job fails).

## Troubleshooting

### `Cannot reach Ollama at localhost:11434`

Ollama is not running. Start it (`ollama serve` or the desktop app) and retry.

### `No Ollama models installed`

Pull one: `ollama pull qwen3:4b` (small, general) or a 7B-class model for better review depth.

### `No embedding model installed` (from `ask`)

Run `ollama pull nomic-embed-text`, then retry. The index builds after that.

### Review is slow

The full pipeline makes 2 generation calls per file plus one judge call per candidate — expect
seconds-to-minutes on small models. Use `--fast` for quick checks, or scope reviews to staged
commits rather than whole branches. Check `ollama ps` — if two models are resident
(`chat_model` + `security_model`), memory pressure forces CPU offload; a single-model setup is
faster on 16 GB machines.

### Findings disagree with each other or look wrong

Read the `Suppressed` section of `--report` first: the judge drops what it cannot verify, and
its rationales are recorded there. If a valid finding was dropped, the judge was wrong —
`--no-gates` bypasses it, and the eval fixtures are where to tune.

### `organize` moved something you didn't want moved

```bash
ollakit organize --undo ~/.cache/ollakit/organize-<stamp>.json
```

Every apply prints its journal path; nothing is ever deleted, so undo is always possible.

### Hook blocks a commit you know is fine

Either fix the finding, or `git commit --no-verify` — the hook says so. Never edit the check to
make it pass.

### `ask` answers "does not contain the answer"

That is the no-hallucination guard working: the answer is not in the indexed top-k chunks. Try
`--k 8`, `--reindex` if files changed recently, or a differently-phrased question.

## Project Layout

See [Architecture](#architecture). Branching convention: features land through `feature/<name>`
branches → PR → review → merge to `main`; commits are granular (one idea each) so bisect works.

## Design Principles

1. **Local or nothing** — no cloud calls, no telemetry, no accounts. The only network path is
   your own Ollama server.
2. **Precision over volume** — one verified finding beats five vague ones; gates drop what
   cannot be verified, and say so.
3. **Reversibility** — `organize` journals everything and never deletes; hooks are one
   `rm` away from removal.
4. **Evidence culture** — "works" means pasted command output; the eval harness turns review
   quality into a number anyone can reproduce.
5. **Smallest change** — one pip dependency (`ollama`), stdlib everywhere else; linters are
   optional system tools, not requirements.

## Contributing

1. Branch from `main`: `git checkout -b feature/<name>`
2. Follow the repo's `AGENTS.md`; add tests for every behavior change
3. `.venv/bin/python -m pytest` must pass, and claims of "works" need real command output
4. Open a PR with Why / What changed / Scope / Verification; merge on green

If you run the eval on your hardware and model, opening an issue with your
`results-*.json` is one of the most useful contributions possible — it is the dataset no
vendor publishes.

## License

MIT — see [LICENSE](LICENSE).
