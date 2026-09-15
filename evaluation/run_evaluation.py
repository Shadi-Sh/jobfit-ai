"""Evaluation runner for JobFit's LLM components (extraction and matching).

Evaluates extraction and matching independently against a fixed synthetic
dataset (cases.json), using the configured production LLM settings from
environment variables. Does not modify production prompts or behavior, and
does not call another LLM as a judge.

Usage:
    python evaluation/run_evaluation.py --runs 3
    python -m evaluation.run_evaluation --runs 3 --extraction-prompt granularity

--extraction-prompt selects which extraction system prompt to evaluate:
    baseline     production prompt, calls app.extraction.extract_requirements
                 directly and unmodified (default).
    granularity  the evaluation-only Prompt B variant defined in
                 evaluation/prompts.py (baseline + one extra instruction),
                 run through evaluation/extraction_variants.py so it is
                 checked against the exact same JSON/Pydantic contract as
                 production without touching app/extraction.py.
Matching always uses the unmodified production matching prompt regardless
of --extraction-prompt.
"""
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from app.extraction import ExtractionError, extract_requirements
from app.llm import LLMTimeoutError, LLMUnavailableError
from app.matching import MatchingError, match_cv_to_requirements
from app.models import Requirement, RequirementImportance
from evaluation.comparison import (
    aggregate_results,
    check_evidence_consistency,
    compare_extraction,
    compare_matching_statuses,
)
from evaluation.extraction_variants import extract_requirements_with_prompt
from evaluation.prompts import PROMPT_VARIANTS

CASES_PATH = Path(__file__).resolve().parent / "cases.json"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
DEFAULT_EXTRACTION_PROMPT = "baseline"


def load_cases(cases_path: Path = CASES_PATH) -> list[dict]:
    return json.loads(cases_path.read_text())


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


def evaluate_extraction(case: dict, extraction_prompt: str = DEFAULT_EXTRACTION_PROMPT) -> dict:
    start = time.perf_counter()
    try:
        if extraction_prompt == "baseline":
            # Calls production's extract_requirements directly and unmodified —
            # the baseline path can never drift from what /analyze actually runs.
            actual = extract_requirements(case["job_description"])
        else:
            actual = extract_requirements_with_prompt(
                case["job_description"], PROMPT_VARIANTS[extraction_prompt]
            )
    except ExtractionError:
        return {
            "structured_valid": False,
            "correct": False,
            "latency_ms": _elapsed_ms(start),
            "failure_type": "invalid_structured_output",
            "details": None,
        }
    except LLMTimeoutError:
        return {
            "structured_valid": None,
            "correct": None,
            "latency_ms": _elapsed_ms(start),
            "failure_type": "llm_timeout",
            "details": None,
        }
    except LLMUnavailableError:
        return {
            "structured_valid": None,
            "correct": None,
            "latency_ms": _elapsed_ms(start),
            "failure_type": "llm_unavailable",
            "details": None,
        }

    latency_ms = _elapsed_ms(start)
    comparison = compare_extraction(case["expected_requirements"], actual)
    return {
        "structured_valid": True,
        "correct": comparison["correct"],
        "latency_ms": latency_ms,
        "failure_type": None if comparison["correct"] else "incorrect_result",
        "details": comparison,
    }


def evaluate_matching(case: dict, name_to_concept: dict) -> dict | None:
    if not case["matching_applicable"]:
        return None

    gold_requirements = [
        Requirement(name=c["canonical_name"], importance=RequirementImportance(c["importance"]))
        for c in case["expected_requirements"]
    ]

    start = time.perf_counter()
    try:
        actual = match_cv_to_requirements(case["cv_text"], gold_requirements)
    except MatchingError:
        return {
            "structured_valid": False,
            "correct": False,
            "latency_ms": _elapsed_ms(start),
            "failure_type": "invalid_structured_output",
            "evidence_consistent": None,
            "details": None,
        }
    except LLMTimeoutError:
        return {
            "structured_valid": None,
            "correct": None,
            "latency_ms": _elapsed_ms(start),
            "failure_type": "llm_timeout",
            "evidence_consistent": None,
            "details": None,
        }
    except LLMUnavailableError:
        return {
            "structured_valid": None,
            "correct": None,
            "latency_ms": _elapsed_ms(start),
            "failure_type": "llm_unavailable",
            "evidence_consistent": None,
            "details": None,
        }

    latency_ms = _elapsed_ms(start)
    comparison = compare_matching_statuses(case["expected_matches"], actual, name_to_concept)
    return {
        "structured_valid": True,
        "correct": comparison["correct"],
        "latency_ms": latency_ms,
        "failure_type": None if comparison["correct"] else "incorrect_result",
        "evidence_consistent": check_evidence_consistency(actual),
        "details": comparison,
    }


