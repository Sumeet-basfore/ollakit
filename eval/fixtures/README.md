# eval fixtures: planted bugs with known lines

Each file in `buggy/` has known defects recorded in `manifest.json`
(file, line, class). Files in `clean/` contain no planted defects and
must produce zero findings.

`run.py` drives each fixture through the review pipeline (a scratch git
repo stages the buggy version; `git diff --no-index` produces the diff
for clean twins) and reports:

- detection rate: planted bugs found (±2 lines) in surfaced findings
- false positives: findings on clean files or far from planted lines
- gate drops: candidates removed by the factual judge / actionability

Usage:
    .venv/bin/python eval/run.py            # gated pipeline
    .venv/bin/python eval/run.py --fast     # v1 single-pass baseline
