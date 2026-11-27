"""ollakit review: production-pipeline code review on a local model.

Package layout: diff (fetch/parse), context (enrichment), linters
(deterministic pre-filter), generate (constrained generation), gates
(factual judge + actionability), handoff (report + agent fix prompts).
"""
