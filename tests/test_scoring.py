import pytest
from pydantic import ValidationError

from app.models import MatchStatus, Requirement, RequirementImportance, RequirementMatch
from app.scoring import calculate_fit_score


def _match(importance: RequirementImportance, status: MatchStatus) -> RequirementMatch:
    return RequirementMatch(
        requirement=Requirement(name="Python", importance=importance),
        status=status,
        explanation="test",
    )


def test_empty_matches_returns_zero():
    assert calculate_fit_score([]) == 0.0


def test_all_required_matches_gives_full_score():
    matches = [
        _match(RequirementImportance.REQUIRED, MatchStatus.MATCH),
        _match(RequirementImportance.REQUIRED, MatchStatus.MATCH),
    ]
    assert calculate_fit_score(matches) == 100.0


def test_all_missing_gives_zero_score():
    matches = [
        _match(RequirementImportance.REQUIRED, MatchStatus.MISSING),
        _match(RequirementImportance.PREFERRED, MatchStatus.NOT_FOUND),
    ]
    assert calculate_fit_score(matches) == 0.0


def test_mixed_importance_and_status():
    matches = [
        _match(RequirementImportance.REQUIRED, MatchStatus.MATCH),  # 2 of 2
        _match(RequirementImportance.PREFERRED, MatchStatus.MATCH),  # 1 of 1
        _match(RequirementImportance.REQUIRED, MatchStatus.MISSING),  # 0 of 2
    ]
    # achieved = 3, max = 5 -> 60.0
    assert calculate_fit_score(matches) == 60.0


def test_unsupported_importance_value_is_rejected():
    with pytest.raises(ValidationError):
        Requirement(name="Python", importance="nice_to_have")
