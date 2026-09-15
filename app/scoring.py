from app.models import MatchStatus, RequirementImportance, RequirementMatch

_IMPORTANCE_POINTS = {
    RequirementImportance.REQUIRED: 2,
    RequirementImportance.PREFERRED: 1,
}


def calculate_fit_score(matches: list[RequirementMatch]) -> float:
    if not matches:
        return 0.0

    achieved = 0
    max_possible = 0

    for match in matches:
        points = _IMPORTANCE_POINTS.get(match.requirement.importance, 0)
        max_possible += points
        if match.status == MatchStatus.MATCH:
            achieved += points

    if max_possible == 0:
        return 0.0

    return achieved / max_possible * 100
