"""Pure comparison and aggregation logic for the evaluation framework.

No LLM calls, no I/O. Kept separate from run_evaluation.py so it can be
unit-tested deterministically without Ollama.
"""
import statistics

from app.models import MatchStatus, RequirementMatch


def normalize_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def name_matches_accepted(actual_name: str, accepted_names: list[str]) -> bool:
    normalized_actual = normalize_name(actual_name)
    return any(normalize_name(candidate) == normalized_actual for candidate in accepted_names)


def compare_extraction(expected_requirements: list[dict], actual_requirements: list) -> dict:
    """Compare extracted requirements against the gold concepts for one case.

    `expected_requirements` is the case's list of
    {concept, canonical_name, accepted_names, importance} dicts.
    `actual_requirements` is the list[Requirement] returned by extract_requirements.
    """
    remaining_actual = list(actual_requirements)
    matched_concepts = set()
    importance_mismatches = []

    for expected in expected_requirements:
        found = next(
            (a for a in remaining_actual if name_matches_accepted(a.name, expected["accepted_names"])),
            None,
        )
        if found is None:
            continue
        remaining_actual.remove(found)
        matched_concepts.add(expected["concept"])
        if found.importance.value != expected["importance"]:
            importance_mismatches.append(
                {
                    "concept": expected["concept"],
                    "expected_importance": expected["importance"],
                    "actual_importance": found.importance.value,
                }
            )

    missing_concepts = [
        expected["concept"]
        for expected in expected_requirements
        if expected["concept"] not in matched_concepts
    ]
    extra_names = [a.name for a in remaining_actual]

    correct = not missing_concepts and not extra_names and not importance_mismatches

    return {
        "correct": correct,
        "missing_concepts": missing_concepts,
        "extra_names": extra_names,
        "importance_mismatches": importance_mismatches,
    }


def compare_matching_statuses(
    expected_matches: dict, actual_matches: list[RequirementMatch], name_to_concept: dict
) -> dict:
    """Compare each match's status against the expected status for its concept.

    `expected_matches` maps concept -> expected status string.
    `name_to_concept` maps a gold requirement's canonical_name -> concept, so an
    actual RequirementMatch (which only carries `requirement.name`) can be
    traced back to the concept it corresponds to.
    """
    mismatches = []
    seen_concepts = set()

    for match in actual_matches:
        concept = name_to_concept.get(match.requirement.name)
        if concept is None:
            mismatches.append({"concept": None, "name": match.requirement.name, "issue": "unknown_requirement_name"})
            continue

        seen_concepts.add(concept)
        expected_status = expected_matches.get(concept)
        if expected_status is None:
            mismatches.append({"concept": concept, "issue": "unexpected_concept"})
        elif match.status.value != expected_status:
            mismatches.append(
                {
                    "concept": concept,
                    "expected_status": expected_status,
                    "actual_status": match.status.value,
                }
            )

    missing_concepts = [concept for concept in expected_matches if concept not in seen_concepts]
    correct = not mismatches and not missing_concepts

    return {
        "correct": correct,
        "mismatches": mismatches,
        "missing_concepts": missing_concepts,
    }


def check_evidence_consistency(actual_matches: list[RequirementMatch]) -> bool:
    """MATCH should normally carry non-null cv_evidence; NOT_FOUND should normally carry null."""
    for match in actual_matches:
        if match.status == MatchStatus.MATCH and match.cv_evidence is None:
            return False
        if match.status == MatchStatus.NOT_FOUND and match.cv_evidence is not None:
            return False
    return True


def _latency_stats(latencies) -> dict:
    values = [latency for latency in latencies if latency is not None]
    if not values:
        return {"mean": None, "median": None, "count": 0}
    return {
        "mean": round(statistics.mean(values), 1),
        "median": round(statistics.median(values), 1),
        "count": len(values),
    }


def _failures_by_type(failure_types) -> dict:
    counts: dict[str, int] = {}
    for failure_type in failure_types:
        if failure_type is not None:
            counts[failure_type] = counts.get(failure_type, 0) + 1
    return counts


def _completion_stats(structured_valid_flags, correct_flags, attempted: int) -> dict:
    """Break a tri-state (True / False / None) metric into explicit counts.

    `attempted` is the total number of calls that were actually made (the
    denominator for `completion_rate`). Among those, a call either
    "completed" (produced a response — structured_valid is True or False,
    never None) or did not (LLM unavailable/timeout — structured_valid is
    None, and by construction `correct` is None too). `structured_valid_rate`
    and `correctness_rate` are computed only over completed calls: a timeout
    means no structured output was produced at all, so it cannot be scored
    as either valid/invalid or correct/incorrect — it is absence of a
    result, not a failed result. It is still visible via completion_rate.

    Every count used as a rate's denominator is included explicitly
    (attempted, completed, structured_valid_denominator, correct_denominator)
    so no percentage here can be read without also seeing what it's a
    percentage *of*.
    """
    structured_valid_flags = list(structured_valid_flags)
    correct_flags = list(correct_flags)

    completed = sum(1 for v in structured_valid_flags if v is not None)
    structured_valid_count = sum(1 for v in structured_valid_flags if v is True)
    correct_denominator = sum(1 for v in correct_flags if v is not None)
    correct_count = sum(1 for v in correct_flags if v is True)

    return {
        "attempted": attempted,
        "completed": completed,
        "completion_rate": (completed / attempted) if attempted else None,
        "structured_valid": structured_valid_count,
        "structured_valid_denominator": completed,
        "structured_valid_rate": (structured_valid_count / completed) if completed else None,
        "correct": correct_count,
        "correct_denominator": correct_denominator,
        "correctness_rate": (correct_count / correct_denominator) if correct_denominator else None,
    }


def _matching_was_attempted(record: dict) -> bool:
    """True iff matching was applicable for this record's case (whether or not it completed)."""
    return record["matching_latency_ms"] is not None or record["matching_failure_type"] is not None


def aggregate_results(records: list[dict]) -> dict:
    matching_attempted_records = [r for r in records if _matching_was_attempted(r)]

    def extraction_stats(recs: list[dict]) -> dict:
        stats = _completion_stats(
            (r["extraction_structured_valid"] for r in recs),
            (r["extraction_correct"] for r in recs),
            attempted=len(recs),
        )
        stats["latency_ms"] = _latency_stats(r["extraction_latency_ms"] for r in recs)
        stats["failures_by_type"] = _failures_by_type(r["extraction_failure_type"] for r in recs)
        return stats

    def matching_stats(recs: list[dict]) -> dict:
        attempted_recs = [r for r in recs if _matching_was_attempted(r)]
        stats = _completion_stats(
            (r["matching_structured_valid"] for r in attempted_recs),
            (r["matching_correct"] for r in attempted_recs),
            attempted=len(attempted_recs),
        )
        stats["latency_ms"] = _latency_stats(r["matching_latency_ms"] for r in attempted_recs)
        stats["failures_by_type"] = _failures_by_type(r["matching_failure_type"] for r in attempted_recs)
        return stats

    by_category = {}
    for category in sorted({r["category"] for r in records}):
        cat_records = [r for r in records if r["category"] == category]
        by_category[category] = {
            "count": len(cat_records),
            "extraction": extraction_stats(cat_records),
            "matching": matching_stats(cat_records),
        }

    return {
        "total_runs": len(records),
        "extraction": extraction_stats(records),
        "matching": matching_stats(records),
        "matching_evaluated_count": len(matching_attempted_records),
        "by_category": by_category,
    }
