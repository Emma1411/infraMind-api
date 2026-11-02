from models.evaluation import ArchitectureResult, CriterionScore, EvaluationResult, SensitivityEntry, Verdict

CRITERIA_FR = {
    "cost": "coût",
    "security": "sécurité",
    "performance": "performance",
    "availability": "disponibilité",
    "scalability": "évolutivité",
    "maintenance": "maintenance",
    "portability": "portabilité",
    "rollback": "restauration",
}
RATED = ("security", "performance", "availability", "scalability", "maintenance", "portability", "rollback")

SENSITIVITY_SHOWN = 3
MAX_WARNINGS = 5
MAX_ARCH_WARNINGS = 2
PRIORITIES_SHOWN = 4


def safe_warnings(result: EvaluationResult) -> list[str]:
    """Avertissements sans texte saisi par l'utilisateur (un champ libre pourrait contenir une consigne)."""
    return [w for w in result.global_warnings if not w.startswith("Fournisseur imposé «")][:MAX_WARNINGS]


def strengths_and_weaknesses(
    arch: ArchitectureResult, n: int = 2
) -> tuple[list[CriterionScore], list[CriterionScore]]:
    rated = [s for s in arch.scores if s.criterion in RATED]
    best = sorted(rated, key=lambda s: (-s.score, -s.weight))[:n]
    worst = sorted(rated, key=lambda s: (s.score, -s.weight))[:n]
    return best, worst


def _view(score: CriterionScore) -> dict:
    return {
        "criterion": CRITERIA_FR[score.criterion],
        "score_out_of_5": int(round(score.score / 20)),
        "why": score.why,
    }


def _sensitivity_view(entry: SensitivityEntry) -> dict:
    return {
        "question": entry.question,
        "status": entry.status,
        "current_value": entry.current_label,
        "cost_min": entry.cost_min,
        "cost_max": entry.cost_max,
        "changes_recommendation": entry.changes_recommendation,
    }


def build_payload(result: EvaluationResult) -> dict:
    live = [a for a in result.ranking if a.verdict != Verdict.eliminated]
    cost_rank = {a.id: position + 1 for position, a in enumerate(sorted(live, key=lambda a: a.cost_low))}

    architectures = []
    for arch in result.ranking:
        best, worst = strengths_and_weaknesses(arch)
        entry = {
            "id": arch.id,
            "label": arch.label,
            "status": arch.verdict.value,
            "score_out_of_100": arch.total_score,
            "cost_low": arch.cost_low,
            "cost_high": arch.cost_high,
            "cost_rank_among_eligible": cost_rank.get(arch.id),
            "estimate_complete": arch.estimate_complete,
            "prices_to_verify": arch.needs_verification,
            "budget_risk": arch.budget_risk.value if arch.budget_risk else None,
            "maintenance_hours_per_month": arch.maintenance_hours_per_month,
            "eliminated_reasons": arch.eliminated_reasons,
            "unmet_requirements": arch.requirements_unmet,
            "strengths": [_view(s) for s in best],
            "weaknesses": [_view(s) for s in worst],
        }
        if arch.id == result.recommended_id:
            entry["warnings"] = arch.warnings[:MAX_ARCH_WARNINGS]
        architectures.append(entry)

    top_weights = sorted(result.weights, key=lambda w: -w.weight)[:PRIORITIES_SHOWN]
    sensitivity = [
        _sensitivity_view(e) for e in result.sensitivity if e.arch_id == result.recommended_id
    ][:SENSITIVITY_SHOWN]

    return {
        "recommended_id": result.recommended_id,
        "others_to_explain": [a.id for a in result.ranking if a.id != result.recommended_id],
        "project_size": result.tier_label,
        "currency": "dollars américains par mois, hors taxes",
        "priorities": [{"criterion": CRITERIA_FR[w.criterion], "weight_percent": w.weight} for w in top_weights],
        "priority_reasons": result.weight_reasons,
        "warnings": safe_warnings(result),
        "architectures": architectures,
        "sensitivity": sensitivity,
    }