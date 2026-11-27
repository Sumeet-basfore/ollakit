# ollakit

Local Ollama toolkit. Python, single dependency (`ollama`).

## Commands (verified)

```factory
test: .venv/bin/python -m pytest
run: .venv/bin/ollakit --help
```

## Conventions

Before you change code here, read the single prosci skill that matches this request and follow it
(skills live in `/home/sumeet/personal-repo/projects/prosci/skills/`).

- Stdlib only beyond the `ollama` package; no new dependency without a stated reason.
- Never delete user files in `organize`; every move is journaled for undo.
- Every claim of "works" carries the command and its output.

## Review pipeline notes

- review/ is a package: diff.py, context.py, linters.py, generate.py, gates.py, handoff.py.
- The factual judge in gates.py fails closed; never bypass gates to make a check pass.
- eval/run.py numbers go in the README only when pasted from a real run.
