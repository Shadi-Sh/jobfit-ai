import pytest

from evaluation.comparison import (
    aggregate_results,
    check_evidence_consistency,
    compare_extraction,
    compare_matching_statuses,
    name_matches_accepted,
    normalize_name,
)
from app.models import MatchStatus, Requirement, RequirementImportance, RequirementMatch


def _req(name: str, importance: RequirementImportance) -> Requirement:
    return Requirement(name=name, importance=importance)


def _match(name: str, importance: RequirementImportance, status: MatchStatus, cv_evidence=None) -> RequirementMatch:
    return RequirementMatch(
        requirement=_req(name, importance),
        status=status,
        cv_evidence=cv_evidence,
        explanation="irrelevant for these tests",
    )


# --- normalize_name / name_matches_accepted ---


def test_normalize_name_lowercases_and_collapses_whitespace():
    assert normalize_name("  Python   Developer ") == "python developer"


def test_name_matches_accepted_is_case_and_whitespace_insensitive():
    assert name_matches_accepted("python", ["Python"])
    assert name_matches_accepted("  PYTHON  ", ["python"])


def test_name_matches_accepted_does_not_match_unrelated_name():
    assert not name_matches_accepted("Java", ["Python"])


# --- compare_extraction ---

_PYTHON_DOCKER_EXPECTED = [
    {"concept": "python", "canonical_name": "Python", "accepted_names": ["Python"], "importance": "required"},
    {"concept": "docker", "canonical_name": "Docker", "accepted_names": ["Docker"], "importance": "preferred"},
]


def test_compare_extraction_correct_when_exact_match():
    actual = [
        _req("Python", RequirementImportance.REQUIRED),
        _req("Docker", RequirementImportance.PREFERRED),
    ]
    result = compare_extraction(_PYTHON_DOCKER_EXPECTED, actual)
    assert result["correct"] is True
    assert result["missing_concepts"] == []
    assert result["extra_names"] == []
    assert result["importance_mismatches"] == []


def test_compare_extraction_accepts_alias_name():
    expected = [
        {
            "concept": "rest_api_development",
            "canonical_name": "REST API development",
            "accepted_names": ["REST API development", "REST APIs", "REST API experience"],
            "importance": "required",
        }
    ]
    actual = [_req("REST APIs", RequirementImportance.REQUIRED)]
    result = compare_extraction(expected, actual)
    assert result["correct"] is True


def test_compare_extraction_detects_missing_requirement():
    actual = [_req("Python", RequirementImportance.REQUIRED)]  # Docker never extracted
    result = compare_extraction(_PYTHON_DOCKER_EXPECTED, actual)
    assert result["correct"] is False
    assert result["missing_concepts"] == ["docker"]
    assert result["extra_names"] == []


def test_compare_extraction_detects_extra_invented_requirement():
    actual = [
        _req("Python", RequirementImportance.REQUIRED),
        _req("Docker", RequirementImportance.PREFERRED),
        _req("Kubernetes", RequirementImportance.PREFERRED),  # not expected
    ]
    result = compare_extraction(_PYTHON_DOCKER_EXPECTED, actual)
    assert result["correct"] is False
    assert result["missing_concepts"] == []
    assert result["extra_names"] == ["Kubernetes"]


def test_compare_extraction_detects_importance_mismatch():
    actual = [
        _req("Python", RequirementImportance.PREFERRED),  # should be required
        _req("Docker", RequirementImportance.PREFERRED),
    ]
    result = compare_extraction(_PYTHON_DOCKER_EXPECTED, actual)
    assert result["correct"] is False
    assert len(result["importance_mismatches"]) == 1
    assert result["importance_mismatches"][0]["concept"] == "python"


def test_compare_extraction_correct_with_no_expected_and_no_actual():
    assert compare_extraction([], [])["correct"] is True


def test_compare_extraction_flags_invented_requirement_when_none_expected():
    result = compare_extraction([], [_req("Something", RequirementImportance.REQUIRED)])
    assert result["correct"] is False
    assert result["extra_names"] == ["Something"]


# --- compare_matching_statuses ---


def test_compare_matching_statuses_correct():
    name_to_concept = {"Python": "python", "Docker": "docker"}
    actual = [
        _match("Python", RequirementImportance.REQUIRED, MatchStatus.MATCH, "3 years of Python"),
        _match("Docker", RequirementImportance.PREFERRED, MatchStatus.NOT_FOUND),
    ]
    result = compare_matching_statuses({"python": "match", "docker": "not_found"}, actual, name_to_concept)
    assert result["correct"] is True
    assert result["mismatches"] == []
    assert result["missing_concepts"] == []


