import logging
import time

from app.extraction import extract_requirements
from app.matching import match_cv_to_requirements
from app.models import JobFitAnalysis
from app.scoring import calculate_fit_score

logger = logging.getLogger(__name__)


def analyze_job_fit(cv_text: str, job_description: str) -> JobFitAnalysis:
    """Run the full JobFit pipeline: extract, match, score."""
    total_start = time.perf_counter()

    extraction_start = time.perf_counter()
    requirements = extract_requirements(job_description)
    extraction_ms = (time.perf_counter() - extraction_start) * 1000

    matching_start = time.perf_counter()
    matches = match_cv_to_requirements(cv_text, requirements)
    matching_ms = (time.perf_counter() - matching_start) * 1000

    scoring_start = time.perf_counter()
    fit_score = calculate_fit_score(matches)
    scoring_ms = (time.perf_counter() - scoring_start) * 1000

    total_ms = (time.perf_counter() - total_start) * 1000

    logger.info(
        "analyze_job_fit timing: extraction_ms=%.1f matching_ms=%.1f scoring_ms=%.1f total_ms=%.1f",
        extraction_ms,
        matching_ms,
        scoring_ms,
        total_ms,
    )

    return JobFitAnalysis(
        requirements=requirements,
        matches=matches,
        fit_score=fit_score,
    )
