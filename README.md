# ollakit

Local Ollama toolkit: a pre-commit code reviewer, a RAG chat over your notes, and a
reversible file organizer. All inference runs on your machine through Ollama.

## Install

Requires Python 3.10+ and a running Ollama server (`ollama serve`).

```sh
python3 -m venv .venv
.venv/bin/pip install -e .
```

On first use ollakit picks a chat model from what you have installed (prefers
`*coder*`, then qwen-family, then the largest local model) and remembers it in
`~/.config/ollakit/config.json`. Override per call with `--model`. On this
machine `Qwen3.5-uncensored:latest` was the best reviewer; smaller models
false-positived on safe code.

## review — code review before it lands

```sh
ollakit review                 # review staged changes (default)
ollakit review --branch main   # review diff from main to HEAD
ollakit review --json          # raw findings JSON
ollakit review --install-hook  # pre-commit hook that blocks commits with critical findings
```

Findings are grouped by file with severities `critical | warn | nit`. Exit code 1 on any
critical finding, so the hook (or CI) can block. The hook is written with the absolute
path of the `ollakit` executable; remove it with `rm .git/hooks/pre-commit`.

Limits, measured locally: a 4B-class model misses some real issues and occasionally
flags safe code; treat this as a first-pass filter, not a human review.

## ask — local RAG over a notes directory

```sh
ollakit pull nomic-embed-text              # one-time, ~275MB, stays local
ollakit ask "what did I decide about X?" --index ~/notes
ollakit ask --chat --index ~/notes         # interactive session
ollakit ask "..." --index ~/notes --reindex
```

Indexes `.md`, `.txt`, code and config files (hidden dirs, `node_modules`, `.git`
skipped) in chunks of ~800 characters, embeds them locally, and answers from the top-5
chunks with file citations. The index lives in `~/.cache/ollakit/` and is incremental
(files are re-embedded only when mtime or size changed). Questions outside the context
get "does not contain the answer", not an invention.

## organize — AI file sorting, reversibly

```sh
ollakit organize ~/Downloads              # dry-run: prints the plan, changes nothing
ollakit organize ~/Downloads --apply      # asks for confirmation, then moves
ollakit organize --undo ~/.cache/ollakit/organize-<stamp>.json
```

Files are classified into `Documents | Images | Videos | Archives | Code | Music |
Other` and moved there. It never deletes, skips hidden files, suffixes collisions
(`report (2).pdf`), preserves mtimes, and journals every move for exact undo.

## Configuration

`~/.config/ollakit/config.json`: `chat_model`, `embed_model`, `notes_dir` (the
default `--index` for `ask`). All optional; ollakit fills them on first use.