def test_compare_matching_statuses_detects_status_mismatch():
    name_to_concept = {"Python": "python"}
    actual = [_match("Python", RequirementImportance.REQUIRED, MatchStatus.MATCH, "evidence")]
    result = compare_matching_statuses({"python": "missing"}, actual, name_to_concept)
    assert result["correct"] is False
    assert result["mismatches"][0]["concept"] == "python"
    assert result["mismatches"][0]["expected_status"] == "missing"
    assert result["mismatches"][0]["actual_status"] == "match"


def test_compare_matching_statuses_detects_missing_concept_in_actual():
    name_to_concept = {"Python": "python"}
    actual = []  # matching returned nothing for an expected concept
    result = compare_matching_statuses({"python": "match"}, actual, name_to_concept)
    assert result["correct"] is False
    assert result["missing_concepts"] == ["python"]


# --- check_evidence_consistency ---


def test_evidence_consistency_true_when_match_has_evidence_and_not_found_has_none():
    matches = [
        _match("Python", RequirementImportance.REQUIRED, MatchStatus.MATCH, "some evidence"),
        _match("Docker", RequirementImportance.PREFERRED, MatchStatus.NOT_FOUND, None),
    ]
    assert check_evidence_consistency(matches) is True


def test_evidence_consistency_false_when_match_has_no_evidence():
    matches = [_match("Python", RequirementImportance.REQUIRED, MatchStatus.MATCH, None)]
    assert check_evidence_consistency(matches) is False


def test_evidence_consistency_false_when_not_found_has_evidence():
    matches = [_match("Docker", RequirementImportance.PREFERRED, MatchStatus.NOT_FOUND, "unexpected evidence")]
    assert check_evidence_consistency(matches) is False


# --- aggregate_results ---


def _record(
    case_id="case_01",
    category="clear_case",
    extraction_correct=True,
    extraction_structured_valid=True,
    extraction_latency_ms=100.0,
    extraction_failure_type=None,
    matching_correct=True,
    matching_structured_valid=True,
    matching_latency_ms=200.0,
    matching_failure_type=None,
):
    return {
        "case_id": case_id,
        "category": category,
        "run_number": 1,
        "extraction_structured_valid": extraction_structured_valid,
        "extraction_correct": extraction_correct,
        "extraction_latency_ms": extraction_latency_ms,
        "extraction_failure_type": extraction_failure_type,
        "matching_structured_valid": matching_structured_valid,
        "matching_correct": matching_correct,
        "matching_latency_ms": matching_latency_ms,
        "matching_failure_type": matching_failure_type,
    }


def test_aggregate_results_computes_rates_and_latency():
    records = [
        _record(extraction_correct=True, matching_correct=True),
        _record(extraction_correct=False, extraction_failure_type="incorrect_result", matching_correct=False, matching_failure_type="incorrect_result"),
    ]
    summary = aggregate_results(records)

    assert summary["total_runs"] == 2
    assert summary["extraction"]["attempted"] == 2
    assert summary["extraction"]["completed"] == 2
    assert summary["extraction"]["correct"] == 1
    assert summary["extraction"]["correct_denominator"] == 2
    assert summary["extraction"]["correctness_rate"] == 0.5
    assert summary["extraction"]["structured_valid_rate"] == 1.0
    assert summary["extraction"]["latency_ms"]["mean"] == 100.0
    assert summary["extraction"]["failures_by_type"] == {"incorrect_result": 1}
    assert summary["matching_evaluated_count"] == 2
    assert summary["matching"]["correctness_rate"] == 0.5


def test_aggregate_results_excludes_not_applicable_matching_from_matching_stats():
    records = [
        _record(matching_correct=None, matching_structured_valid=None, matching_latency_ms=None, matching_failure_type=None),
        _record(matching_correct=True),
    ]
    summary = aggregate_results(records)

    assert summary["matching_evaluated_count"] == 1
    assert summary["matching"]["attempted"] == 1
    assert summary["matching"]["correctness_rate"] == 1.0


