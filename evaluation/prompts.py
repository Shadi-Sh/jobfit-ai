"""Evaluation-only extraction prompt variants.

Prompt A ("baseline") is imported directly from app.extraction rather than
retyped, so it is guaranteed byte-identical to the current production
prompt — there is no way for this file to silently drift from production.

Prompt B ("granularity") is Prompt A plus one additional instruction,
defined only for this evaluation. app/extraction.py is never touched.
"""
from app.extraction import _SYSTEM_PROMPT as BASELINE_SYSTEM_PROMPT

GRANULARITY_ADDENDUM = (
    "Extract each independent skill or qualification as a separate requirement. "
    "Do not combine multiple independent requirements into one item."
)

GRANULARITY_SYSTEM_PROMPT = f"{BASELINE_SYSTEM_PROMPT} {GRANULARITY_ADDENDUM}"

PROMPT_VARIANTS = {
    "baseline": BASELINE_SYSTEM_PROMPT,
    "granularity": GRANULARITY_SYSTEM_PROMPT,
}
