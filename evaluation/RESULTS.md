# JobFit AI — Evaluation Results

Committed summary of the AI evaluation required for submission. Raw, timestamped
run outputs (`evaluation/results/results_*.json`) are intentionally **not**
committed — they are generated artifacts, git-ignored via
`evaluation/results/*.json` — but the aggregated numbers and conclusions in this
file are copied directly from one of those real, locally-run evaluation files
and are reproducible by re-running the commands below.

- **Dataset:** 10 synthetic cases (`evaluation/cases.json`), each targeting a
  specific behavior relevant to JobFit's actual use (clear match, requirement
  absent from CV, explicitly contradicted requirement, required-vs-preferred
  importance, semantic paraphrase, requirement granularity, paraphrased
  evidence, out-of-scope non-job input, underspecified job input, and a
  prompt-injection attempt).
- **Runner:** `evaluation/run_evaluation.py`, 3 repetitions per case.
- **Model/config:** `qwen3:4b` via local Ollama, `LLM_REASONING_EFFORT=none`.
- **Methodology:** extraction and matching are evaluated **independently** —
  matching always runs against the dataset's own gold-standard requirements,
  never against whatever extraction happened to produce, so an extraction
  failure cannot silently cause a matching failure to be misattributed. See
  `evaluation/comparison.py` for the alias-based correctness comparison and
  `README.md`'s "AI evaluation" section for the full write-up this file backs.

## Baseline (production prompt)

**Extraction** — 30 total calls (10 cases × 3 repetitions):

| Metric | Result |
|---|---|
| Completion rate | 30/30 |
| Structured-output validity | 30/30 |
| Correctness | 22/30 = **73%** |
| Mean latency | 3607.7 ms |
| Median latency | 3408.3 ms |

**Matching** — 24 applicable calls (8 of the 10 cases have a CV to match against, × 3):

| Metric | Result |
|---|---|
| Completion rate | 24/24 |
| Structured-output validity | 24/24 |
| Correctness | 23/24 ≈ **96%** |
| Mean latency | 7649.0 ms |
| Median latency | 7470.9 ms |

## Important failures

- **Underspecified job input** ("We are hiring a developer."): 0/3 extraction
  correctness. The model consistently inferred plausible-sounding but entirely
  unstated requirements instead of correctly returning none. The clearest
  observed hallucination mode in this project.
- **Out-of-scope, non-job input** ("Happy birthday! Have a wonderful day."):
  1/3. In 2 of 3 runs the model still invented requirement-shaped output from
  clearly non-job text.
- **Nondeterminism across repeated runs:** latency and correctness both varied
  noticeably across the 3 repetitions of the same case in several categories —
  expected LLM behavior, and the reason the evaluation runs more than once per
  case.
- **The single matching failure (23/24):** one repetition of the "requirement
  not mentioned in the CV" case (SQL) returned `missing` instead of the gold
  `not_found` — i.e. the model asserted the CV actively showed the *absence*
  of SQL experience, when the CV simply never mentions SQL. This distinction
  matters for JobFit's schema (see README's "Confidence and uncertainty"
  section) and this miss shows the model doesn't always draw it correctly.

## Prompt comparison (Prompt A vs. Prompt B)

Prompt B = the production extraction prompt plus one added instruction telling
the model to extract independent requirements separately rather than merging
them. Implemented entirely under `evaluation/` (`evaluation/prompts.py`,
`evaluation/extraction_variants.py`); **`app/extraction.py`'s production prompt
was never modified.**

| | Prompt A (baseline) | Prompt B (granularity) |
|---|---|---|
| Overall extraction correctness | 22/30 = 73% | 23/30 = 77% |
| Target granularity case | 2/3 | **3/3** (improved) |
| Unrelated semantic/paraphrase case (cloud) | 2/3 | **1/3** (regressed) |

**Prompt B was not adopted into production.** It fixed the specific behavior
it targeted, but on this same small sample introduced a new, unrelated
regression of the same size on a different case — the "23 > 22" headline
number is a redistribution of the same total correct count across two
categories, not a clean improvement. With only 3 repetitions per case, neither
result is treated as statistically significant.

## Reproducing this evaluation

```bash
# Baseline (production prompt):
python -m evaluation.run_evaluation --runs 3

# Prompt B (granularity variant, evaluation-only):
LLM_REASONING_EFFORT=none python -m evaluation.run_evaluation --runs 3 --extraction-prompt granularity
```

Each run writes a new timestamped `evaluation/results/results_<UTC timestamp>.json`
(git-ignored) and prints the same aggregate summary reproduced above.