def test_aggregate_results_groups_by_category():
    records = [
        _record(case_id="case_01", category="clear_case", extraction_correct=True),
        _record(case_id="case_02", category="requirement_not_found_in_cv", extraction_correct=False),
    ]
    summary = aggregate_results(records)

    assert summary["by_category"]["clear_case"]["count"] == 1
    assert summary["by_category"]["clear_case"]["extraction"]["correctness_rate"] == 1.0
    assert summary["by_category"]["requirement_not_found_in_cv"]["extraction"]["correctness_rate"] == 0.0


# --- Regression tests for the aggregation bug: a real False result, and a
# timeout (None), must never be conflated, and neither can be silently
# dropped in a way that makes a dataset containing real failures look
# like a 100% pass rate. ---


def test_aggregate_results_false_results_reduce_correctness_below_100_percent():
    """A dataset with a genuine semantic failure must not report 100% correctness."""
    records = [
        _record(extraction_correct=True),
        _record(extraction_correct=True),
        _record(extraction_correct=False, extraction_failure_type="incorrect_result"),
    ]
    summary = aggregate_results(records)

    assert summary["extraction"]["correct"] == 2
    assert summary["extraction"]["correct_denominator"] == 3
    assert summary["extraction"]["correctness_rate"] == pytest.approx(2 / 3)
    assert summary["extraction"]["correctness_rate"] < 1.0


def test_aggregate_results_mix_of_true_false_and_none_computed_correctly():
    """Exact scenario from the bug report: a mix of pass / fail / timeout."""
    records = [
        _record(extraction_correct=True, extraction_structured_valid=True),
        _record(extraction_correct=True, extraction_structured_valid=True),
        _record(extraction_correct=False, extraction_structured_valid=False, extraction_failure_type="incorrect_result"),
        _record(
            extraction_correct=None,
            extraction_structured_valid=None,
            extraction_latency_ms=None,
            extraction_failure_type="llm_timeout",
        ),
    ]
    summary = aggregate_results(records)
    ext = summary["extraction"]

    # 4 calls were attempted; only 3 actually completed (1 timed out).
    assert ext["attempted"] == 4
    assert ext["completed"] == 3
    assert ext["completion_rate"] == pytest.approx(3 / 4)

    # Correctness/validity are scored only among the 3 completed calls,
    # and the real False result must count against them.
    assert ext["correct_denominator"] == 3
    assert ext["correct"] == 2
    assert ext["correctness_rate"] == pytest.approx(2 / 3)
    assert ext["structured_valid_denominator"] == 3
    assert ext["structured_valid"] == 2
    assert ext["structured_valid_rate"] == pytest.approx(2 / 3)

    # The timeout must never be silently absorbed into a 100% figure.
    assert ext["correctness_rate"] != 1.0
    assert ext["failures_by_type"] == {"incorrect_result": 1, "llm_timeout": 1}


def test_aggregate_results_all_timeouts_yields_none_rates_not_100_percent():
    """If every call times out, correctness/validity must be n/a (None), never 100%."""
    records = [
        _record(
            extraction_correct=None,
            extraction_structured_valid=None,
            extraction_latency_ms=None,
            extraction_failure_type="llm_timeout",
        )
        for _ in range(3)
    ]
    summary = aggregate_results(records)
    ext = summary["extraction"]

    assert ext["attempted"] == 3
    assert ext["completed"] == 0
    assert ext["completion_rate"] == 0.0
    assert ext["correctness_rate"] is None
    assert ext["structured_valid_rate"] is None
    assert ext["failures_by_type"] == {"llm_timeout": 3}


def test_aggregate_results_handles_llm_failure_as_excluded_from_correctness_but_records_failure_type():
    records = [
        _record(
            extraction_correct=None,
            extraction_structured_valid=None,
            extraction_failure_type="llm_timeout",
            matching_correct=None,
            matching_structured_valid=None,
            matching_failure_type="llm_timeout",
        ),
        _record(),
    ]
    summary = aggregate_results(records)

    # correctness_rate excludes the None (LLM failure) entry from its denominator,
    # but it is still visible via attempted vs completed and failures_by_type.
    assert summary["extraction"]["attempted"] == 2
    assert summary["extraction"]["completed"] == 1
    assert summary["extraction"]["correctness_rate"] == 1.0
    assert summary["extraction"]["failures_by_type"] == {"llm_timeout": 1}
    assert summary["matching"]["failures_by_type"] == {"llm_timeout": 1}