def evaluate_case(case: dict, run_number: int, extraction_prompt: str = DEFAULT_EXTRACTION_PROMPT) -> dict:
    name_to_concept = {c["canonical_name"]: c["concept"] for c in case["expected_requirements"]}

    extraction_result = evaluate_extraction(case, extraction_prompt)
    matching_result = evaluate_matching(case, name_to_concept)

    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "run_number": run_number,
        "extraction_prompt": extraction_prompt,
        "extraction_structured_valid": extraction_result["structured_valid"],
        "extraction_correct": extraction_result["correct"],
        "extraction_latency_ms": extraction_result["latency_ms"],
        "extraction_failure_type": extraction_result["failure_type"],
        "extraction_details": extraction_result["details"],
        "matching_structured_valid": matching_result["structured_valid"] if matching_result else None,
        "matching_correct": matching_result["correct"] if matching_result else None,
        "matching_latency_ms": matching_result["latency_ms"] if matching_result else None,
        "matching_failure_type": matching_result["failure_type"] if matching_result else None,
        "matching_evidence_consistent": matching_result["evidence_consistent"] if matching_result else None,
        "matching_details": matching_result["details"] if matching_result else None,
    }


def _fmt_rate_with_n(rate: float | None, numerator: int, denominator: int) -> str:
    if rate is None:
        return f"n/a (0/{denominator})"
    return f"{rate * 100:.0f}% ({numerator}/{denominator})"


def _fmt_outcome(correct: bool | None, failure_type: str | None) -> str:
    """Render a tri-state (True/False/None) outcome without collapsing None into FAIL."""
    if correct is True:
        return "OK"
    if correct is False:
        return "FAIL"
    if failure_type is not None:
        return f"ERROR({failure_type})"
    return "N/A"


def _print_component_summary(label: str, stats: dict) -> None:
    print(f"\n{label}:")
    print(f"  attempted:                        {stats['attempted']}")
    print(
        "  completion rate (got a response): "
        f"{_fmt_rate_with_n(stats['completion_rate'], stats['completed'], stats['attempted'])}"
    )
    print(
        "  structured-output validity"
        f" (among completed): {_fmt_rate_with_n(stats['structured_valid_rate'], stats['structured_valid'], stats['structured_valid_denominator'])}"
    )
    print(
        "  correctness (among completed):    "
        f"{_fmt_rate_with_n(stats['correctness_rate'], stats['correct'], stats['correct_denominator'])}"
    )
    lat = stats["latency_ms"]
    print(f"  latency ms (mean / median):        {lat['mean']} / {lat['median']}")
    print(f"  failures by type:                  {stats['failures_by_type'] or '(none)'}")


def print_summary(summary: dict, output_path: Path) -> None:
    print("=" * 70)
    print("EVALUATION SUMMARY")
    print("=" * 70)
    print(f"Total (case x run) records: {summary['total_runs']}")
    print(f"Matching-applicable records: {summary['matching_evaluated_count']}")

    _print_component_summary("Extraction", summary["extraction"])
    _print_component_summary("Matching", summary["matching"])

    print("\nBy category:")
    for category, cat in summary["by_category"].items():
        ext, match = cat["extraction"], cat["matching"]
        print(
            f"  {category}: n={cat['count']} "
            f"extraction_correct={_fmt_rate_with_n(ext['correctness_rate'], ext['correct'], ext['correct_denominator'])} "
            f"matching_correct={_fmt_rate_with_n(match['correctness_rate'], match['correct'], match['correct_denominator'])}"
        )

    print(f"\nResults written to: {output_path}")
    print(
        "\nNOTE: with only a few repetitions per case, these rates are indicative only — "
        "not statistically significant. 'Completion rate' below 100% means some calls timed "
        "out or the LLM was unavailable — those are excluded from validity/correctness rates "
        "(no output to score), not silently counted as passes."
    )


def main(argv: list[str] | None = None) -> dict:
    parser = argparse.ArgumentParser(description="Run the JobFit LLM evaluation suite.")
    parser.add_argument("--runs", type=int, default=3, help="Repetitions per case (default: 3)")
    parser.add_argument("--cases-file", type=Path, default=CASES_PATH)
    parser.add_argument("--output-dir", type=Path, default=RESULTS_DIR)
    parser.add_argument(
        "--extraction-prompt",
        choices=sorted(PROMPT_VARIANTS),
        default=DEFAULT_EXTRACTION_PROMPT,
        help="Extraction system prompt variant to evaluate (default: baseline = production prompt).",
    )
    args = parser.parse_args(argv)

    cases = load_cases(args.cases_file)
    records = []

    for case in cases:
        for run_number in range(1, args.runs + 1):
            record = evaluate_case(case, run_number, args.extraction_prompt)
            records.append(record)
            extraction_outcome = _fmt_outcome(record["extraction_correct"], record["extraction_failure_type"])
            matching_outcome = _fmt_outcome(record["matching_correct"], record["matching_failure_type"])
            print(
                f"[{record['case_id']}][run {run_number}/{args.runs}] "
                f"extraction={extraction_outcome} matching={matching_outcome}"
            )

    summary = aggregate_results(records)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = args.output_dir / f"results_{timestamp}.json"
    output_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "runs_per_case": args.runs,
                "extraction_prompt": args.extraction_prompt,
                "records": records,
                "summary": summary,
            },
            indent=2,
        )
    )

    print_summary(summary, output_path)
    return {"records": records, "summary": summary, "output_path": output_path}


if __name__ == "__main__":
    main()
